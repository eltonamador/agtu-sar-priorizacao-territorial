#!/usr/bin/env python3
"""Testes do firewall lógico e congelamento da preparação REP-S."""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

import export_rep_s_firewall as firewall


BLIND_HEADERS = [
    "scenario_id",
    "candidate_id",
    "site_id",
    "estimated_lat",
    "estimated_lon",
    "base_radius_m",
    "detection_quality",
    "environment_class",
    "position_dispersion_m",
    "information_age_min",
    "r0_semantics",
    "factors_applied",
    "r0_provenance",
    "data_origin",
    "source_row_hash",
    "execution_phase",
]

GT_HEADERS = [
    "site_id",
    "scenario_id",
    "ground_truth_lat",
    "ground_truth_lon",
    "capture_timestamp",
    "horizontal_precision_m",
    "equipment",
    "collection_method",
    "evidence_reference",
    "environment_type",
    "ground_truth_status",
    "custody_status",
]


def blind_row(**updates):
    row = {
        "scenario_id": "RS-001",
        "candidate_id": "RS-001-C1",
        "site_id": "SITE-001",
        # Coordenadas deliberadamente sintéticas e neutras; não reproduzem
        # nenhum ponto histórico ou local de coleta do projeto.
        "estimated_lat": 10.0,
        "estimated_lon": 20.0,
        "base_radius_m": 2000,
        "detection_quality": 0.8,
        "environment_class": "MATA",
        "position_dispersion_m": 25,
        "information_age_min": 30,
        "r0_semantics": "nominal_base",
        "factors_applied": "none",
        "r0_provenance": "PROTOCOLO_CONGELADO",
        "data_origin": "GERADOR_CONGELADO",
        "source_row_hash": "abc123",
        "execution_phase": "REP-S",
    }
    row.update(updates)
    return row


def gt_row(**updates):
    row = {
        "site_id": "SITE-001",
        "scenario_id": "RS-001",
        "ground_truth_lat": 10.001,
        "ground_truth_lon": 20.002,
        "capture_timestamp": "",
        "horizontal_precision_m": "",
        "equipment": "",
        "collection_method": "manual_map_marker",
        "evidence_reference": "",
        "environment_type": "",
        "ground_truth_status": "REVISAR",
        "custody_status": "LACRADO",
    }
    row.update(updates)
    return row


def plan_row(**updates):
    row = {
        "site_id": "SITE-001",
        "planned_environment": "MATA",
        "validation_modality": "REP-S-FIELD-PILOT",
        "execution_phase": "REP-S",
        "partition_assigned_before_outcomes": "SIM",
        "source_is_new_for_rep_s": "SIM",
        "acquisition_status": "COLETADO",
    }
    row.update(updates)
    return row


def append_dict(sheet, headers, row):
    sheet.append([row.get(header, "") for header in headers])


def build_workbook(
    path: Path,
    *,
    blind_headers=None,
    blind_rows=None,
    gt_headers=None,
    gt_rows=None,
    plan_rows=None,
    header_row=1,
):
    blind_headers = list(blind_headers or BLIND_HEADERS)
    blind_rows = list(blind_rows or [blind_row()])
    gt_headers = list(gt_headers or GT_HEADERS)
    gt_rows = list(gt_rows or [gt_row()])

    wb = Workbook()
    ws = wb.active
    ws.title = firewall.BLIND_SHEET
    for index in range(1, header_row):
        ws.append(["Título/instrução" if index == 1 else ""])
    ws.append(blind_headers)
    for row in blind_rows:
        append_dict(ws, blind_headers, row)

    gt = wb.create_sheet(firewall.GT_SHEET)
    for index in range(1, header_row):
        gt.append(["Título/instrução" if index == 1 else ""])
    gt.append(gt_headers)
    for row in gt_rows:
        append_dict(gt, gt_headers, row)

    if plan_rows is not None:
        plan = wb.create_sheet(firewall.PLAN_SHEET)
        plan_headers = [
            "site_id",
            "planned_environment",
            "validation_modality",
            "execution_phase",
            "partition_assigned_before_outcomes",
            "source_is_new_for_rep_s",
            "acquisition_status",
        ]
        for index in range(1, header_row):
            plan.append(["Título/instrução" if index == 1 else ""])
        plan.append(plan_headers)
        for row in plan_rows:
            append_dict(plan, plan_headers, row)
    wb.save(path)


class RepSFirewallTestCase(unittest.TestCase):
    timestamp = "2026-10-14T12:00:00Z"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workbook = self.root / "kit.xlsx"
        self.output = self.root / "package"

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, **workbook_kwargs):
        workbook_kwargs.setdefault("plan_rows", [plan_row()])
        build_workbook(self.workbook, **workbook_kwargs)
        return firewall.prepare_package(
            self.workbook, self.output, timestamp=self.timestamp
        )

    def reproducibility_evidence(self):
        config = self.root / "config.json"
        engine = self.root / "engine.py"
        tests = self.root / "test_result.json"
        config.write_text('{"protocol":"synthetic-test"}\n', encoding="utf-8")
        engine.write_text("def run():\n    return 'synthetic'\n", encoding="utf-8")
        tests.write_text(
            json.dumps(
                {"status": "PASS", "tests_run": 7, "failures": 0, "errors": 0}
            )
            + "\n",
            encoding="utf-8",
        )
        return config, engine, tests

    def write_engine_manifest(
        self,
        output_path,
        config,
        engine,
        destination,
        *,
        generated_at="2026-10-14T12:00:00Z",
        ground_truth_used=False,
        role_hash_overrides=None,
    ):
        output_path = Path(output_path)
        if output_path.is_file():
            scientific = [output_path]
        else:
            scientific = sorted(
                path
                for path in output_path.rglob("*")
                if path.is_file()
                and path.suffix.lower() in firewall.SCIENTIFIC_OUTPUT_SUFFIXES
                and "manifest" not in firewall.normalized_token(path.stem)
                and "log" not in firewall.normalized_token(path.stem)
            )
        input_path = self.output / "public" / "rep_s_input_blind.csv"
        overrides = dict(role_hash_overrides or {})
        files = [
            {
                "role": "input",
                "path": str(input_path),
                "sha256": overrides.get("input", firewall.sha256_file(input_path)),
                "bytes": input_path.stat().st_size,
            },
            {
                "role": "config",
                "path": str(config),
                "sha256": overrides.get("config", firewall.sha256_file(config)),
                "bytes": Path(config).stat().st_size,
            },
            {
                "role": "engine",
                "path": str(engine),
                "sha256": overrides.get("engine", firewall.sha256_file(engine)),
                "bytes": Path(engine).stat().st_size,
            },
        ]
        files.extend(
            {
                "role": "output",
                "path": str(path),
                "sha256": firewall.sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in scientific
        )
        payload = {
            "protocol_id": "EXT-ESP-BUF-v1.0",
            "engine_version": "synthetic-test",
            "generated_at_utc": generated_at,
            "ground_truth_used": ground_truth_used,
            "record_count": 1,
            "files": files,
        }
        destination = Path(destination)
        destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return destination

    def freeze(self, model_output, repeat_output, **kwargs):
        config, engine, tests = self.reproducibility_evidence()
        engine_manifest = kwargs.pop("engine_manifest_path", None)
        repeat_engine_manifest = kwargs.pop("repeat_engine_manifest_path", None)
        if engine_manifest is None:
            engine_manifest = self.write_engine_manifest(
                model_output,
                config,
                engine,
                self.root / "engine_manifest_run_1.json",
                generated_at="2026-10-14T12:00:01Z",
            )
        if repeat_engine_manifest is None:
            repeat_engine_manifest = self.write_engine_manifest(
                repeat_output,
                config,
                engine,
                self.root / "engine_manifest_run_2.json",
                generated_at="2026-10-14T12:00:02Z",
            )
        return firewall.freeze_model_output(
            model_output,
            self.output / "manifesto_preparacao_rep_s.json",
            config_path=config,
            engine_path=engine,
            test_evidence_path=tests,
            repeat_output_path=repeat_output,
            engine_manifest_path=engine_manifest,
            repeat_engine_manifest_path=repeat_engine_manifest,
            timestamp=self.timestamp,
            **kwargs,
        )

    def test_prepare_exports_physically_separated_files_and_hash_only_manifest(self):
        self.prepare(plan_rows=[plan_row()])
        blind_path = self.output / "public" / "rep_s_input_blind.csv"
        gt_path = self.output / "locked" / "rep_s_ground_truth_locked.csv"
        root_manifest = self.output / "manifesto_preparacao_rep_s.json"
        public_text = blind_path.read_text(encoding="utf-8")
        locked_text = gt_path.read_text(encoding="utf-8")
        manifest_text = root_manifest.read_text(encoding="utf-8")

        self.assertTrue(blind_path.is_file())
        self.assertTrue(gt_path.is_file())
        self.assertNotIn("ground_truth", public_text)
        self.assertIn("ground_truth_lat", locked_text)
        self.assertNotIn("10.001", manifest_text)
        self.assertNotIn("20.002", manifest_text)

        payload = json.loads(manifest_text)
        self.assertEqual(payload["state"], "ENTRADA_CEGA_CONGELADA")
        self.assertEqual(
            payload["artifacts"]["ground_truth_locked"]["sha256"],
            firewall.sha256_file(gt_path),
        )
        self.assertFalse(
            payload["artifacts"]["ground_truth_locked"]["coordinates_disclosed"]
        )
        public_manifest = json.loads(
            (self.output / "public" / "manifesto_entrada_cega.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(public_manifest["state"], "ENTRADA_CEGA_CONGELADA")
        gates = {item["gate_id"]: item["status"] for item in public_manifest["gates"]}
        self.assertEqual([gates[f"G{i:02d}"] for i in range(1, 6)], ["PASS"] * 5)
        self.assertEqual([gates[f"G{i:02d}"] for i in range(6, 11)], ["PENDENTE"] * 5)

    def test_blank_rows_are_ignored(self):
        self.prepare(blind_rows=[blind_row(), {}], gt_rows=[gt_row(), {}])
        payload = json.loads(
            (self.output / "manifesto_preparacao_rep_s.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["counts"]["blind_rows"], 1)
        self.assertEqual(payload["counts"]["ground_truth_rows"], 1)

    def test_human_facing_header_on_row_four_is_detected(self):
        self.prepare(
            header_row=4,
            plan_rows=[plan_row()],
        )
        payload = json.loads(
            (self.output / "manifesto_preparacao_rep_s.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["counts"]["blind_rows"], 1)
        self.assertEqual(payload["counts"]["sites"], 1)

    def test_template_row_status_formula_is_ignored(self):
        blind_headers = BLIND_HEADERS + ["row_status"]
        gt_headers = GT_HEADERS + ["row_status"]
        build_workbook(
            self.workbook,
            blind_headers=blind_headers,
            blind_rows=[blind_row(row_status='=IF(A5="","","PRONTO")')],
            gt_headers=gt_headers,
            gt_rows=[gt_row(row_status='=IF(A5="","","PRONTO")')],
            plan_rows=[plan_row()],
            header_row=4,
        )
        firewall.prepare_package(
            self.workbook, self.output, timestamp=self.timestamp
        )
        blind_text = (self.output / "public" / "rep_s_input_blind.csv").read_text(
            encoding="utf-8"
        )
        locked_text = (
            self.output / "locked" / "rep_s_ground_truth_locked.csv"
        ).read_text(encoding="utf-8")
        self.assertNotIn("row_status", blind_text)
        self.assertNotIn("row_status", locked_text)

    def test_ground_truth_column_in_blind_sheet_is_rejected_even_if_blank(self):
        headers = BLIND_HEADERS + ["ground_truth_lat"]
        with self.assertRaises(firewall.WorkbookSchemaError):
            self.prepare(blind_headers=headers)

    def test_duplicate_candidate_key_is_rejected(self):
        with self.assertRaises(firewall.WorkbookValueError):
            self.prepare(blind_rows=[blind_row(), blind_row()])

    def test_same_site_cannot_be_split_between_development_and_rep_s(self):
        rows = [
            blind_row(candidate_id="RS-001-C1", execution_phase="REP-S"),
            blind_row(
                scenario_id="RS-002",
                candidate_id="RS-002-C1",
                execution_phase="DEV-S",
            ),
        ]
        gts = [gt_row(), gt_row(scenario_id="RS-002")]
        with self.assertRaisesRegex(firewall.WorkbookValueError, "Partição inválida"):
            self.prepare(blind_rows=rows, gt_rows=gts)

    def test_scenario_cannot_map_to_multiple_sites(self):
        rows = [
            blind_row(candidate_id="RS-001-C1"),
            blind_row(candidate_id="RS-001-C2", site_id="SITE-002"),
        ]
        with self.assertRaisesRegex(firewall.WorkbookValueError, "mais de um site_id"):
            self.prepare(blind_rows=rows)

    def test_plan_phase_must_match_blind_input(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "diverge"):
            self.prepare(
                plan_rows=[plan_row(execution_phase="DEV-S")]
            )

    def test_rep_s_requires_plan_sheet(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "obrigatória"):
            self.prepare(plan_rows=None)

    def test_plan_partition_must_be_assigned_before_outcomes(self):
        with self.assertRaisesRegex(
            firewall.WorkbookValueError, "partition_assigned_before_outcomes deve ser SIM"
        ):
            self.prepare(
                plan_rows=[plan_row(partition_assigned_before_outcomes="NÃO")]
            )

    def test_rep_s_source_must_be_new(self):
        with self.assertRaisesRegex(
            firewall.WorkbookValueError, "source_is_new_for_rep_s deve ser SIM"
        ):
            self.prepare(plan_rows=[plan_row(source_is_new_for_rep_s="NÃO")])

    def test_plan_rejects_unknown_acquisition_status(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "acquisition_status"):
            self.prepare(plan_rows=[plan_row(acquisition_status="EM_CAMPO")])

    def test_planned_site_cannot_enter_execution_package(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "deve ser COLETADO"):
            self.prepare(plan_rows=[plan_row(acquisition_status="PLANEJADO")])

    def test_plan_rejects_unknown_modality(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "validation_modality"):
            self.prepare(plan_rows=[plan_row(validation_modality="REP-S-OUTRA")])

    def test_field_pilot_requires_frozen_generator_origin(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "data_origin incompatível"):
            self.prepare(
                blind_rows=[blind_row(data_origin="SISTEMA_AEROTRANSPORTADO")]
            )

    def test_operational_modality_accepts_airborne_origin(self):
        payload = self.prepare(
            blind_rows=[blind_row(data_origin="SISTEMA_AEROTRANSPORTADO")],
            plan_rows=[plan_row(validation_modality="REP-S-OP")],
        )
        self.assertEqual(payload["state"], "ENTRADA_CEGA_CONGELADA")

    def test_operational_modality_rejects_generator_origin(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "data_origin incompatível"):
            self.prepare(plan_rows=[plan_row(validation_modality="REP-S-OP")])

    def test_every_blind_scenario_requires_matching_locked_ground_truth(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "sem registro correspondente"):
            self.prepare(gt_rows=[gt_row(scenario_id="RS-999")])

    def test_candidate_output_columns_are_rejected_from_ground_truth(self):
        headers = GT_HEADERS + ["candidate_rank"]
        with self.assertRaises(firewall.WorkbookSchemaError):
            self.prepare(gt_headers=headers)

    def test_ground_truth_status_enum_is_enforced(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "ground_truth_status"):
            self.prepare(gt_rows=[gt_row(ground_truth_status="CONFIRMADO")])

    def test_custody_status_enum_is_enforced(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "custody_status"):
            self.prepare(gt_rows=[gt_row(custody_status="GUARDADO")])

    def test_ground_truth_cannot_be_open_during_preparation(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "RESERVADO ou LACRADO"):
            self.prepare(gt_rows=[gt_row(custody_status="ABERTO")])

    def test_rep_s_rejects_diagnostic_legacy_r0(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "não é elegível"):
            self.prepare(blind_rows=[blind_row(r0_semantics="diagnostic_legacy")])

    def test_rep_s_nominal_base_requires_frozen_two_kilometres(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "base_radius_m = 2000"):
            self.prepare(blind_rows=[blind_row(base_radius_m=1750)])

    def test_rep_s_requires_origin_and_r0_provenance(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "r0_provenance"):
            self.prepare(blind_rows=[blind_row(r0_provenance="")])

    def test_source_row_hash_is_generated_by_exporter(self):
        self.prepare(blind_rows=[blind_row(source_row_hash="preenchimento_manual_ignorado")])
        with (self.output / "public" / "rep_s_input_blind.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertRegex(rows[0]["source_row_hash"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(rows[0]["source_row_hash"], "preenchimento_manual_ignorado")

    def test_present_plan_sheet_cannot_be_empty(self):
        build_workbook(self.workbook, plan_rows=[])
        with self.assertRaisesRegex(firewall.WorkbookValueError, "nenhuma linha de planejamento"):
            firewall.prepare_package(
                self.workbook, self.output, timestamp=self.timestamp
            )

    def test_source_adjusted_requires_factor_history_and_provenance(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "source_adjusted exige"):
            self.prepare(
                blind_rows=[
                    blind_row(
                        r0_semantics="source_adjusted",
                        factors_applied="",
                        r0_provenance="",
                    )
                ]
            )

    def test_formula_in_critical_data_is_rejected(self):
        with self.assertRaisesRegex(firewall.WorkbookValueError, "fórmulas não são aceitas"):
            self.prepare(blind_rows=[blind_row(detection_quality="=1/2")])

    def test_invalid_ground_truth_error_does_not_echo_coordinate_value(self):
        bad_value = "-999.123456"
        build_workbook(self.workbook, gt_rows=[gt_row(ground_truth_lon=bad_value)])
        with self.assertRaises(firewall.WorkbookValueError) as caught:
            firewall.prepare_package(self.workbook, self.output, timestamp=self.timestamp)
        self.assertNotIn(bad_value, str(caught.exception))

    def test_existing_outputs_require_explicit_overwrite(self):
        self.prepare()
        with self.assertRaises(firewall.FreezeStateError):
            firewall.prepare_package(self.workbook, self.output, timestamp=self.timestamp)
        firewall.prepare_package(
            self.workbook,
            self.output,
            overwrite=True,
            timestamp=self.timestamp,
        )

    def test_freeze_output_records_hash_without_reading_or_disclosing_gt(self):
        self.prepare()
        model_output = self.root / "model_output.csv"
        model_output.write_text(
            "scenario_id,candidate_id,adaptive_radius_m\nRS-001,RS-001-C1,2500\n",
            encoding="utf-8",
        )
        repeat_output = self.root / "model_output_repeat.csv"
        repeat_output.write_bytes(model_output.read_bytes())
        frozen = self.freeze(model_output, repeat_output)
        self.assertEqual(frozen["state"], "SAIDA_DO_MODELO_CONGELADA")
        self.assertEqual(
            frozen["model_output"]["sha256"], firewall.sha256_file(model_output)
        )
        self.assertFalse(frozen["ground_truth"]["coordinates_disclosed"])
        self.assertFalse(frozen["ground_truth"]["opened_by_freeze_command"])
        self.assertTrue(
            frozen["reproducibility_evidence"]["deterministic_runs"]["matching"]
        )
        self.assertEqual(frozen["gates"]["G06"], "PASS")
        self.assertEqual(frozen["gates"]["G07"], "PASS")
        self.assertEqual(frozen["gates"]["G08"], "PASS")
        self.assertEqual(frozen["next_required_state"], "GROUND_TRUTH_ABERTO")
        manifest_text = model_output.with_name(
            "manifesto_saida_modelo_congelada.json"
        ).read_text(encoding="utf-8")
        self.assertNotIn("10.001", manifest_text)
        self.assertNotIn("20.002", manifest_text)

    def test_ground_truth_used_boolean_false_is_allowed_in_csv_json_and_geojson(self):
        self.prepare()
        first = self.root / "gt_false_run_1"
        second = self.root / "gt_false_run_2"
        for directory in (first, second):
            directory.mkdir()
            (directory / "result.csv").write_text(
                "scenario_id,ground_truth_used,radius\nRS-001,false,2500\n",
                encoding="utf-8",
            )
            (directory / "result.json").write_text(
                '{"ground_truth_used":false,"results":[{"ground_truth_used":false,"radius":2500}]}\n',
                encoding="utf-8",
            )
            (directory / "result.geojson").write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "ground_truth_used": False,
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"ground_truth_used": False},
                                "geometry": {"type": "Point", "coordinates": [20.0, 10.0]},
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        frozen = self.freeze(first, second)
        self.assertEqual(frozen["model_output"]["scope"], "scientific_results_only")
        self.assertEqual(frozen["model_output"]["file_count"], 3)

    def test_ground_truth_used_json_rejects_true_and_non_boolean_false(self):
        self.prepare()
        for index, bad_value in enumerate((True, "false", 0), start=1):
            first = self.root / f"bad_json_{index}_1.json"
            second = self.root / f"bad_json_{index}_2.json"
            content = json.dumps({"ground_truth_used": bad_value, "radius": 2500}) + "\n"
            first.write_text(content, encoding="utf-8")
            second.write_text(content, encoding="utf-8")
            with self.subTest(value=bad_value), self.assertRaisesRegex(
                firewall.FreezeStateError, "booleano false"
            ):
                self.freeze(first, second)

    def test_ground_truth_used_csv_rejects_true_zero_and_blank(self):
        self.prepare()
        for index, bad_value in enumerate(("true", "0", ""), start=1):
            first = self.root / f"bad_csv_{index}_1.csv"
            second = self.root / f"bad_csv_{index}_2.csv"
            content = (
                "scenario_id,ground_truth_used,radius\n"
                f"RS-001,{bad_value},2500\n"
            )
            first.write_text(content, encoding="utf-8")
            second.write_text(content, encoding="utf-8")
            with self.subTest(value=bad_value), self.assertRaisesRegex(
                firewall.FreezeStateError, "booleano false"
            ):
                self.freeze(first, second)

    def test_engine_manifest_must_match_prepared_input_hash(self):
        self.prepare()
        first = self.root / "manifest_input_1.csv"
        second = self.root / "manifest_input_2.csv"
        content = "scenario_id,radius\nRS-001,2500\n"
        first.write_text(content, encoding="utf-8")
        second.write_text(content, encoding="utf-8")
        config, engine, _tests = self.reproducibility_evidence()
        bad_hash = "0" * 64
        manifest_1 = self.write_engine_manifest(
            first,
            config,
            engine,
            self.root / "bad_input_manifest_1.json",
            role_hash_overrides={"input": bad_hash},
        )
        manifest_2 = self.write_engine_manifest(
            second, config, engine, self.root / "bad_input_manifest_2.json"
        )
        with self.assertRaisesRegex(firewall.FreezeStateError, "role=input"):
            self.freeze(
                first,
                second,
                engine_manifest_path=manifest_1,
                repeat_engine_manifest_path=manifest_2,
            )

    def test_engine_manifest_config_and_engine_hashes_must_match_files(self):
        self.prepare()
        first = self.root / "manifest_roles_1.csv"
        second = self.root / "manifest_roles_2.csv"
        content = "scenario_id,radius\nRS-001,2500\n"
        first.write_text(content, encoding="utf-8")
        second.write_text(content, encoding="utf-8")
        config, engine, _tests = self.reproducibility_evidence()
        for role in ("config", "engine"):
            manifest_1 = self.write_engine_manifest(
                first,
                config,
                engine,
                self.root / f"bad_{role}_manifest_1.json",
                role_hash_overrides={role: "f" * 64},
            )
            manifest_2 = self.write_engine_manifest(
                second,
                config,
                engine,
                self.root / f"bad_{role}_manifest_2.json",
            )
            with self.subTest(role=role), self.assertRaisesRegex(
                firewall.FreezeStateError, f"role={role}"
            ):
                self.freeze(
                    first,
                    second,
                    engine_manifest_path=manifest_1,
                    repeat_engine_manifest_path=manifest_2,
                )

    def test_engine_manifest_requires_boolean_false_ground_truth_flag(self):
        self.prepare()
        first = self.root / "manifest_gt_1.csv"
        second = self.root / "manifest_gt_2.csv"
        content = "scenario_id,radius\nRS-001,2500\n"
        first.write_text(content, encoding="utf-8")
        second.write_text(content, encoding="utf-8")
        config, engine, _tests = self.reproducibility_evidence()
        for index, bad_value in enumerate((True, "false"), start=1):
            manifest_1 = self.write_engine_manifest(
                first,
                config,
                engine,
                self.root / f"bad_gt_manifest_{index}_1.json",
                ground_truth_used=bad_value,
            )
            manifest_2 = self.write_engine_manifest(
                second,
                config,
                engine,
                self.root / f"bad_gt_manifest_{index}_2.json",
            )
            with self.subTest(value=bad_value), self.assertRaisesRegex(
                firewall.FreezeStateError, "booleano false"
            ):
                self.freeze(
                    first,
                    second,
                    engine_manifest_path=manifest_1,
                    repeat_engine_manifest_path=manifest_2,
                )

    def test_manifest_and_log_differences_do_not_break_scientific_determinism(self):
        self.prepare()
        first = self.root / "evidence_run_1"
        second = self.root / "evidence_run_2"
        for directory, stamp in (
            (first, "2026-10-14T12:00:01Z"),
            (second, "2026-10-14T12:00:02Z"),
        ):
            directory.mkdir()
            (directory / "result.csv").write_text(
                "scenario_id,ground_truth_used,radius\nRS-001,false,2500\n",
                encoding="utf-8",
            )
            (directory / "execution.log").write_text(
                f"started_at={stamp} ground_truth_used=false\n", encoding="utf-8"
            )
        frozen = self.freeze(first, second)
        deterministic = frozen["reproducibility_evidence"]["deterministic_runs"]
        self.assertTrue(deterministic["matching"])
        self.assertEqual(deterministic["comparison_scope"], "scientific_results_only")
        self.assertFalse(frozen["execution_evidence"]["equality_required"])
        self.assertNotEqual(
            frozen["execution_evidence"]["run_1"]["sha256"],
            frozen["execution_evidence"]["run_2"]["sha256"],
        )

    def test_real_buffer_engine_manifest_contract_is_accepted(self):
        self.prepare()
        test_root = Path(__file__).resolve().parent
        source_layout_root = test_root.parent / "ext_espacial_buffer_v1"
        # No diretório de desenvolvimento, motor e configuração vivem no
        # projeto irmão. No pacote ZIP distribuível, todos os arquivos ficam
        # lado a lado. O teste deve comprovar ambos os layouts.
        buffer_root = (
            test_root
            if (test_root / "motor_buffer_adaptativo.py").is_file()
            else source_layout_root
        )
        engine_path = buffer_root / "motor_buffer_adaptativo.py"
        config_path = buffer_root / "config_buffer_v1.json"
        packaged_test_evidence = test_root / "resultado_testes_rep_s_v1.json"
        test_evidence = (
            packaged_test_evidence
            if packaged_test_evidence.is_file()
            else buffer_root / "results" / "test_results.json"
        )
        spec = importlib.util.spec_from_file_location("rep_s_real_buffer_engine", engine_path)
        assert spec is not None and spec.loader is not None
        real_engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(real_engine)

        manifests = []
        run_dirs = []
        for run in (1, 2):
            directory = self.root / f"real_engine_run_{run}"
            directory.mkdir()
            manifest = directory / "manifest_execucao.json"
            real_engine.run_pipeline(
                input_path=self.output / "public" / "rep_s_input_blind.csv",
                config_path=config_path,
                output_csv_path=directory / "buffer_results.csv",
                output_json_path=directory / "buffer_results.json",
                output_geojson_path=directory / "buffer_polygons.geojson",
                manifest_path=manifest,
            )
            manifests.append(manifest)
            run_dirs.append(directory)

        frozen = firewall.freeze_model_output(
            run_dirs[0],
            self.output / "manifesto_preparacao_rep_s.json",
            config_path=config_path,
            engine_path=engine_path,
            test_evidence_path=test_evidence,
            repeat_output_path=run_dirs[1],
            engine_manifest_path=manifests[0],
            repeat_engine_manifest_path=manifests[1],
            timestamp=self.timestamp,
        )
        self.assertTrue(
            frozen["reproducibility_evidence"]["deterministic_runs"]["matching"]
        )
        self.assertEqual(frozen["model_output"]["file_count"], 3)

    def test_freeze_output_rejects_output_that_contains_ground_truth(self):
        self.prepare()
        model_output = self.root / "contaminated.csv"
        model_output.write_text(
            "scenario_id,ground_truth_lat\nRS-001,0.1\n", encoding="utf-8"
        )
        repeat_output = self.root / "repeat.csv"
        repeat_output.write_text(
            "scenario_id,candidate_id\nRS-001,RS-001-C1\n", encoding="utf-8"
        )
        with self.assertRaises(firewall.WorkbookSchemaError):
            self.freeze(model_output, repeat_output)

    def test_freeze_output_requires_all_reproducibility_evidence(self):
        self.prepare()
        model_output = self.root / "model_output.csv"
        repeat_output = self.root / "repeat.csv"
        content = "scenario_id,candidate_id\nRS-001,RS-001-C1\n"
        model_output.write_text(content, encoding="utf-8")
        repeat_output.write_text(content, encoding="utf-8")
        with self.assertRaisesRegex(firewall.FreezeStateError, "configuração congelada"):
            firewall.freeze_model_output(
                model_output,
                self.output / "manifesto_preparacao_rep_s.json",
                repeat_output_path=repeat_output,
                timestamp=self.timestamp,
            )

    def test_freeze_output_rejects_failing_test_evidence(self):
        self.prepare()
        model_output = self.root / "model_output.csv"
        repeat_output = self.root / "repeat.csv"
        content = "scenario_id,candidate_id\nRS-001,RS-001-C1\n"
        model_output.write_text(content, encoding="utf-8")
        repeat_output.write_text(content, encoding="utf-8")
        config, engine, tests = self.reproducibility_evidence()
        tests.write_text(
            '{"status":"FAILED","tests_run":7,"failures":1,"errors":0}\n',
            encoding="utf-8",
        )
        manifest_1 = self.write_engine_manifest(
            model_output, config, engine, self.root / "failed_tests_manifest_1.json"
        )
        manifest_2 = self.write_engine_manifest(
            repeat_output, config, engine, self.root / "failed_tests_manifest_2.json"
        )
        with self.assertRaisesRegex(firewall.FreezeStateError, "não comprova"):
            firewall.freeze_model_output(
                model_output,
                self.output / "manifesto_preparacao_rep_s.json",
                config_path=config,
                engine_path=engine,
                test_evidence_path=tests,
                repeat_output_path=repeat_output,
                engine_manifest_path=manifest_1,
                repeat_engine_manifest_path=manifest_2,
                timestamp=self.timestamp,
            )

    def test_test_evidence_accepts_real_motor_result_schema(self):
        evidence = self.root / "motor_test_results.json"
        evidence.write_text(
            json.dumps(
                {
                    "protocol_id": "EXT-ESP-BUF-v1.0",
                    "tests_run": 28,
                    "passed": 28,
                    "failed": 0,
                    "errors": 0,
                    "skipped": 0,
                    "successful": True,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        validated = firewall._validate_test_evidence(evidence)
        self.assertEqual(validated["status"], "PASS")
        self.assertEqual(validated["tests_run"], 28)

    def test_freeze_output_rejects_non_deterministic_second_run(self):
        self.prepare()
        model_output = self.root / "model_output.json"
        repeat_output = self.root / "repeat.json"
        model_output.write_text('{"radius":2500}\n', encoding="utf-8")
        repeat_output.write_text('{"radius":2600}\n', encoding="utf-8")
        with self.assertRaisesRegex(firewall.FreezeStateError, "não são determinísticas"):
            self.freeze(model_output, repeat_output)

    def test_freeze_output_rejects_empty_artifact(self):
        self.prepare()
        model_output = self.root / "model_output.json"
        repeat_output = self.root / "repeat.json"
        model_output.write_text("{}\n", encoding="utf-8")
        repeat_output.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(firewall.FreezeStateError, "estrutura JSON vazia"):
            self.freeze(model_output, repeat_output)

    def test_freeze_output_inspects_nested_json_fields(self):
        self.prepare()
        model_output = self.root / "model_output.json"
        repeat_output = self.root / "repeat.json"
        content = '{"results":[{"metrics":{"target_lat":10.001}}]}\n'
        model_output.write_text(content, encoding="utf-8")
        repeat_output.write_text(content, encoding="utf-8")
        with self.assertRaises(firewall.WorkbookSchemaError):
            self.freeze(model_output, repeat_output)

    def test_freeze_output_accepts_recursive_csv_json_geojson_bundle(self):
        self.prepare()
        first = self.root / "run_1"
        second = self.root / "run_2"
        for directory in (first, second):
            (directory / "nested").mkdir(parents=True)
            (directory / "result.csv").write_text(
                "scenario_id,candidate_id\nRS-001,RS-001-C1\n", encoding="utf-8"
            )
            (directory / "nested" / "metrics.json").write_text(
                '{"coverage":0.9,"area_m2":1234}\n', encoding="utf-8"
            )
            (directory / "nested" / "geometry.geojson").write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"candidate_id": "RS-001-C1"},
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [20.0, 10.0],
                                },
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
        frozen = self.freeze(first, second)
        self.assertEqual(frozen["model_output"]["file_count"], 3)
        self.assertEqual(frozen["model_output"]["formats"], ["CSV", "GEOJSON", "JSON"])
        self.assertTrue(frozen["ground_truth"]["release_authorized_after_this_state"])

    def test_freeze_output_rejects_nested_contamination_in_directory(self):
        self.prepare()
        first = self.root / "run_1"
        second = self.root / "run_2"
        for directory in (first, second):
            (directory / "nested").mkdir(parents=True)
            (directory / "nested" / "result.geojson").write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"inside_buffer": True},
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [20.0, 10.0],
                                },
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
        with self.assertRaises(firewall.WorkbookSchemaError):
            self.freeze(first, second)

    def test_freeze_output_never_reads_locked_ground_truth_as_bundle(self):
        self.prepare()
        repeat_output = self.root / "repeat.csv"
        repeat_output.write_text(
            "scenario_id,candidate_id\nRS-001,RS-001-C1\n", encoding="utf-8"
        )
        config, engine, _tests = self.reproducibility_evidence()
        manifest_1 = self.write_engine_manifest(
            repeat_output, config, engine, self.root / "gt_guard_manifest_1.json"
        )
        manifest_2 = self.write_engine_manifest(
            repeat_output, config, engine, self.root / "gt_guard_manifest_2.json"
        )
        with self.assertRaisesRegex(firewall.FreezeStateError, "arquivo reservado"):
            self.freeze(
                self.output,
                repeat_output,
                engine_manifest_path=manifest_1,
                repeat_engine_manifest_path=manifest_2,
            )

    def test_cli_reports_controlled_error_code(self):
        build_workbook(
            self.workbook,
            blind_headers=BLIND_HEADERS + ["true_lat"],
        )
        exit_code = firewall.main(
            ["prepare", str(self.workbook), str(self.output), "--timestamp", self.timestamp]
        )
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
