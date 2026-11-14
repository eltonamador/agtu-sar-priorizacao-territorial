#!/usr/bin/env python3
"""Valida e manifesta a candidata prospectiva do protocolo integrado."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work" / "protocolo_integrado_v1"
OUTPUT = ROOT / "outputs" / "protocolo_integrado_v1"
PROFILE_WORK = ROOT / "work" / "perfil_vitima_v3"
PROFILE_OUTPUT = ROOT / "outputs" / "modulo_perfil_vitima_v3"
PACKAGE_ID = "PROTOCOLO-INTEGRADO-PROSPECTIVO-v1.0-CANDIDATO"


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    qa_path = OUTPUT / "resultado_testes_protocolo_integrado_v1.json"
    manifest_path = OUTPUT / "manifesto_candidato_protocolo_integrado_v1.json"
    qa_path.write_bytes(canonical_bytes({
        "suite_id": "PROTOCOLO-INTEGRADO-v1-ACCEPTANCE",
        "status": "EM_VALIDACAO",
    }))
    manifest_path.write_bytes(canonical_bytes({
        "package_id": PACKAGE_ID,
        "status": "EM_VALIDACAO",
        "urbe_01_modified": False,
        "ground_truth_in_package": False,
        "artifacts": [],
    }))

    json_files = [
        OUTPUT / "entrada_integrada_v1.schema.json",
        OUTPUT / "evento_busca_v1.schema.json",
        OUTPUT / "loc_result_v1.schema.json",
        OUTPUT / "loc_engine_lock_v1.json",
        OUTPUT / "catalogo_regras_urg_v1.json",
        OUTPUT / "visual_metadata_manifest_v1.schema.json",
        OUTPUT / "visual_sector_binding_v1.schema.json",
        OUTPUT / "visual_spatial_policy_v1.json",
        PROFILE_OUTPUT / "config_perfil_quantitativo_v3.json",
        PROFILE_OUTPUT / "perfil_quantitativo_v3.input.schema.json",
        PROFILE_OUTPUT / "perfil_v3_revisao_espacial.schema.json",
    ]
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))

    sys.path.insert(0, str(WORK))
    protocol_suite = unittest.TestLoader().discover(str(WORK), pattern="test*.py")
    profile_suite = unittest.TestLoader().discover(
        str(PROFILE_WORK), pattern="test_profile*.py"
    )
    suite = unittest.TestSuite([protocol_suite, profile_suite])
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    qa = {
        "suite_id": "PROTOCOLO-INTEGRADO-v1-ACCEPTANCE",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "json_contracts_parsed": [path.name for path in json_files],
        "checks": [
            "determinismo",
            "firewall_ground_truth",
            "integridade_pos_congelamento",
            "abstencao_urg",
            "separacao_loc_urg_det",
            "conjunto_a_sem_alvo",
            "resultado_negativo_sem_efeito_loc",
            "testes_adversariais",
            "ordem_independente_urg",
            "proveniencia_temporal",
            "artefatos_e_cadeia_verificados",
            "hash_logico_loc_invariante",
            "contrato_loc_vinculado_a_revisao_e_entrada",
            "setor_det_vinculado_ao_loc_validado",
            "compatibilidade_dominio_evidencia_det",
            "coerencia_perfil_urg",
            "origem_autorizada_do_novo_ponto",
            "coerencia_direcao_azimute",
            "conformidade_limites_schema_runtime",
            "paridade_schema_runtime",
            "vinculo_causal_perfil_entrada_loc_revisao",
            "reexecucao_deterministica_perfil_v3",
            "motor_e_configuracao_loc_congelados_por_hash",
            "det_sem_aptidao_sem_vinculo_espacial_autenticado",
            "midia_validada_apenas_no_limite_estrutural_declarado",
            "metadados_visuais_reextraidos_dos_originais",
            "vinculo_imagem_setor_recalculado_por_intersecao",
            "footprint_aproximado_limita_det_a_apto_com_restricoes",
            "fotografia_solo_ou_obliqua_permanece_contextual",
            "pacote_visual_nao_altera_hash_logico_loc",
            "gpx_segmentos_e_poligonos_com_buracos_preservados",
            "evento_negativo_sem_efeito_loc",
            "cobertura_negativa_sem_elegibilidade_sem_vinculos_espaciais_e_temporais",
        ],
    }
    qa_path.write_bytes(canonical_bytes(qa))

    release_files = [
        WORK / "integrated_protocol.py",
        WORK / "visual_spatial_binding.py",
        WORK / "extract_image_metadata.swift",
        WORK / "test_integrated_protocol.py",
        WORK / "test_protocol_adversarial.py",
        WORK / "test_protocol_cross_module_guards.py",
        WORK / "test_visual_spatial_binding.py",
        WORK / "test_schema_contracts.py",
        WORK / "README.md",
        WORK / "build_release.py",
        PROFILE_WORK / "profile_ranker.py",
        PROFILE_WORK / "profile_integration.py",
        PROFILE_WORK / "test_profile_ranker.py",
        PROFILE_WORK / "test_profile_integration.py",
        *json_files,
        OUTPUT / "Especificacao_Protocolo_Integrado_LOC_URG_DET_v1.md",
        OUTPUT / "Guia_Preenchimento_Proximos_Casos_v1.md",
        qa_path,
    ]
    manifest = {
        "package_id": PACKAGE_ID,
        "status": (
            "CANDIDATO_PROSPECTIVO"
            if result.wasSuccessful()
            else "INVALIDO_TESTES"
        ),
        "urbe_01_modified": False,
        "ground_truth_in_package": False,
        "tests": qa,
        "artifacts": [
            {
                "path": str(path.relative_to(ROOT)),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in sorted(release_files)
        ],
    }
    manifest_path.write_bytes(canonical_bytes(manifest))
    print(json.dumps({"status": qa["status"], "tests_run": qa["tests_run"], "manifest": str(manifest_path)}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
