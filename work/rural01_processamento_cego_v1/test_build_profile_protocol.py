#!/usr/bin/env python3
"""Testes de integração local para o pacote PERFIL/URG/DET do RURAL-01."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent / "build_profile_protocol.py"
SPEC = importlib.util.spec_from_file_location("build_profile_protocol_tested", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Falha ao carregar build_profile_protocol.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Rural01ProfileProtocolTest(unittest.TestCase):
    def test_contextual_profile_abstains_and_urgency_is_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ranking = root / "ranking_base_rural01.csv"
            polygons = root / "setores_rural01.geojson"
            visual_manifest = root / "manifesto_metadados_visuais.json"
            output = root / "output"
            rows = [
                {
                    "scenario_id": "RURAL-01",
                    "candidate_id": "RURAL-01-E0",
                    "sector_id": "RURAL-01::RURAL-01-E0::R01::N",
                    "score_base": "0.7",
                    "rank_base_within_buffer": "1",
                    "azimuth_start_deg": "315",
                    "azimuth_end_deg": "45",
                    "representative_lat": "0.190",
                    "representative_lon": "-51.155",
                    "ring_id": "R01",
                    "direction": "N",
                },
                {
                    "scenario_id": "RURAL-01",
                    "candidate_id": "RURAL-01-E0",
                    "sector_id": "RURAL-01::RURAL-01-E0::R01::S",
                    "score_base": "0.6",
                    "rank_base_within_buffer": "2",
                    "azimuth_start_deg": "135",
                    "azimuth_end_deg": "225",
                    "representative_lat": "0.187",
                    "representative_lon": "-51.155",
                    "ring_id": "R01",
                    "direction": "S",
                },
            ]
            with ranking.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            polygons.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"sector_id": rows[0]["sector_id"]},
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [[
                                        [-51.156, 0.188],
                                        [-51.154, 0.188],
                                        [-51.154, 0.190],
                                        [-51.156, 0.190],
                                        [-51.156, 0.188],
                                    ]],
                                },
                            },
                            {
                                "type": "Feature",
                                "properties": {"sector_id": rows[1]["sector_id"]},
                                "geometry": {
                                    "type": "Polygon",
                                    "coordinates": [[
                                        [-51.156, 0.186],
                                        [-51.154, 0.186],
                                        [-51.154, 0.188],
                                        [-51.156, 0.188],
                                        [-51.156, 0.186],
                                    ]],
                                },
                            },
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            visual_manifest.write_text(
                json.dumps(
                    {
                        "scenario_id": "RURAL-01",
                        "use": "REFERENCIA_DE_CONTROLE_SEM_EFEITO_LOC_DET",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            manifest = MODULE.build_package(
                ranking,
                polygons,
                visual_manifest,
                output,
                "2026-10-22T12:13:12-03:00",
            )
            self.assertTrue(manifest["checks"]["profile_v3_abstained"])
            self.assertTrue(manifest["checks"]["territorial_ranking_preserved_exactly"])
            self.assertEqual(manifest["checks"]["urgency_status"], "REVISAO_PRIORITARIA")
            self.assertEqual(manifest["checks"]["detectability_status"], "REVISAR")
            self.assertTrue(manifest["checks"]["loc_contract_validated"])
            self.assertEqual(manifest["checks"]["loc_valid_sector_count"], 2)
            result = json.loads(
                (output / "perfil_v3_rural01_resultado.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                [row["profile_score"] for row in result["operational_rows"]],
                [row["territorial_score"] for row in result["operational_rows"]],
            )
            self.assertEqual(result["operational_status"], "ABSTENCAO_PERFIL")
            case = json.loads(
                (output / "protocolo_integrado_rural01_congelado.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                case["source_artifacts"]["visual_manifest_sha256"],
                MODULE._sha256(visual_manifest),
            )
            self.assertEqual(case["visual_evidence"], [])
            integrated = json.loads(
                (output / "resultado_urg_det_rural01.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                integrated["location"]["status"],
                "RESULTADO_EXTERNO_CONTRATO_VALIDADO_CEGAMENTO_DECLARADO",
            )
            self.assertEqual(len(integrated["location"]["valid_sector_ids"]), 2)

            first_run = {
                path.name: path.read_bytes()
                for path in output.iterdir()
                if path.is_file()
            }
            MODULE.build_package(
                ranking,
                polygons,
                visual_manifest,
                output,
                "2026-10-22T12:13:12-03:00",
            )
            second_run = {
                path.name: path.read_bytes()
                for path in output.iterdir()
                if path.is_file()
            }
            self.assertEqual(first_run, second_run)


if __name__ == "__main__":
    unittest.main()
