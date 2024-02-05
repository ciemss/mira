import requests
from pathlib import Path

import sympy

from mira.sources.system_dynamics.vensim import *
from mira.sources.system_dynamics.stella import *
from mira.modeling.amr.stockflow import template_model_to_stockflow_json
from mira.metamodel import *
from mira.modeling import Model
from mira.metamodel.utils import safe_parse_expr

MDL_SIR_URL = "https://raw.githubusercontent.com/SDXorg/test-models/master/samples/SIR/SIR.mdl"
MDL_LOTKA_URL = (
    "https://raw.githubusercontent.com/SDXorg/test-models/master/samples/Lotka_"
    "Volterra/Lotka_Volterra.mdl"
)
MDL_TEA_URL = "https://raw.githubusercontent.com/SDXorg/test-models/master/samples/teacup/teacup.mdl"

XMILE_SIR_URL = "https://raw.githubusercontent.com/SDXorg/test-models/master/samples/SIR/SIR.xmile"
XMILE_TEA_URL = "https://raw.githubusercontent.com/SDXorg/test-models/master/samples/teacup/teacup.xmile"

HERE = Path(__file__).parent
MDL_SIR_PATH = HERE / "SIR.mdl"
XMILE_SIR_PATH = HERE / "SIR.xmile"


def test_vensim_file():
    data = requests.get(MDL_SIR_URL).content
    with open(MDL_SIR_PATH, "wb") as file:
        file.write(data)
    tm = template_model_from_mdl_file(MDL_SIR_PATH)
    sir_tm_test(tm)


def test_vensim_url():
    tm = template_model_from_mdl_url(MDL_SIR_URL)
    sir_tm_test(tm)


def test_vensim_lotka_url():
    tm = template_model_from_mdl_url(MDL_LOTKA_URL)


def test_stella_file():
    data = requests.get(XMILE_SIR_URL).content
    with open(XMILE_SIR_PATH, "wb") as file:
        file.write(data)
    tm = template_model_from_stella_model_file(XMILE_SIR_PATH)
    sir_tm_test(tm)


def test_stella_url():
    tm = template_model_from_stella_model_url(XMILE_SIR_URL)
    sir_tm_test(tm)


def test_end_to_end_sir_vensim():
    tm = template_model_from_mdl_url(MDL_SIR_URL)
    model = Model(tm)
    amr = template_model_to_stockflow_json(tm)
    sir_end_to_end_test(model, amr)


def test_end_to_end_sir_stella():
    tm = template_model_from_stella_model_url(XMILE_SIR_URL)
    model = Model(tm)
    amr = template_model_to_stockflow_json(tm)
    sir_end_to_end_test(model, amr)


def test_end_to_end_tea_vensim():
    tm = template_model_from_mdl_url(MDL_TEA_URL)
    model = Model(tm)
    amr = template_model_to_stockflow_json(tm)
    tea_end_to_end_test(model, amr)


def test_end_to_end_tea_stella():
    tm = template_model_from_stella_model_url(XMILE_TEA_URL)
    model = Model(tm)
    amr = template_model_to_stockflow_json(tm)
    tea_end_to_end_test(model, amr)


def sir_tm_test(tm):
    assert len(tm.templates) == 2
    assert len(tm.parameters) == 3
    assert len(tm.initials) == 3

    assert isinstance(tm.templates[0], NaturalConversion)
    assert isinstance(tm.templates[1], ControlledConversion)

    assert "susceptible" in tm.initials
    assert "infectious" in tm.initials
    assert "recovered" in tm.initials
    assert tm.initials["susceptible"].expression == SympyExprStr(
        sympy.Float(1000)
    )
    assert tm.initials["infectious"].expression == SympyExprStr(sympy.Float(5))
    assert tm.initials["recovered"].expression == SympyExprStr(sympy.Float(0))

    assert "contact_infectivity" in tm.parameters
    assert "duration" in tm.parameters
    assert "total_population" in tm.parameters
    assert tm.parameters["contact_infectivity"].value == 0.3
    assert tm.parameters["duration"].value == 5.0
    assert tm.parameters["total_population"].value == 1000

    assert tm.templates[0].subject.name == "infectious"
    assert tm.templates[0].outcome.name == "recovered"

    assert tm.templates[1].subject.name == "susceptible"
    assert tm.templates[1].outcome.name == "infectious"
    assert tm.templates[1].controller.name == "infectious"


def sir_end_to_end_test(model, amr):
    assert len(model.transitions) == 2
    assert len(model.variables) == 3
    assert len(model.parameters) - 1 == 3
    assert "infectious" in model.variables
    assert "recovered" in model.variables
    assert "susceptible" in model.variables
    assert "duration" in model.parameters
    assert "contact_infectivity" in model.parameters
    assert "total_population" in model.parameters

    amr_model = amr["model"]
    amr_semantics_ode = amr["semantics"]["ode"]
    assert len(amr_model["flows"]) == 2
    assert len(amr_model["stocks"]) == 3
    assert len(amr_model["auxiliaries"]) == 3
    assert len(amr_model["links"]) == 6
    assert len(amr_semantics_ode["parameters"]) == 3
    assert len(amr_semantics_ode["initials"]) == 3

    assert amr_model["flows"][0]["upstream_stock"] == "infectious"
    assert amr_model["flows"][0]["downstream_stock"] == "recovered"
    assert amr_model["flows"][0]["name"] == "recovering"
    assert amr_model["flows"][1]["upstream_stock"] == "susceptible"
    assert amr_model["flows"][1]["downstream_stock"] == "infectious"
    assert amr_model["flows"][1]["name"] == "succumbing"

    assert safe_parse_expr(
        amr_model["flows"][0]["rate_expression"]
    ) == safe_parse_expr("infectious/duration")
    assert safe_parse_expr(
        amr_model["flows"][1]["rate_expression"]
    ) == safe_parse_expr(
        "infectious*susceptible*contact_infectivity/total_population"
    )

    assert amr_model["stocks"][0]["name"] == "infectious"
    assert amr_model["stocks"][1]["name"] == "recovered"
    assert amr_model["stocks"][2]["name"] == "susceptible"

    assert amr_model["auxiliaries"][0]["name"] == "duration"
    assert amr_model["auxiliaries"][1]["name"] == "contact_infectivity"
    assert amr_model["auxiliaries"][2]["name"] == "total_population"

    assert amr_semantics_ode["parameters"][0]["id"] == "duration"
    assert amr_semantics_ode["parameters"][0]["value"] == 5.0
    assert amr_semantics_ode["parameters"][1]["id"] == "contact_infectivity"
    assert amr_semantics_ode["parameters"][1]["value"] == 0.3
    assert amr_semantics_ode["parameters"][2]["id"] == "total_population"
    assert amr_semantics_ode["parameters"][2]["value"] == 1000.0

    assert amr_semantics_ode["initials"][0]["target"] == "infectious"
    assert float(amr_semantics_ode["initials"][0]["expression"]) == 5.0
    assert amr_semantics_ode["initials"][1]["target"] == "recovered"
    assert float(amr_semantics_ode["initials"][1]["expression"]) == 0.0
    assert amr_semantics_ode["initials"][2]["target"] == "susceptible"
    assert float(amr_semantics_ode["initials"][2]["expression"]) == 1000.0


def tea_end_to_end_test(model, amr):
    assert len(model.transitions) == 1
    assert len(model.variables) == 1
    assert len(model.parameters) - 1 == 2
    assert "teacup_temperature" in model.variables
    assert "characteristic_time" in model.parameters
    assert "room_temperature" in model.parameters

    amr_model = amr["model"]
    amr_semantics_ode = amr["semantics"]["ode"]
    assert len(amr_model["flows"]) == 1
    assert len(amr_model["stocks"]) == 1
    assert len(amr_model["auxiliaries"]) == 2
    assert len(amr_model["links"]) == 3
    assert len(amr_semantics_ode["parameters"]) == 2
    assert len(amr_semantics_ode["initials"]) == 1

    assert amr_model["flows"][0]["upstream_stock"] == "teacup_temperature"
    assert amr_model["flows"][0]["downstream_stock"] is None
    assert amr_model["flows"][0]["name"] == "heat_loss_to_room"

    assert safe_parse_expr(
        amr_model["flows"][0]["rate_expression"]
    ) == safe_parse_expr(
        "(teacup_temperature - room_temperature)/characteristic_time"
    )

    assert amr_model["stocks"][0]["name"] == "teacup_temperature"

    assert amr_model["auxiliaries"][0]["name"] == "characteristic_time"
    assert amr_model["auxiliaries"][1]["name"] == "room_temperature"

    assert amr_semantics_ode["parameters"][0]["id"] == "characteristic_time"
    assert amr_semantics_ode["parameters"][0]["value"] == 10.0
    assert amr_semantics_ode["parameters"][1]["id"] == "room_temperature"
    assert amr_semantics_ode["parameters"][1]["value"] == 70.0
    assert amr_semantics_ode["initials"][0]["target"] == "teacup_temperature"
    assert float(amr_semantics_ode["initials"][0]["expression"]) == 180.0
