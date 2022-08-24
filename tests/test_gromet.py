from mira.modeling.gromet_model import GroMEtModel, \
    model_to_gromet_json_file, model_to_gromet
from mira.metamodel import ControlledConversion, Concept, NaturalConversion
from mira.modeling import Model, TemplateModel


def _get_sir_model_templ():
    infected = Concept(name="infected population", identifiers={"ido": "0000511"})
    susceptible = Concept(name="susceptible population", identifiers={"ido": "0000514"})
    immune = Concept(name="immune population", identifiers={"ido": "0000592"})

    t1 = ControlledConversion(
        controller=infected,
        subject=susceptible,
        outcome=infected,
    )
    t2 = NaturalConversion(subject=infected, outcome=immune)
    sir_model_templ = TemplateModel(templates=[t1, t2])
    return sir_model_templ


def test_init():
    # Sanity check to see that the class can be instantiated
    sir_model_templ = _get_sir_model_templ()
    sir_model = Model(sir_model_templ)
    gromet_model = GroMEtModel(sir_model, "sir_model", "PetriNet")


def test_gromet_as_dict():
    sir_model_templ = _get_sir_model_templ()
    sir_model = Model(sir_model_templ)

    name = "sir_model"
    model_name = "PetriNet"

    gromet = model_to_gromet(sir_model, name=name, model_name=model_name)

    from dataclasses import asdict
    gromet_dict = asdict(gromet)


def test_gromet_json_conversion():
    """Test model_to_gromet_json_file and gromet_json_file_to_model"""
    from pathlib import Path
    sir_model_templ = _get_sir_model_templ()
    sir_model = Model(sir_model_templ)

    # Gromet json file
    fname = "sir_model_test.json"
    name = "sir_model"
    model_name = "PetriNet"
    model_to_gromet_json_file(
        model=sir_model, fname=fname, name=name, model_name=model_name
    )
    assert Path(fname).exists()
    assert Path(fname).stat().st_size > 0
