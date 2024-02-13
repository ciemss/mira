"""This module implements an API interface for retrieving Stella models by ISEE Systems
denoted by the .xmile, .xml, or .stmx extension through a locally downloaded file or URL. We
cannot process stella models with the .itmx extension. Additionally, the pysd library depends on
the parsimonious library which fails to parse a number of stella models with valid file
extensions.  We then convert the Stella model into a generic pysd model object that will be
parsed and converted to an equivalent MIRA template model. We preprocess the stella model file to
extract variable expressions.

Landing page for Stella: https://www.iseesystems.com/store/products/stella-online.aspx

Website containing sample Stella models: https://www.vensim.com/documentation/sample_models.html
"""

__all__ = [
    "template_model_from_stella_model_file",
    "template_model_from_stella_model_url",
    "process_file"
]

import tempfile
from pathlib import Path
import re

import pysd
from pysd.translators.xmile.xmile_file import XmileFile
from pysd.translators.xmile.xmile_element import (
    ControlElement,
    Aux,
    Stock,
    Flow,
)
from pysd.translators.structures.abstract_expressions import (
    ArithmeticStructure,
    ReferenceStructure,
)
import requests

from mira.metamodel import TemplateModel
from mira.sources.system_dynamics.pysd import (
    template_model_from_pysd_model,
)

PLACE_HOLDER_EQN = "<eqn>0</eqn>"


def process_file(fname):
    with open(fname) as f:
        xml_str = f.read()

    # commented out for current debugging
    # xml_str = xml_str.replace("\n","")

    # Conditional preprocessing
    eqn_tags = re.findall(r"<eqn>.*?</eqn>", xml_str, re.DOTALL)
    for tag in eqn_tags:
        if all(word in tag.lower() for word in ["if", "then", "else"]):
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)
        if all(word in tag.lower() for word in ["int", "mod"]):
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)
        if "sum" in tag.lower():
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)
        if "//" in tag.lower():
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)
        if "," in tag.lower():
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)
        if "init" in tag.lower():
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)
        if "nan" in tag.lower():
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)
        if "pi" in tag.lower():
            xml_str = xml_str.replace(tag, PLACE_HOLDER_EQN)

    # Comment preprocessing
    eqn_bracket_pattern = r"(<eqn>.*?)\{[^}]*\}(.*?</eqn>)"
    eqn_bracket_sub = r"\1" + r"\2"
    xml_str = re.sub(eqn_bracket_pattern, eqn_bracket_sub, xml_str)

    with open(fname, "w") as f:
        f.write(xml_str)

    return fname


def template_model_from_stella_model_file(fname) -> TemplateModel:
    """Return a template model from a local Stella model file.

    Parameters
    ----------
    fname : str or pathlib.Path
        The path to the local Stella model file

    Returns
    -------
    :
        A MIRA template model
    """

    process_file(fname)

    pysd_model = pysd.read_xmile(fname)
    stella_model_file = XmileFile(fname)
    stella_model_file.parse()

    expression_map = extract_stella_variable_expressions(stella_model_file)
    return template_model_from_pysd_model(pysd_model, expression_map)


def template_model_from_stella_model_url(url) -> TemplateModel:
    """Return a template model from a Stella model file provided by an url.

    Parameters
    ----------
    url : str
        The url to the Stella model file.

    Returns
    -------
    :
        A MIRA Template Model
    """

    file_extension = Path(url).suffix
    data = requests.get(url).content
    temp_file = tempfile.NamedTemporaryFile(
        mode="w+b", suffix=file_extension, delete=False
    )

    with temp_file as file:
        file.write(data)

    process_file(temp_file.name)
    pysd_model = pysd.read_xmile(temp_file.name)
    stella_model_file = XmileFile(temp_file.name)
    stella_model_file.parse()
    expression_map = extract_stella_variable_expressions(stella_model_file)

    return template_model_from_pysd_model(pysd_model, expression_map)


def extract_stella_variable_expressions(stella_model_file):
    """Method that extracts expressions for each variable in a Stella model

    Parameters
    ----------
    stella_model_file : XmileFile
        The XmileFile object

    Returns
    -------
    : dict[str,str]
        Mapping of variable name to string variable expression
    """
    expression_map = {}
    operand_operator_per_level_var_map = {}

    for component in stella_model_file.sections[0].components:
        if isinstance(component, ControlElement):
            continue
        # test to see if flow first as flow is a subclass or Aux
        elif isinstance(component, Flow):
            # TODO: test for call structure object
            operands = component.components[0][1].arguments
            # If the flow doesn't use operands (e.g. +,-) but actual functions (e.g. max,pulse)
            # assign the flow as None
            if not hasattr(component.components[0][1], "operators"):
                expression_map[component.name] = "xxplaceholderxx"
                continue
            operators = component.components[0][1].operators
            operand_operator_per_level_var_map[component.name] = {}
            extract_variables(
                operands,
                operators,
                component.name,
                operand_operator_per_level_var_map,
            )
        elif isinstance(component, Aux):
            # TODO: test for call structure object
            if not isinstance(component.components[0][1], ArithmeticStructure):
                expression_map[component.name] = parse_aux_structure(component)
                continue
            operands = component.components[0][1].arguments
            operators = component.components[0][1].operators
            operand_operator_per_level_var_map[component.name] = {}
            extract_variables(
                operands,
                operators,
                component.name,
                operand_operator_per_level_var_map,
            )

        elif isinstance(component, Stock):
            try:
                operand_operator_per_level_var_map[component.name] = {}
                operands = component.components[0][1].flow.arguments
                operators = component.components[0][1].flow.operators
                extract_variables(
                    operands,
                    operators,
                    component.name,
                    operand_operator_per_level_var_map,
                )
            # If the stock only has a reference and no operators in its expression
            except AttributeError:
                expression_map[component.name] = component.components[0][
                    1
                ].flow.reference
                operand_operator_per_level_var_map[component.name] = {}
                operand_operator_per_level_var_map[component.name][0] = {}
                operand_operator_per_level_var_map[component.name][0][
                    "operands"
                ] = [component.components[0][1].flow.reference]

    # construct the expression for each variable once its operators and operands are mapped
    for var_name, expr_level_dict in operand_operator_per_level_var_map.items():
        expression_map[var_name] = create_expression(expr_level_dict)
    return expression_map


def create_expression(expr_level_dict):
    """When a variable's operators and operands are mapped, construct the string expression.

    Parameters
    ----------
    expr_level_dict : dict[int,Any]
        The mapping of level to operands and operators present in a level of an expression
    Returns
    -------
    : str
        The string expression
    """
    str_expression = ""
    for level, ops in reversed(expr_level_dict.items()):
        operands = ops["operands"]
        operators = ops["operators"] if ops.get("operators") else []
        if not operators:
            level_expr = operands[0]
            str_expression += level_expr
            continue
        elif len(operands) > len(operators):
            level_expr = "("
            for idx, operand in enumerate(operands):
                try:
                    if operators[idx] != "negative":
                        if level == len(expr_level_dict) - 1:
                            level_expr += operand + operators[idx]
                        else:
                            level_expr += operators[idx] + operand
                    else:
                        level_expr += "-" + operand
                except IndexError:
                    level_expr += operands[len(operands) - 1]
            str_expression += level_expr + ")"
        elif len(operands) == len(operators):
            level_expr = ""
            for idx, operand in enumerate(operands):
                if operators[idx] != "negative":
                    if level == len(expr_level_dict) - 1:
                        level_expr = operand + operators[idx]
                    else:
                        level_expr = operators[idx] + operand
                else:
                    level_expr += "-" + operand
                str_expression += level_expr
    return str_expression


def extract_variables(
    operands, operators, name, operand_operator_per_level_var_map
):
    """Helper method to construct an expression for each variable in a Stella model

    Parameters
    ----------
    operands : list[ReferenceStructure,ArithmeticStructure]
        List of ReferenceStructure objects representing operands in an expression for a variable
    operators : list[str]
        List of operators in an expression for a variable
    name : str
        Name of the variable
    operand_operator_per_level_var_map : dict[str,Any]
        Mapping of variable name to operators and operands associated with the level they are
        encountered

    """
    operand_operator_per_level_var_map[name][0] = {}
    operand_operator_per_level_var_map[name][0]["operators"] = []
    operand_operator_per_level_var_map[name][0]["operands"] = []
    operand_operator_per_level_var_map[name][0]["operators"].extend(operators)
    for idx, operand in enumerate(operands):
        parse_structures(operand, 0, name, operand_operator_per_level_var_map)


def parse_structures(operand, idx, name, operand_operator_per_level_var_map):
    """Recursive helper method that retrieves each operand associated with a ReferenceStructure
    object and operators associated with an ArithmeticStructure object. ArithmeticStructures can
    contain ArithmeticStructure or ReferenceStructure Objects.

    Parameters
    ----------
    operand : ReferenceStructure or ArithmeticStructure
        The operand in an expression
    idx : int
        The level at which the operand is encountered in an expression (e.g. 5+(7-3). The
        operands 7 and 3 are considered as level 1 and 5 is considered as level 5).
    name : str
        The name of the variable
    operand_operator_per_level_var_map : dict[str,Any]
        Mapping of variable name to operators and operands associated with the level they are
        encountered
    """
    if operand_operator_per_level_var_map[name].get(idx) is None:
        operand_operator_per_level_var_map[name][idx] = {}
        operand_operator_per_level_var_map[name][idx]["operators"] = []
        operand_operator_per_level_var_map[name][idx]["operands"] = []

    # base case
    if isinstance(operand, ReferenceStructure):
        operand_operator_per_level_var_map[name][idx]["operands"].append(
            operand.reference
        )
        return
    elif isinstance(operand, ArithmeticStructure):
        for struct in operand.arguments:
            parse_structures(
                struct, idx + 1, name, operand_operator_per_level_var_map
            )
        operand_operator_per_level_var_map[name][idx + 1]["operators"].extend(
            operand.operators
        )

    # case where operand is just a primitive
    else:
        operand_operator_per_level_var_map[name][idx]["operands"].append(
            str(operand)
        )


def parse_aux_structure(structure):
    """If an Aux object's component method is not a reference structure, deconstruct the Aux object
    to retrieve the primitive value that the auxiliary represents.

    Parameters
    ----------
    structure : Aux
        The Aux object
    Returns
    -------

    """
    val = structure.components[0][1]
    while (
        not isinstance(val, float)
        and not isinstance(val, str)
        and not isinstance(val, int)
    ):
        if hasattr(val, "argument"):
            val = val.argument
        if isinstance(val, ReferenceStructure):
            val = val.reference
    return str(val)
