"""No-dependency regressions for the experimental native driver transport."""

import unittest

from native_model import definition_commands


class EncodingTests(unittest.TestCase):
    def test_source_map_and_final_constraint_are_encoded(self):
        spec = {
            "nodes": [
                {"name": "items", "op": "source", "width": 2},
                {
                    "name": "remaining",
                    "op": "map",
                    "input": "items",
                    "exprs": [["c0"], [10, "c1", "-"]],
                },
                {
                    "name": "bad",
                    "op": "filter",
                    "input": "remaining",
                    "column": 1,
                    "cmp": "lt",
                    "value": 0,
                },
            ],
            "required_empty": ["bad"],
        }
        self.assertEqual(
            definition_commands(spec),
            [
                "DEF source items 2",
                "DEF map remaining items 2 1 c0 3 10 c1 -",
                "DEF filter bad remaining 1 lt 0",
                "SEAL 1 bad",
            ],
        )

    def test_protocol_tokens_cannot_inject_commands(self):
        for node in [
            {"name": "x\nBEGIN", "op": "source", "width": 1},
            {"name": "x", "op": "source", "width": True},
            {"name": "x", "op": "map", "input": "a", "exprs": [["c0\nCOMMIT"]]},
        ]:
            with self.assertRaises(ValueError):
                definition_commands({"nodes": [node]})

    def test_definition_limit_is_checked_before_transport(self):
        with self.assertRaisesRegex(ValueError, "too many"):
            definition_commands({"nodes": [{"name": "x", "op": "source", "width": 1}] * 4097})


if __name__ == "__main__":
    unittest.main()
