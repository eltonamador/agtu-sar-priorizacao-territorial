#!/usr/bin/env python3
"""Testes independentes do avaliador pós-abertura RURAL-01 T4.5–T6.

Todos os pontos usados aqui são construídos sinteticamente a partir do centro
técnico congelado. A suíte não contém nem tenta descobrir a posição reservada
do alvo simulado.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "evaluate_rural01_reference.py"
SPEC = importlib.util.spec_from_file_location("evaluate_rural01_reference", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Falha ao carregar o avaliador: {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ROOT = HERE.parents[1]
T4_DIR = ROOT / "outputs/campo_rural01/processamento_movimento_cego_v2"
V1_DIR = ROOT / "outputs/campo_rural01/processamento_cego_v1"
T4_LEDGER = T4_DIR / "ledger_congelamento_T4_mov_v2.json"
V1_MANIFEST = V1_DIR / "manifesto_processamento_cego.json"
SECTORS = V1_DIR / "setores_rural01.geojson"

LAT0 = 0.188611
LON0 = -51.155556
SYNTHETIC_X_M = 600.0
SYNTHETIC_Y_M = 300.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(paths: list[Path]) -> dict[str, str]:
    return {str(path): _sha256(path) for path in paths}


def _find_value(value: Any, key: str) -> list[Any]:
    """Coleta ocorrências de uma chave em um resultado JSON aninhado."""
    found: list[Any] = []
    if isinstance(value, Mapping):
        for item_key, item in value.items():
            if item_key == key:
                found.append(item)
            found.extend(_find_value(item, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_find_value(item, key))
    return found


def _assert_rejected(
    case: unittest.TestCase,
    call: Callable[[], Any],
    *,
    expected_fragments: tuple[str, ...] = (),
) -> None:
    """Aceita exceção de contrato ou retorno explícito de falha/não avaliável."""
    try:
        result = call()
    except Exception as exc:  # o tipo concreto pertence ao contrato do avaliador
        text = str(exc).casefold()
        if expected_fragments:
            case.assertTrue(
                any(fragment.casefold() in text for fragment in expected_fragments),
                f"Erro não explica a rejeição esperada: {exc}",
            )
        return
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True).casefold()
    case.assertTrue(
        any(token in serialized for token in ("fail", "erro", "diverg", "ausente", "nao_avaliavel", "inválid", "invalido")),
        f"Entrada inválida não foi rejeitada: {result!r}",
    )


def _synthetic_reference(**overrides: Any) -> dict[str, Any]:
    """Registro mínimo e deliberadamente sintético para testes."""
    lat, lon = MODULE.aeqd_inverse(SYNTHETIC_X_M, SYNTHETIC_Y_M, LAT0, LON0)
    lat = overrides.pop("latitude", lat)
    lon = overrides.pop("longitude", lon)
    reference: dict[str, Any] = {
        "$schema": "schema_referencia_t5_v1.json",
        "schema_version": "1.0",
        "record_id": "RURAL-01-T5-SYNTHETIC-UNIT-TEST-ONLY",
        "scenario_id": "RURAL-01",
        "stage": "T5_REFERENCE_OPENING",
        "status": "REVELADO_CONGELADO",
        "reference_received": True,
        "reference_role": "POSICAO_DECLARADA_ALVO_SIMULADO",
        "verification_status": "DECLARADA_NAO_AFERIDA_INDEPENDENTEMENTE",
        "position": {
            "latitude": lat,
            "longitude": lon,
            "crs": "EPSG:4326",
            "coordinate_order": "LONGITUDE_LATITUDE",
        },
        "source": {
            "collection_method": None,
            "equipment": None,
            "horizontal_accuracy_m": None,
            "position_observed_at": None,
            "source_artifact": None,
            "source_artifact_sha256": None,
            "provenance_note": "COORDENADA_SINTETICA_EXCLUSIVA_PARA_TESTE",
        },
        "opening": {
            "opened_at": "2099-01-01T12:00:00-03:00",
            "opened_by": "TESTE_AUTOMATIZADO",
            "opening_method": "REGISTRO_SINTETICO_DE_TESTE",
            "evaluator_freeze_manifest_sha256": "0" * 64,
        },
        "missing_fields": [
            "collection_method",
            "equipment",
            "horizontal_accuracy_m",
            "position_observed_at",
            "source_artifact",
            "source_artifact_sha256",
        ],
        "notes": "Não corresponde à posição real ou declarada do caso.",
    }
    reference.update(overrides)
    return reference


class ProjectionAndDomainTests(unittest.TestCase):
    def test_aeqd_roundtrip_at_center_and_offsets(self) -> None:
        for x_m, y_m in ((0.0, 0.0), (600.0, 300.0), (-1200.0, 50.0), (0.0, -1499.0)):
            lat, lon = MODULE.aeqd_inverse(x_m, y_m, LAT0, LON0)
            restored_x, restored_y = MODULE.aeqd_forward(lat, lon, LAT0, LON0)
            self.assertAlmostEqual(restored_x, x_m, places=6)
            self.assertAlmostEqual(restored_y, y_m, places=6)

    def test_domain_inside_exact_boundary_and_outside(self) -> None:
        interior = MODULE.classify_domain(1499.94, 0.0)
        lower_edge = MODULE.classify_domain(1499.95, 0.0)
        exact = MODULE.classify_domain(1500.0, 0.0)
        upper_edge = MODULE.classify_domain(1500.05, 0.0)
        exterior = MODULE.classify_domain(1500.051, 0.0)
        self.assertEqual(interior["status"], "INTERIOR")
        self.assertEqual(lower_edge["status"], "BORDA")
        self.assertEqual(exact["status"], "BORDA")
        self.assertEqual(upper_edge["status"], "BORDA")
        self.assertEqual(exterior["status"], "EXTERIOR")
        self.assertFalse(exterior["inside_evaluation_domain"])


class SectorAndGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with SECTORS.open("r", encoding="utf-8") as handle:
            cls.features = json.load(handle)["features"]

    def test_radial_and_angular_boundary_returns_all_and_worst_v1_rank(self) -> None:
        radius_m = 1500.0 * math.sqrt(1.0 / 3.0)
        bearing_rad = math.radians(22.5)
        x_m = radius_m * math.sin(bearing_rad)
        y_m = radius_m * math.cos(bearing_rad)
        result = MODULE.match_sectors(x_m, y_m, self.features)
        self.assertTrue(result["boundary_case"])
        self.assertGreaterEqual(len(result["matched_sector_ids"]), 4)
        matched_ranks = [
            int(feature["properties"]["rank_base_within_buffer"])
            for feature in self.features
            if feature["properties"]["sector_id"] in result["matched_sector_ids"]
        ]
        self.assertEqual(result["primary_v1_rank_worst"], max(matched_ranks))
        expected_id = sorted(
            feature["properties"]["sector_id"]
            for feature in self.features
            if feature["properties"]["sector_id"] in result["matched_sector_ids"]
            and int(feature["properties"]["rank_base_within_buffer"]) == max(matched_ranks)
        )[0]
        self.assertEqual(result["primary_sector_id_v1_worst"], expected_id)

    def test_nearest_cell_tie_is_lexicographic(self) -> None:
        rows = [
            {"cell_id": "CELL-B", "row": 0, "col": 1, "x_m": -1.0, "y_m": 0.0},
            {"cell_id": "CELL-A", "row": 0, "col": 0, "x_m": 1.0, "y_m": 0.0},
        ]
        result = MODULE.nearest_grid_cell(0.0, 0.0, rows, max_distance_m=10.0)
        self.assertEqual(result["status"], "CELULA_ASSOCIADA")
        self.assertEqual(result["cell"]["cell_id"], "CELL-A")
        self.assertAlmostEqual(result["snap_distance_m"], 1.0)

    def test_grid_support_boundary_and_outside_have_no_fabricated_snap(self) -> None:
        rows = [{"cell_id": "CELL-A", "row": 0, "col": 0, "x_m": 0.0, "y_m": 0.0}]
        at_limit = MODULE.nearest_grid_cell(MODULE.GRID_MAX_SNAP_M, 0.0, rows)
        numerical_edge = MODULE.nearest_grid_cell(
            MODULE.GRID_MAX_SNAP_M + MODULE.DOMAIN_TOLERANCE_M,
            0.0,
            rows,
        )
        outside = MODULE.nearest_grid_cell(
            MODULE.GRID_MAX_SNAP_M + MODULE.DOMAIN_TOLERANCE_M + 0.001,
            0.0,
            rows,
        )
        self.assertEqual(at_limit["status"], "CELULA_ASSOCIADA")
        self.assertEqual(numerical_edge["status"], "CELULA_ASSOCIADA")
        self.assertEqual(outside["status"], "SEM_CELULA_NO_SUPORTE_DISCRETO")
        self.assertIsNone(outside["cell"])


class CostAndCorridorTests(unittest.TestCase):
    def test_inclusive_ecdf_preserves_ties(self) -> None:
        population = [1.0, 2.0, 2.0, 4.0]
        self.assertEqual(MODULE.inclusive_ecdf_percentile(0.0, population), 0.0)
        self.assertEqual(MODULE.inclusive_ecdf_percentile(1.0, population), 25.0)
        self.assertEqual(MODULE.inclusive_ecdf_percentile(2.0, population), 75.0)
        self.assertEqual(MODULE.inclusive_ecdf_percentile(4.0, population), 100.0)

    def test_cost_bands_use_frozen_inclusive_upper_limits(self) -> None:
        cases = {
            0.0: "B1_ATE_UM_TERCO",
            500.0: "B1_ATE_UM_TERCO",
            500.000001: "B2_ENTRE_UM_E_DOIS_TERCOS",
            1000.0: "B2_ENTRE_UM_E_DOIS_TERCOS",
            1000.000001: "B3_ENTRE_DOIS_TERCOS_E_ORCAMENTO",
            1500.0: "B3_ENTRE_DOIS_TERCOS_E_ORCAMENTO",
            1500.000001: "B4_ACIMA_DO_ORCAMENTO",
        }
        for cost, expected in cases.items():
            with self.subTest(cost=cost):
                self.assertEqual(MODULE.cost_band(cost), expected)
        self.assertEqual(MODULE.cost_band(None), "NAO_DISPONIVEL")
        self.assertEqual(MODULE.cost_band(float("inf")), "NAO_DISPONIVEL")

    def test_linestring_distance_and_frozen_support_tolerance(self) -> None:
        line = [(0.0, 0.0), (10.0, 0.0)]
        self.assertAlmostEqual(MODULE.minimum_distance_to_linestring_m((5.0, 3.0), line), 3.0)
        self.assertAlmostEqual(MODULE.minimum_distance_to_linestring_m((-4.0, 3.0), line), 5.0)
        distance = MODULE.minimum_distance_to_linestring_m(
            (5.0, MODULE.GRID_MAX_SNAP_M),
            line,
        )
        self.assertAlmostEqual(distance, 21.2132034356, places=10)
        self.assertLessEqual(distance, MODULE.GRID_MAX_SNAP_M + MODULE.DOMAIN_TOLERANCE_M)


class IntegrityTests(unittest.TestCase):
    def test_real_frozen_ledgers_are_intact(self) -> None:
        t4 = MODULE.verify_t4_ledger(T4_LEDGER, ROOT)
        v1 = MODULE.verify_v1_manifest(V1_MANIFEST, ROOT)
        self.assertEqual(t4["status"], "INSUMOS_VERIFICADOS")
        self.assertEqual(v1["status"], "INSUMOS_VERIFICADOS")
        self.assertEqual(t4["technical_status"], "PASS")
        self.assertEqual(v1["technical_status"], "PASS")

    def test_tampered_ledger_is_rejected(self) -> None:
        with T4_LEDGER.open("r", encoding="utf-8") as handle:
            ledger = json.load(handle)
        tampered = copy.deepcopy(ledger)
        tampered["files"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / "ledger_tampered.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            _assert_rejected(
                self,
                lambda: MODULE.verify_t4_ledger(path, ROOT),
                expected_fragments=("hash", "integridade", "diverg"),
            )

    def test_missing_file_is_rejected(self) -> None:
        with T4_LEDGER.open("r", encoding="utf-8") as handle:
            ledger = json.load(handle)
        missing = copy.deepcopy(ledger)
        missing["files"][0]["path"] = "arquivo_sintetico_inexistente.xyz"
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / "ledger_missing.json"
            path.write_text(json.dumps(missing), encoding="utf-8")
            _assert_rejected(
                self,
                lambda: MODULE.verify_t4_ledger(path, ROOT),
                expected_fragments=("ausente", "arquivo", "integridade", "inválid"),
            )


class ReferenceSchemaTests(unittest.TestCase):
    def test_structured_revealed_record_is_the_publication_contract(self) -> None:
        normalized = MODULE.validate_reference(
            _synthetic_reference(),
            require_frozen_record=True,
        )
        self.assertEqual(normalized["input_contract"], "STRUCTURED_T5_SCHEMA")
        self.assertEqual(normalized["reference_role"], "POSICAO_DECLARADA_ALVO_SIMULADO")

    def test_flat_reference_is_rejected_for_publication(self) -> None:
        flat = {
            "scenario_id": "RURAL-01",
            "latitude": LAT0,
            "longitude": LON0,
        }
        _assert_rejected(
            self,
            lambda: MODULE.validate_reference(flat, require_frozen_record=True),
            expected_fragments=("estruturado", "position", "publica"),
        )

    def test_unrevealed_record_is_rejected(self) -> None:
        reference = _synthetic_reference()
        reference["status"] = "AGUARDANDO_REVELACAO"
        reference["reference_received"] = False
        _assert_rejected(
            self,
            lambda: MODULE.validate_reference(reference, require_frozen_record=True),
            expected_fragments=("revelado_congelado", "revela"),
        )

    def test_nullable_source_metadata_must_not_be_invented(self) -> None:
        normalized = MODULE.validate_reference(
            _synthetic_reference(),
            require_frozen_record=True,
        )
        self.assertIsNone(normalized["horizontal_accuracy_m"])
        self.assertIsNone(normalized["collection_method"])
        self.assertIsNone(normalized["equipment"])

    def test_required_nullable_source_key_cannot_silently_disappear(self) -> None:
        reference = _synthetic_reference()
        reference["source"].pop("collection_method")
        _assert_rejected(
            self,
            lambda: MODULE.validate_reference(reference, require_frozen_record=True),
            expected_fragments=("collection_method", "source", "obrigat", "ausente"),
        )


class OpeningGateTests(unittest.TestCase):
    @staticmethod
    def _write_synthetic_freeze_ledger(directory: Path, created_at: str) -> Path:
        receipt_names = {
            "relatorio_testes_avaliador_t45_v1.json",
            "relatorio_qa_avaliador_t45_v1.json",
            "RESUMO_CONGELAMENTO_T45.md",
        }
        records: list[dict[str, Any]] = []
        for name in sorted(MODULE.T45_REQUIRED_BASENAMES):
            artifact = directory / name
            artifact.write_text(f"artefato sintético T4.5: {name}\n", encoding="utf-8")
            records.append(
                {
                    "path": str(artifact.relative_to(ROOT)),
                    "role": (
                        "T45_FREEZE_RECEIPT" if name in receipt_names else "T45_EVALUATOR_PACKAGE"
                    ),
                    "bytes": artifact.stat().st_size,
                    "sha256": _sha256(artifact),
                }
            )
        ledger: dict[str, Any] = {
            "protocol_id": "RURAL01-EVAL-T45-T6-v1.0",
            "stage": "T4_5_PRE_REVEAL_EVALUATOR_FREEZE",
            "status": "CONGELADO_ANTES_DA_REVELACAO",
            "created_at_local": created_at,
            "ground_truth_received": False,
            "reference_coordinates_present": False,
            "reference_opening_allowed_after_this_ledger": True,
            "retuning_after_reference_opening": False,
            "tests": {"status": "PASS", "tests_run": 31},
            "qa": {"status": "PASS", "passed_check_count": 1, "check_count": 1},
            "files": records,
            "file_count": len(records),
        }
        ledger["payload_sha256"] = MODULE.canonical_hash(ledger)
        path = directory / "ledger_congelamento_avaliador_t45_sintetico.json"
        path.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def test_real_ledger_hash_and_post_freeze_timestamp_are_required(self) -> None:
        with tempfile.TemporaryDirectory(dir=HERE) as directory_text:
            directory = Path(directory_text)
            ledger_path = self._write_synthetic_freeze_ledger(
                directory,
                "2098-12-31T23:59:59-03:00",
            )
            reference = _synthetic_reference()
            reference["opening"]["evaluator_freeze_manifest_sha256"] = _sha256(ledger_path)
            receipt = MODULE.verify_t45_opening_gate(reference, ledger_path, ROOT)
            self.assertEqual(receipt["status"], "ABERTURA_T5_AUTORIZADA")
            self.assertTrue(receipt["opened_after_freeze"])
            self.assertEqual(receipt["ledger_sha256"], _sha256(ledger_path))

    def test_empty_or_incomplete_freeze_package_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=HERE) as directory_text:
            directory = Path(directory_text)
            ledger_path = self._write_synthetic_freeze_ledger(
                directory,
                "2098-12-31T23:59:59-03:00",
            )
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["files"] = []
            ledger["file_count"] = 0
            ledger["payload_sha256"] = MODULE.canonical_hash(
                {key: value for key, value in ledger.items() if key != "payload_sha256"}
            )
            ledger_path.write_text(
                json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            reference = _synthetic_reference()
            reference["opening"]["evaluator_freeze_manifest_sha256"] = _sha256(ledger_path)
            _assert_rejected(
                self,
                lambda: MODULE.verify_t45_opening_gate(reference, ledger_path, ROOT),
                expected_fragments=("records_nonempty", "required_artifacts", "file_count"),
            )

    def test_wrong_freeze_hash_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=HERE) as directory_text:
            directory = Path(directory_text)
            ledger_path = self._write_synthetic_freeze_ledger(
                directory,
                "2098-12-31T23:59:59-03:00",
            )
            reference = _synthetic_reference()
            reference["opening"]["evaluator_freeze_manifest_sha256"] = "f" * 64
            _assert_rejected(
                self,
                lambda: MODULE.verify_t45_opening_gate(reference, ledger_path, ROOT),
                expected_fragments=("hash", "diverge", "selo"),
            )

    def test_opening_equal_to_or_before_freeze_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=HERE) as directory_text:
            directory = Path(directory_text)
            frozen_at = "2099-01-01T12:00:00-03:00"
            ledger_path = self._write_synthetic_freeze_ledger(directory, frozen_at)
            for opened_at in (frozen_at, "2099-01-01T11:59:59-03:00"):
                reference = _synthetic_reference()
                reference["opening"]["opened_at"] = opened_at
                reference["opening"]["evaluator_freeze_manifest_sha256"] = _sha256(ledger_path)
                with self.subTest(opened_at=opened_at):
                    _assert_rejected(
                        self,
                        lambda: MODULE.verify_t45_opening_gate(reference, ledger_path, ROOT),
                        expected_fragments=("posterior", "congelamento", "opened_at"),
                    )

    def test_publication_rejects_flat_reference_before_creating_output(self) -> None:
        """A API de publicação não pode aceitar o atalho plano da API unitária."""
        flat = {
            "scenario_id": "RURAL-01",
            "latitude": LAT0,
            "longitude": LON0,
        }
        with tempfile.TemporaryDirectory(dir=HERE) as directory_text:
            directory = Path(directory_text)
            reference_path = directory / "referencia_plana_invalida.json"
            output_dir = directory / "saida_que_nao_deve_existir"
            reference_path.write_text(
                json.dumps(flat, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _assert_rejected(
                self,
                lambda: MODULE.run_and_publish(reference_path, output_dir),
                expected_fragments=("estruturado", "position", "publica"),
            )
            self.assertFalse(output_dir.exists())

    def test_publication_must_invoke_t45_opening_gate(self) -> None:
        """Evita regressão em que validar o helper não protege run_and_publish."""
        reference = _synthetic_reference()
        with tempfile.TemporaryDirectory(dir=HERE) as directory_text:
            directory = Path(directory_text)
            reference_path = directory / "referencia_t5_sintetica.json"
            output_dir = directory / "saida_que_nao_deve_existir"
            reference_path.write_text(
                json.dumps(reference, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                MODULE,
                "verify_t45_opening_gate",
                side_effect=MODULE.EvaluationContractError("GATE_T45_SENTINEL"),
            ) as gate:
                _assert_rejected(
                    self,
                    lambda: MODULE.run_and_publish(reference_path, output_dir),
                    expected_fragments=("gate_t45_sentinel",),
                )
            gate.assert_called_once_with(reference)
            self.assertFalse(output_dir.exists())


class EvaluationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reference = _synthetic_reference()
        cls.integrity = {
            "t4_ledger": MODULE.verify_t4_ledger(T4_LEDGER, ROOT),
            "v1_manifest": MODULE.verify_v1_manifest(V1_MANIFEST, ROOT),
        }
        cls.frozen_data = MODULE.load_frozen_data()
        cls.result = MODULE.build_evaluation(
            cls.reference,
            frozen_data=cls.frozen_data,
            integrity_receipts=cls.integrity,
        )

    @classmethod
    def evaluate(cls, reference: Mapping[str, Any]) -> dict[str, Any]:
        return MODULE.build_evaluation(
            reference,
            frozen_data=cls.frozen_data,
            integrity_receipts=cls.integrity,
        )

    def test_invalid_reference_and_missing_required_field_are_rejected(self) -> None:
        invalid = _synthetic_reference(latitude=91.0)
        missing = _synthetic_reference()
        missing["position"].pop("longitude")
        _assert_rejected(self, lambda: self.evaluate(invalid), expected_fragments=("latitude", "coorden"))
        _assert_rejected(self, lambda: self.evaluate(missing), expected_fragments=("longitude", "coorden", "ausente"))

    def test_optional_metadata_may_remain_absent(self) -> None:
        reference = _synthetic_reference()
        result = self.evaluate(reference)
        self.assertEqual(result["reference"]["horizontal_accuracy_m"], None)
        self.assertEqual(result["reference"]["equipment"], None)
        self.assertEqual(result["reference"]["collection_method"], None)

    def test_two_primary_hypotheses_are_reported_without_selection(self) -> None:
        primary = {
            row["cost_scenario_id"]: row
            for row in self.result["scenario_metrics"]
            if row["cost_scenario_id"] in MODULE.PRIMARY_BASE_SCENARIOS
        }
        self.assertEqual(set(primary), set(MODULE.PRIMARY_BASE_SCENARIOS))
        self.assertEqual(len(primary), 2)
        self.assertEqual(
            {row["hypothesis_id"] for row in primary.values()},
            {"H_REDE_DISPONIVEL", "H_FORA_REDE"},
        )
        serialized = json.dumps(self.result, ensure_ascii=False, sort_keys=True)
        self.assertNotIn('"selected_hypothesis"', serialized)
        self.assertNotIn('"winning_hypothesis"', serialized)
        self.assertFalse(self.result["method_guardrails"]["hypotheses_collapsed"])

    def test_sensitivity_and_ablations_are_complete_and_separated(self) -> None:
        sensitivity_ids = {
            row["cost_scenario_id"]
            for row in self.result["scenario_metrics"]
            if row["cost_scenario_id"] in MODULE.SENSITIVITY_SCENARIOS
        }
        ablation_ids = {
            row["cost_scenario_id"] for row in self.result["ablation_metrics_secondary"]
        }
        self.assertEqual(sensitivity_ids, set(MODULE.SENSITIVITY_SCENARIOS))
        self.assertEqual(ablation_ids, set(MODULE.ABLATION_SCENARIOS))
        self.assertTrue(sensitivity_ids.isdisjoint(ablation_ids))
        self.assertEqual(len(sensitivity_ids), 6)
        self.assertGreaterEqual(len(ablation_ids), 4)

    def test_outside_domain_has_no_cell_sector_or_cost(self) -> None:
        lat, lon = MODULE.aeqd_inverse(1600.0, 0.0, LAT0, LON0)
        result = self.evaluate(_synthetic_reference(latitude=lat, longitude=lon))
        self.assertEqual(result["domain"]["status"], "EXTERIOR")
        self.assertIsNone(result["grid_assignment"]["cell_id"])
        self.assertEqual(result["sector_assignment"]["matched_sector_ids"], [])
        for scenario in result["scenario_metrics"]:
            self.assertIsNone(scenario["accumulated_cost_m_equivalent"])

    def test_corridor_scopes_follow_frozen_three_level_contract(self) -> None:
        by_hypothesis: dict[str, set[str]] = {}
        for row in self.result["corridor_metrics"]:
            by_hypothesis.setdefault(row["hypothesis_id"], set()).add(row["scope"])
        self.assertEqual(set(by_hypothesis), {"H_REDE_DISPONIVEL", "H_FORA_REDE"})
        expected = {"PRIMARY_MOV_V_TOP3", "SECONDARY_V1_TOP3", "DIAGNOSTIC_ANY_24"}
        for scopes in by_hypothesis.values():
            self.assertEqual(scopes, expected)

    def test_build_is_deterministic(self) -> None:
        first = self.evaluate(copy.deepcopy(self.reference))
        second = self.evaluate(copy.deepcopy(self.reference))
        self.assertEqual(
            json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            json.dumps(second, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )

    def test_scientific_package_and_narrative_are_complete_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(dir=HERE) as directory_text:
            parent = Path(directory_text)
            first_dir = parent / "run1"
            second_dir = parent / "run2"
            MODULE.build_scientific_outputs(
                first_dir,
                copy.deepcopy(self.reference),
                self.frozen_data,
                self.integrity,
                None,
            )
            MODULE.build_scientific_outputs(
                second_dir,
                copy.deepcopy(self.reference),
                self.frozen_data,
                self.integrity,
                None,
            )
            for name in MODULE.SCIENTIFIC_OUTPUTS:
                self.assertTrue((first_dir / name).is_file(), name)
                self.assertEqual(_sha256(first_dir / name), _sha256(second_dir / name), name)
            narrative = (first_dir / "RELATORIO_AVALIACAO_RURAL01_T6.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("H_REDE_DISPONIVEL", narrative)
            self.assertIn("H_FORA_REDE", narrative)
            self.assertIn("não", narrative.casefold())
            self.assertIn("probabilidade", narrative.casefold())

    def test_evaluation_does_not_modify_frozen_upstream(self) -> None:
        protected = [
            T4_LEDGER,
            T4_DIR / "grade_resistencia.csv",
            T4_DIR / "setores_mov_v2.csv",
            T4_DIR / "corredores_mov_v2.geojson",
            T4_DIR / "resultado_mov_v2.json",
            V1_MANIFEST,
            V1_DIR / "setores_rural01.geojson",
            V1_DIR / "ranking_base_rural01.csv",
            V1_DIR / "top3_rural01.json",
        ]
        before = _snapshot(protected)
        self.evaluate(copy.deepcopy(self.reference))
        after = _snapshot(protected)
        self.assertEqual(before, after)

    def test_no_real_reference_identifiers_leak_into_test_fixture(self) -> None:
        serialized = json.dumps(self.reference, ensure_ascii=False, sort_keys=True)
        self.assertIn("SYNTHETIC-UNIT-TEST-ONLY", serialized)
        self.assertIn("COORDENADA_SINTETICA_EXCLUSIVA_PARA_TESTE", serialized)
        self.assertNotIn("ground_truth_lat", serialized.casefold())
        self.assertNotIn("ground_truth_lon", serialized.casefold())


if __name__ == "__main__":
    unittest.main(verbosity=2)
