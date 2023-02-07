"""This module implements generation into Petri net models which are defined
through a set of states, transitions, and the input and output connections
between them.

Once the model is created, it can be exported into JSON following the
conventions in https://github.com/AlgebraicJulia/ASKEM-demos/tree/master/data.
"""

__all__ = ["PetriNetModel"]

import json
from typing import List, Optional

from pydantic import BaseModel, Field
from sympy.printing.mathml import mathml

from . import Model


class State(BaseModel):
    sname: str
    mira_ids: str
    mira_context: str
    mira_initial_value: Optional[float]


class Transition(BaseModel):
    tname: str
    template_type: str
    parameter_name: Optional[str]
    parameter_value: Optional[str]
    parameters: Optional[str]


class Input(BaseModel):
    source: int = Field(alias="is")
    transition: int = Field(alias="it")


class Output(BaseModel):
    source: int = Field(alias="os")
    transition: int = Field(alias="ot")


class PetriNetResponse(BaseModel):
    S: List[State] = Field(..., description="A list of states")
    T: List[Transition] = Field(..., description="A list of transitions")
    I: List[Input] = Field(..., description="A list of inputs")
    O: List[Output] = Field(..., description="A list of outputs")


class PetriNetModel:
    """A class representing a PetriNet model."""

    def __init__(self, model: Model):
        """Instantiate a petri net model from a generic transition model.

        Parameters
        ----------
        model:
            The pre-compiled transition model
        """
        self.states = []
        self.transitions = []
        self.inputs = []
        self.outputs = []
        self.vmap = {variable.key: (idx + 1) for idx, variable
                     in enumerate(model.variables.values())}
        for key, var in model.variables.items():
            # Use the variable's concept name if possible but fall back
            # on the key otherwise
            name = var.data.get('name') or str(key)
            ids = str(var.data.get('identifiers', '')) or None
            context = str(var.data.get('context', '')) or None
            state_data = {
                'sname': name,
                'mira_ids': ids,
                'mira_context': context,
                'mira_concept': var.concept.json(),
            }
            initial = var.data.get('initial_value')
            if initial is not None:
                state_data['mira_initial_value'] = initial
            self.states.append(state_data)

        for idx, transition in enumerate(model.transitions.values()):
            # NOTE: this is a bit hacky. It attempts to determine
            # if the parameter was generated automatically
            if not isinstance(transition.rate.key, str):
                pname = f"p_petri_{idx + 1}"
            else:
                pname = transition.rate.key
                pname = sanitize_parameter_name(pname)

            transition_dict = {
                'tname': f"t{idx + 1}",
                'template_type': transition.template_type,
                'parameter_name': pname,
                'parameter_value': transition.rate.value,
                "mira_template": transition.template.json(),
            }

            # Include rate law
            if transition.template.rate_law:
                rate_law = transition.template.rate_law.args[0]
                transition_dict.update(
                    mira_rate_law=str(rate_law),
                    mira_rate_law_mathml=mathml(rate_law),
                )

                # Include all parameters relevant for the transition.
                # Even though this is a bit redundant, it makes it much
                # more accessible for downstream users.
                _parameters = {}
                for parameter_name in transition.template.get_parameter_names():
                    p = model.parameters.get(parameter_name)
                    if p is None:
                        continue
                    key = sanitize_parameter_name(p.key) if p.key else f"p_petri_{idx + 1}"
                    _parameters[key] = p.value
                transition_dict["mira_parameters"] = json.dumps(_parameters,
                                                                sort_keys=True)

            self.transitions.append(transition_dict)
            for c in transition.control:
                self.inputs.append({'is': self.vmap[c.key],
                                    'it': idx + 1})
                self.outputs.append({'os': self.vmap[c.key],
                                     'ot': idx + 1})
            for c in transition.consumed:
                self.inputs.append({'is': self.vmap[c.key],
                                    'it': idx + 1})
            for p in transition.produced:
                self.outputs.append({'os': self.vmap[p.key],
                                     'ot': idx + 1})

    def to_json(self):
        """Return a JSON dict structure of the Petri net model."""
        return {
            'S': self.states,
            'T': self.transitions,
            'I': self.inputs,
            'O': self.outputs
        }

    def to_pydantic(self):
        return PetriNetResponse(**self.to_json())

    def to_json_str(self):
        """Return a JSON string representation of the Petri net model."""
        return json.dumps(self.to_json())

    def to_json_file(self, fname, **kwargs):
        """Write the Petri net model to a JSON file."""
        js = self.to_json()
        with open(fname, 'w') as fh:
            json.dump(js, fh, **kwargs)


def sanitize_parameter_name(pname):
    # This is to revert a sympy representation issue
    return pname.replace('XXlambdaXX', 'lambda')
