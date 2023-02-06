"""Tests for the metamodel."""

import json
import unittest

from mira.metamodel import (
    Concept, ControlledConversion, NaturalConversion, NaturalProduction, NaturalDegradation,
    GroupedControlledConversion, SCHEMA_PATH, get_json_schema
)


class TestMetaModel(unittest.TestCase):
    """A test case for the metamodel."""
    # Set to None for full diff, remove to have default diff
    # https://docs.python.org/3/library/unittest.html#unittest.TestCase.maxDiff
    maxDiff = None

    def setUp(self) -> None:
        """Initialize the test case with shared concepts."""
        self.susceptible = Concept(name="susceptible population", identifiers={"ido": "0000514"})
        self.exposed = Concept(name="exposed", identifiers={"ido": "0000597"})
        self.infected = Concept(name="infected population", identifiers={"ido": "0000511"})
        self.asymptomatic = Concept(name="asymptomatic infected population", identifiers={"ido": "0000511"})
        self.immune = Concept(name="immune population", identifiers={"ido": "0000592"})


    def test_schema(self):
        """Test that the schema is up to date."""
        self.assertTrue(SCHEMA_PATH.is_file())
        self.assertEqual(
            get_json_schema(),
            json.loads(SCHEMA_PATH.read_text()),
            msg="Regenerate an updated JSON schema by running `python -m mira.metamodel.templates`",
        )

    def test_controlled_conversion(self):
        """Test instantiating the controlled conversion."""
        t1 = ControlledConversion(
            controller=self.immune,
            subject=self.susceptible,
            outcome=self.infected,
        )
        self.assertEqual(self.infected, t1.outcome)
        self.assertEqual(self.susceptible, t1.subject)
        self.assertEqual(self.immune, t1.controller)

    def test_natural_conversion(self):
        """Test natural conversions."""
        template = NaturalConversion(subject=self.exposed, outcome=self.infected)
        self.assertEqual(self.infected, template.outcome)
        self.assertEqual(self.exposed, template.subject)

    def test_group_controlled(self):
        """Test natural conversions."""
        t1 = GroupedControlledConversion(subject=self.susceptible, outcome=self.exposed,
                                         controllers=[self.infected, self.asymptomatic])
        self.assertEqual(self.exposed, t1.outcome)
        self.assertEqual(self.susceptible, t1.subject)
        self.assertIn(self.infected, t1.controllers)
        self.assertIn(self.asymptomatic, t1.controllers)

    def test_natural_degradation(self):
        t = NaturalDegradation(subject=self.infected)
        self.assertEqual(self.infected, t.subject)

    def test_natural_production(self):
        t = NaturalProduction(outcome=self.susceptible)
        self.assertEqual(self.susceptible, t.outcome)

