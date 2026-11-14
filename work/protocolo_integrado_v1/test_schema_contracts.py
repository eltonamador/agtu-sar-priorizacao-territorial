from __future__ import annotations

import copy
import json
import math
import re
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import integrated_protocol as module
from test_integrated_protocol import draft_case, draft_event, valid_loc_result


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "outputs" / "protocolo_integrado_v1"


def _same_json(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def _resolve_ref(root: Mapping[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise AssertionError(f"Referência externa não suportada no teste: {reference}")
    current: Any = root
    for part in reference[2:].split("/"):
        current = current[part.replace("~1", "/").replace("~0", "~")]
    return current


def schema_errors(instance: Any, schema: Any, root: Mapping[str, Any], path: str = "$") -> list[str]:
    if schema is False:
        return [f"{path}: schema false"]
    if schema is True:
        return []
    if "$ref" in schema:
        return schema_errors(instance, _resolve_ref(root, schema["$ref"]), root, path)

    errors: list[str] = []
    for subschema in schema.get("allOf", []):
        errors.extend(schema_errors(instance, subschema, root, path))
    if "anyOf" in schema and not any(
        not schema_errors(instance, option, root, path) for option in schema["anyOf"]
    ):
        errors.append(f"{path}: nenhum anyOf aceitou")
    if "oneOf" in schema:
        matches = sum(
            not schema_errors(instance, option, root, path) for option in schema["oneOf"]
        )
        if matches != 1:
            errors.append(f"{path}: oneOf teve {matches} correspondências")
    if "if" in schema:
        branch = "then" if not schema_errors(instance, schema["if"], root, path) else "else"
        if branch in schema:
            errors.extend(schema_errors(instance, schema[branch], root, path))

    if "const" in schema and not _same_json(instance, schema["const"]):
        errors.append(f"{path}: const divergente")
    if "enum" in schema and not any(_same_json(instance, item) for item in schema["enum"]):
        errors.append(f"{path}: fora do enum")

    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = [expected_type] if isinstance(expected_type, str) else expected_type
        checks = {
            "null": lambda value: value is None,
            "boolean": lambda value: isinstance(value, bool),
            "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value)),
            "string": lambda value: isinstance(value, str),
            "array": lambda value: isinstance(value, list),
            "object": lambda value: isinstance(value, Mapping),
        }
        if not any(checks[name](instance) for name in expected_types):
            return errors + [f"{path}: tipo inválido"]

    if isinstance(instance, Mapping):
        required = set(schema.get("required", []))
        missing = sorted(required - set(instance))
        if missing:
            errors.append(f"{path}: ausentes={missing}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                errors.extend(schema_errors(value, properties[key], root, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: propriedade adicional")
            elif isinstance(schema.get("additionalProperties"), Mapping):
                errors.extend(
                    schema_errors(value, schema["additionalProperties"], root, f"{path}.{key}")
                )

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: minItems")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: maxItems")
        if schema.get("uniqueItems"):
            canonical = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in instance]
            if len(canonical) != len(set(canonical)):
                errors.append(f"{path}: itens duplicados")
        prefix = schema.get("prefixItems", [])
        for index, subschema in enumerate(prefix[: len(instance)]):
            errors.extend(schema_errors(instance[index], subschema, root, f"{path}[{index}]"))
        items = schema.get("items")
        start = len(prefix) if prefix else 0
        if items is False and len(instance) > start:
            errors.append(f"{path}: itens adicionais")
        elif isinstance(items, Mapping):
            for index in range(start, len(instance)):
                errors.extend(schema_errors(instance[index], items, root, f"{path}[{index}]"))

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: minLength")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: maxLength")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{path}: pattern")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(instance.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    raise ValueError
            except ValueError:
                errors.append(f"{path}: date-time")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: maximum")
    return errors


class SchemaContractParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case_schema = json.loads(
            (SCHEMA_DIR / "entrada_integrada_v1.schema.json").read_text(encoding="utf-8")
        )
        cls.event_schema = json.loads(
            (SCHEMA_DIR / "evento_busca_v1.schema.json").read_text(encoding="utf-8")
        )
        cls.loc_schema = json.loads(
            (SCHEMA_DIR / "loc_result_v1.schema.json").read_text(encoding="utf-8")
        )

    def assert_schema_accepts(self, instance: Any, schema: Mapping[str, Any]) -> None:
        self.assertEqual(schema_errors(instance, schema, schema), [])

    def assert_schema_rejects(self, instance: Any, schema: Mapping[str, Any]) -> None:
        self.assertTrue(schema_errors(instance, schema, schema))

    def test_runtime_valid_artifacts_also_match_published_schemas(self) -> None:
        case = module.prepare_frozen_case(
            draft_case(), "2026-10-21T10:00:00-03:00"
        )
        event = module.prepare_frozen_event(
            draft_event(), "2026-10-21T11:20:00-03:00"
        )
        loc_result = valid_loc_result(draft_case())
        self.assert_schema_accepts(case, self.case_schema)
        self.assert_schema_accepts(event, self.event_schema)
        self.assert_schema_accepts(loc_result, self.loc_schema)

    def test_retired_case_source_field_is_rejected_by_runtime_and_schema(self) -> None:
        value = draft_case()
        value["source_artifacts"]["spatial_review_sha256"] = value[
            "source_artifacts"
        ].pop("spatial_review_manifest_sha256")
        with self.assertRaises(module.InputValidationError):
            module.validate_case(value)
        self.assert_schema_rejects(value, self.case_schema)

    def test_retired_loc_profile_results_field_is_rejected_by_schema(self) -> None:
        value = valid_loc_result(draft_case())
        value["profile_results"] = value.pop("profile_runs")
        self.assert_schema_rejects(value, self.loc_schema)

    def test_profile_run_requires_pre_ranking_case_binding(self) -> None:
        value = valid_loc_result(draft_case())
        del value["profile_runs"][0]["profile_input"]["source_loc_input_sha256"]
        self.assert_schema_rejects(value, self.loc_schema)


if __name__ == "__main__":
    unittest.main()
