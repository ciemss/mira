"""This module implements an input processor for bilayer representations
of models based on mass-action kinetics."""
import json
from mira.metamodel.templates import *


def template_model_from_bilayer_file(fname) -> TemplateModel:
    """Return a TemplateModel by processing a bilayer JSON file.

    Parameters
    ----------
    fname : str
        The path to a bilayer JSON file.

    Returns
    -------
    :
        A TemplateModel extracted from the bilayer.
    """
    with open(fname, 'r') as fh:
        return template_model_from_bilayer(json.load(fname))


def template_model_from_bilayer(bilayer_json) -> TemplateModel:
    """Return a TemplateModel by processing a bilayer JSON file.

    Parameters
    ----------
    bilayer_json : dict
        A bilayer JSON structure.

    Returns
    -------
    :
        A TemplateModel extracted from the bilayer.
    """
    # For each box
    concepts = {idx + 1: Concept(name=q['variable'])
                for idx, q in enumerate(bilayer_json['Qin'])}
    boxes = [{'inputs': [], 'outputs': [], 'controllers': []}
             for _ in range(len(bilayer_json['Box']))]
    for consumption in bilayer_json['Wn']:
        boxes[consumption['efflux'] - 1]['inputs'].append(
            concepts[consumption['effusion']])
    for production in bilayer_json['Wa']:
        boxes[production['influx'] - 1]['outputs'].append(
            concepts[production['infusion']])
    for control in bilayer_json['Win']:
        if concepts[control['arg']] not in boxes[control['call'] - 1]['inputs']:
            boxes[control['call'] - 1]['controllers'].append(
                concepts[control['arg']])

    templates = []
    for box in boxes:
        templates.append(box_to_template(box))
    return TemplateModel(templates=templates)


def box_to_template(box):
    """Return a Template from a bilayer box by recognizing its topology."""
    # Assert assumptions in template patterns
    assert len(box['inputs']) <= 1
    assert len(box['outputs']) <= 1
    # Unpack inputs and outputs
    input = box['inputs'][0] if box['inputs'] else None
    output = box['outputs'][0] if box['outputs'] else None
    # Decide on template class based on number of controllers
    if not box['controllers']:
        if not input:
            return NaturalProduction(outcome=output)
        elif not output:
            return NaturalDegradation(subject=input)
        else:
            return NaturalConversion(subject=input, outcome=output)
    elif len(box['controllers']) == 1:
        return ControlledConversion(controller=box['controllers'][0],
                                    subject=input, outcome=output)
    else:
        return GroupedControlledConversion(controllers=box['controllers'],
                                           subject=input, outcome=output)