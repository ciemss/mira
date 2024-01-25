"""This module implements parsing of a generic pysd model irrespective of source and source type
and extracting its contents to create an equivalent MIRA template model.
"""

import pandas as pd
import sympy
import re

from mira.metamodel import *
from mira.metamodel.utils import safe_parse_expr
from mira.metamodel import Concept, TemplateModel
from mira.sources.util import (
    parameter_to_mira,
    transition_to_templates,
    get_sympy,
)


NEW_CONTROL_DELIMETER = (
    " ******************************************************** .Control "
    "********************************************************"
)
CONTROL_VARIABLE_NAMES = {"FINALTIME", "INITIALTIME", "SAVEPER", "TIMESTEP"}
UTF_ENCODING = "{UTF-8} "
UNITS_MAPPING = {
    sympy.Symbol("Person"): sympy.Symbol("person"),
    sympy.Symbol("Persons"): sympy.Symbol("person"),
    sympy.Symbol("Day"): sympy.Symbol("day"),
    sympy.Symbol("Days"): sympy.Symbol("day"),
}


def template_model_from_pysd_model(
    pysd_model, model_text=None
) -> TemplateModel:
    """Given a model and its accompanying model text, parse the arguments to extract information
    to create an equivalent MIRA template model.

    Parameters
    ----------
    pysd_model : Model
        The pysd model object
    model_text : str
        The plain-text information representing the model structure. Used for extracting
        expressions.

    Returns
    -------
    :
        MIRA template model
    """

    model_split_text = model_text.split("|")
    model_doc_df = pysd_model.doc
    state_initial_values = pysd_model.run().iloc[0]

    # Mapping of variable name in vensim model to variable python-equivalent name
    old_name_new_pyname_map = dict(
        zip(model_doc_df["Real Name"], model_doc_df["Py Name"])
    )
    pyname_reverse_map = dict(
        zip(model_doc_df["Py Name"], model_doc_df["Real Name"])
    )

    symbols = dict(
        zip(
            model_doc_df["Py Name"],
            list(map(lambda x: sympy.Symbol(x), model_doc_df["Py Name"])),
        )
    )

    new_symbols = dict(
        zip(
            model_doc_df["Real Name"],
            list(map(lambda x: sympy.Symbol(x), model_doc_df["Py Name"])),
        )
    )

    # Mapping of name to string expression
    new_var_name_str_expression_map = {}
    new_var_name_sympy_expression_map = {}
    for text in model_split_text:
        if NEW_CONTROL_DELIMETER in text:
            break
        if "=" not in text:
            continue

        # first entry usually has encoding type
        if UTF_ENCODING in text:
            text = text.replace(UTF_ENCODING, "")

        var_declaration = text.split("~")[0].split("=")
        old_var_name = var_declaration[0].strip()
        text_expression = var_declaration[1]
        new_var_name_str_expression_map[
            old_name_new_pyname_map[old_var_name]
        ] = text_expression

    model_states = model_doc_df[model_doc_df["Type"] == "Stateful"]
    concepts = {}
    all_states = set()

    # map between states and incoming/out-coming rate laws
    state_rate_map = {}
    # map between states and sympy version of the INTEG expression representing that state
    state_sympy_map = {}

    # process states and build mapping of state to input rate laws and output rate laws
    for index, state in model_states.iterrows():
        concept_state = state_to_concept(state)
        concepts[concept_state.name] = concept_state
        all_states.add(concept_state.name)
        symbols[concept_state.name] = sympy.Symbol(concept_state.name)

        state_name = state["Py Name"]
        state_rate_map[state_name] = {"inputs": [], "outputs": []}
        state_expr_text = new_var_name_str_expression_map[state_name]
        state_arg_text = re.search("INTEG+ \( (.*),", state_expr_text).group(1)

        # maybe use mapping of real name to symbol of py name and don't have to call
        # process_expression_text
        # state_arg_sympy = process_expression_text(state_arg_text, symbols)

        state_arg_sympy = safe_parse_expr(state_arg_text, new_symbols)
        new_var_name_sympy_expression_map[state_name] = state_arg_sympy
        # map of states to rate laws that affect the state
        state_sympy_map[state_name] = state_arg_sympy

        # Create a map of states and whether the rate-law/s involved with a state are going in
        # or out of the state
        if state_arg_sympy.args:
            # if it's just the negation of a single symbol
            if (
                sympy.core.numbers.NegativeOne() in state_arg_sympy.args
                and len(state_arg_sympy.args) == 2
            ):
                str_symbol = str(state_arg_sympy)
                state_rate_map[state_name]["outputs"].append(str_symbol[1:])
            else:
                for rate_free_symbol in state_arg_sympy.args:
                    str_rate_free_symbol = str(rate_free_symbol)
                    if "-" in str_rate_free_symbol:
                        # Add the symbol to outputs symbol without the negative sign
                        state_rate_map[state_name]["outputs"].append(
                            str_rate_free_symbol[1:]
                        )
                    else:
                        state_rate_map[state_name]["inputs"].append(
                            str_rate_free_symbol
                        )
        else:
            # if it's just a single symbol (i.e. no negation), args property will be empty
            state_rate_map[state_name]["inputs"].append(str(state_arg_sympy))

    # process initials, currently we use the value of the state at timestamp 0
    mira_initials = {}
    for state_name, state_concept in concepts.items():
        initial = Initial(
            concept=concepts[state_name].copy(deep=True),
            expression=SympyExprStr(
                state_initial_values[pyname_reverse_map[state_name]]
            ),
        )
        mira_initials[initial.concept.name] = initial

    # process parameters
    mira_parameters = {}
    for name, expression in new_var_name_str_expression_map.items():
        if expression.replace(".", "").replace(" ", "").isdecimal():
            model_parameter_info = model_doc_df[model_doc_df["Py Name"] == name]
            if model_parameter_info["Units"].values[0]:
                unit_text = (
                    model_parameter_info["Units"].values[0].replace(" ", "")
                )
                parameter = {
                    "id": name,
                    "value": float(expression),
                    "description": model_parameter_info["Comment"].values[0],
                    "units": {"expression": unit_text},
                }
            else:
                # if units don't exist
                parameter = {
                    "id": name,
                    "value": float(expression),
                    "description": model_parameter_info["Comment"].values[0],
                }
                pass

            mira_parameters[name] = parameter_to_mira(parameter)

            # standardize parameter units if they exist
            if mira_parameters[name].units:
                param_unit = mira_parameters[name].units
                for old_unit_symbol, new_unit_symbol in UNITS_MAPPING.items():
                    param_unit.expression = param_unit.expression.subs(
                        old_unit_symbol, new_unit_symbol
                    )

    # construct transitions mapping that determine inputs and outputs states to a rate-law
    transition_map = {}
    auxiliaries = model_doc_df[model_doc_df["Type"] == "Auxiliary"]
    for index, aux_tuple in auxiliaries.iterrows():
        if (
            aux_tuple["Subtype"] == "Normal"
            and aux_tuple["Real Name"] not in CONTROL_VARIABLE_NAMES
        ):
            rate_name = aux_tuple["Py Name"]
            rate_expr = process_expression_text(
                new_var_name_str_expression_map[rate_name], symbols
            )
            input, output, controller = None, None, None

            # If we come across a rate-law that is leaving a state, we add the state as an input
            # to the rate-law, vice-versa if a rate-law is going into a state.
            for state_name, in_out in state_rate_map.items():
                if rate_name in in_out["outputs"]:
                    input = state_name
                if rate_name in in_out["inputs"]:
                    output = state_name
                    # if a state isn't consumed by a flow (the flow isn't listed as an output of
                    # the state) but affects the rate of a flow, then that state is a controller
                    if (
                        sympy.Symbol(state_name) in rate_expr.free_symbols
                        and rate_name
                        not in state_rate_map[state_name]["outputs"]
                    ):
                        controller = output

            transition_map[rate_name] = {
                "name": rate_name,
                "expression": rate_expr,
                "input": input,
                "output": output,
                "controller": controller,
            }

    used_states = set()

    # Create templates from transitions
    templates_ = []
    for template_id, (transition_name, transition) in enumerate(
        transition_map.items()
    ):
        input_concepts = []
        output_concepts = []
        controller_concepts = []
        input_name, output_name, controller_name = None, None, None
        if transition.get("input"):
            input_name = transition.get("input")
            input_concepts.append(concepts[input_name].copy(deep=True))
        if transition.get("output"):
            output_name = transition.get("output")
            output_concepts.append(concepts[output_name].copy(deep=True))
        if transition.get("controller"):
            controller_name = transition.get("controller")
            controller_concepts.append(
                concepts[controller_name].copy(deep=True)
            )

        used_states |= {input_name, output_name}

        templates_.extend(
            transition_to_templates(
                input_concepts=input_concepts,
                output_concepts=output_concepts,
                controller_concepts=controller_concepts,
                transition_rate=transition["expression"],
                transition_id=str(template_id + 1),
                transition_name=transition_name,
            )
        )

    tm_description = model_split_text[0].split("~")[1]
    anns = Annotations(description=tm_description)

    return TemplateModel(
        templates=templates_,
        parameters=mira_parameters,
        initials=mira_initials,
        annotations=anns,
    )


def state_to_concept(state) -> Concept:
    """Create a MIRA Concept from a state

    Parameters
    ----------
    state : pd.Series
        The series that contains state data

    Returns
    -------
    :
        The MIRA concept created from the state
    """
    name = state["Py Name"]
    description = state["Comment"]
    unit_dict = {
        "expression": state["Units"].replace(" ", "")
        if state["Units"]
        else None
    }
    unit_expr = get_sympy(unit_dict, UNIT_SYMBOLS)
    units_obj = Unit(expression=unit_expr) if unit_expr else None

    return Concept(name=name, units=units_obj, description=description)


def process_expression_text(expr_text, symbols):
    """Create a sympy expression from a string expression using the supplied mapping of symbols

    Parameters
    ----------
    expr_text : str
        The string expression

    symbols : dict[str,sympy.Symbol]
        A mapping of string symbol to a symbol in sympy

    Returns
    -------
    : sympy.Expr
        The sympy expression
    """
    # strip leading and trailing white spaces
    # remove spaces between operators and operands
    # replace space between two words that makeup a variable name with "_"'
    expr_text = (
        expr_text.strip()
        .replace(" * ", "*")
        .replace(" - ", "-")
        .replace(" / ", "/")
        .replace(" + ", "+")
        .replace("^", "**")
        .replace(" ", "_")
        .replace('"', "")
        .lower()
    )

    sympy_expr = safe_parse_expr(expr_text, symbols)
    return sympy_expr
