#!/usr/bin/env python3
"""Consolida e congela o pacote T2 pré-revelação do cenário RURAL-01.

O manifesto agrega apenas artefatos já produzidos pelo núcleo territorial,
pela custódia visual e pelo protocolo PERFIL/LOC/URG/DET. Ele não recebe nem
procura a posição usada na avaliação posterior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
CASE_ROOT = PROJECT_ROOT / "outputs/campo_rural01"
DEFAULT_OUTPUT_DIR = CASE_ROOT / "t2_congelado_final"

CRITICAL_FILES = {
    "custody_manifest": CASE_ROOT / "entrada_cega_v1/manifesto_sha256_conjunto_a.json",
    "visual_metadata_manifest": CASE_ROOT / "entrada_cega_v1/manifesto_metadados_visuais.json",
    "territorial_manifest": CASE_ROOT / "processamento_cego_v1/manifesto_processamento_cego.json",
    "territorial_qa": CASE_ROOT / "processamento_cego_v1/relatorio_qa.json",
    "territorial_determinism": CASE_ROOT / "processamento_cego_v1/relatorio_determinismo.json",
    "territorial_top3": CASE_ROOT / "processamento_cego_v1/top3_rural01.json",
    "profile_protocol_manifest": CASE_ROOT / "perfil_v2_v3/manifesto_perfil_urg_det_rural01.json",
    "profile_report": CASE_ROOT / "perfil_v2_v3/relatorio_perfil_urg_det_rural01.json",
    "integrated_result": CASE_ROOT / "perfil_v2_v3/resultado_urg_det_rural01.json",
    "loc_result": CASE_ROOT / "perfil_v2_v3/loc_result_v1.json",
}


class FreezeError(ValueError):
    """O pacote não satisfaz um controle obrigatório do T2."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError(f"JSON obrigatório inválido: {path}") from exc


def _read_json_snapshot(path: Path) -> dict[str, Any]:
    """Lê bytes uma única vez para validar e selar o mesmo conteúdo."""
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreezeError(f"JSON obrigatório inválido: {path}") from exc
    return {
        "value": value,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FreezeError(message)


def _parse_datetime(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FreezeError("frozen_at deve ser RFC 3339 válido.") from exc
    if parsed.utcoffset() is None:
        raise FreezeError("frozen_at deve conter fuso horário.")
    return parsed.isoformat(timespec="seconds")


def _display_path(path: Path) -> str:
    return path.resolve().relative_to(PROJECT_ROOT).as_posix()


def _payload_hash_valid(document: Mapping[str, Any], field: str) -> bool:
    expected = document.get(field)
    if not isinstance(expected, str):
        return False
    projection = dict(document)
    projection.pop(field, None)
    return hashlib.sha256(_canonical_bytes(projection)).hexdigest() == expected


def _resolve_manifest_entry(
    entry: Mapping[str, Any], manifest_path: Path
) -> Path | None:
    if isinstance(entry.get("path"), str):
        listed = Path(str(entry["path"]))
        return listed if listed.is_absolute() else PROJECT_ROOT / listed
    if isinstance(entry.get("relative_path"), str):
        # Os manifestos visuais definem o caminho relativo à raiz do caso,
        # não ao subdiretório em que o manifesto foi publicado.
        return CASE_ROOT / str(entry["relative_path"])
    return None


def _listed_files_match(
    document: Mapping[str, Any], manifest_path: Path, expected_count: int
) -> bool:
    entries = document.get("files")
    if not isinstance(entries, list) or len(entries) != expected_count:
        return False
    resolved_paths: list[Path] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            return False
        path = _resolve_manifest_entry(entry, manifest_path)
        if path is None:
            return False
        try:
            path.resolve().relative_to(PROJECT_ROOT)
        except ValueError:
            return False
        if not path.is_file():
            return False
        if path.stat().st_size != entry.get("bytes"):
            return False
        if _sha256(path) != entry.get("sha256"):
            return False
        resolved_paths.append(path.resolve())
    return len(set(resolved_paths)) == expected_count


def _critical_snapshots() -> dict[str, dict[str, Any]]:
    for role, path in CRITICAL_FILES.items():
        _require(path.is_file(), f"Artefato obrigatório ausente ({role}): {path}")
    return {role: _read_json_snapshot(path) for role, path in CRITICAL_FILES.items()}


def validate_package(
    snapshots: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, bool], dict[str, Any], dict[str, Mapping[str, Any]]]:
    snapshots = dict(snapshots or _critical_snapshots())
    docs = {role: snapshot["value"] for role, snapshot in snapshots.items()}
    custody = docs["custody_manifest"]
    visual = docs["visual_metadata_manifest"]
    territorial = docs["territorial_manifest"]
    territorial_qa = docs["territorial_qa"]
    determinism = docs["territorial_determinism"]
    top3 = docs["territorial_top3"]
    profile_manifest = docs["profile_protocol_manifest"]
    profile_report = docs["profile_report"]
    integrated = docs["integrated_result"]
    loc_result = docs["loc_result"]

    top3_areas = top3.get("areas", [])
    top3_sector_ids = [area.get("sector_id") for area in top3_areas]
    top3_scores = [area.get("score") for area in top3_areas]
    profile_runs = loc_result.get("profile_runs", [])
    profile_sectors = (
        profile_runs[0].get("profile_input", {}).get("sectors", [])
        if len(profile_runs) == 1
        else []
    )
    profile_top3_sector_ids = [sector.get("sector_id") for sector in profile_sectors[:3]]
    profile_top3_scores = [sector.get("territorial_score") for sector in profile_sectors[:3]]

    checks = {
        "scenario_consistent": all(
            value in (None, "RURAL-01")
            for value in (
                custody.get("scenario_id"),
                visual.get("scenario_id"),
                profile_manifest.get("scenario_id"),
                profile_report.get("scenario_id"),
            )
        ),
        "authorized_visual_file_count_is_15": custody.get("authorized_file_count") == 15
        and custody.get("verified_file_count") == 15
        and len(custody.get("files", [])) == 15,
        "authorized_visual_hashes_match": custody.get("all_hashes_match_frozen_values") is True,
        "custody_payload_hash_valid": _payload_hash_valid(custody, "payload_sha256"),
        "custody_original_files_recomputed": _listed_files_match(
            custody, CRITICAL_FILES["custody_manifest"], 15
        ),
        "visual_manifest_links_exact_custody_file": visual.get("custody_manifest", {}).get(
            "file_sha256"
        )
        == snapshots["custody_manifest"]["sha256"],
        "visual_payload_hash_valid": _payload_hash_valid(visual, "payload_sha256"),
        "visual_file_count_is_15": visual.get("file_count") == 15
        and len(visual.get("records", [])) == 15,
        "visual_temporal_conflict_preserved": visual.get("temporal_review", {}).get(
            "temporal_conflict"
        )
        is True,
        "visual_waits_operator_confirmation": visual.get("temporal_review", {}).get("status")
        == "AWAITING_OPERATOR_CONFIRMATION",
        "visual_has_no_loc_effect": visual.get("global_controls", {}).get("loc_numeric_effect")
        is False,
        "visual_has_no_automatic_footprint": visual.get("global_controls", {}).get(
            "spatial_footprint_authorized"
        )
        is False,
        "territorial_ground_truth_not_used": territorial.get("ground_truth_used") is False,
        "territorial_not_confirmatory": territorial.get("confirmatory_eligible") is False,
        "territorial_radius_is_1500_m": float(territorial.get("radius_m", -1)) == 1500.0,
        "radius_is_source_adjusted_final": territorial.get("r0_semantics")
        == "source_adjusted_final",
        "no_extra_radius_factor_applied": territorial.get(
            "additional_factors_applied_by_engine"
        )
        is False,
        "territorial_sector_count_is_24": territorial.get("sector_count") == 24,
        "territorial_manifest_files_recomputed": _listed_files_match(
            territorial, CRITICAL_FILES["territorial_manifest"], 29
        ),
        "territorial_qa_pass": territorial_qa.get("status") == "PASS"
        and territorial_qa.get("passed_gate_count") == territorial_qa.get("gate_count") == 10,
        "territorial_determinism_pass": determinism.get("status") == "PASS"
        and determinism.get("all_scientific_files_equal") is True,
        "top3_count_is_3": len(top3.get("areas", [])) == 3,
        "top3_is_unique_and_descending": len(set(top3_sector_ids)) == 3
        and all(isinstance(score, (int, float)) for score in top3_scores)
        and top3_scores == sorted(top3_scores, reverse=True),
        "top3_scenario_and_candidate_consistent": all(
            area.get("scenario_id") == "RURAL-01"
            and area.get("candidate_id") == "RURAL-01-E0"
            for area in top3_areas
        ),
        "top3_ground_truth_not_used": top3.get("ground_truth_used") is False
        and all(area.get("ground_truth_used") is False for area in top3.get("areas", [])),
        "profile_abstained": profile_report.get("profile_v3", {}).get("abstained") is True,
        "profile_manifest_files_recomputed": _listed_files_match(
            profile_manifest, CRITICAL_FILES["profile_protocol_manifest"], 14
        ),
        "profile_preserved_territorial_ranking": profile_report.get("profile_v3", {}).get(
            "territorial_ranking_preserved_exactly"
        )
        is True,
        "north_hypothesis_not_weighted": profile_report.get("profile_v3", {}).get(
            "north_hypothesis_weighted"
        )
        is False,
        "loc_contract_validated": profile_report.get("loc", {}).get("status")
        == "RESULTADO_EXTERNO_CONTRATO_VALIDADO_CEGAMENTO_DECLARADO"
        and profile_report.get("loc", {}).get("valid_sector_count") == 24,
        "loc_artifact_is_blind_and_ground_truth_free": loc_result.get("scenario_id")
        == "RURAL-01"
        and loc_result.get("blind_processing") is True
        and loc_result.get("ground_truth_used") is False,
        "loc_profile_has_one_candidate_and_24_sectors": len(profile_runs) == 1
        and profile_runs[0].get("candidate_id") == "RURAL-01-E0"
        and len(profile_sectors) == 24,
        "loc_top3_matches_frozen_territorial_top3": profile_top3_sector_ids
        == top3_sector_ids
        and profile_top3_scores == top3_scores,
        "urgency_is_priority_review": profile_report.get("urg", {}).get("status")
        == "REVISAO_PRIORITARIA"
        and profile_report.get("urg", {}).get("affects_loc") is False,
        "detectability_is_review_only": profile_report.get("det", {}).get("compiled_statuses")
        == ["REVISAR"]
        and profile_report.get("det", {}).get("affects_loc") is False,
        "integrated_artifacts_verified": integrated.get("artifact_verification", {}).get("status")
        == "VERIFIED",
        "integrated_output_hash_valid": _payload_hash_valid(integrated, "output_sha256"),
        "integrated_result_is_blind_and_ground_truth_free": integrated.get("scenario_id")
        == "RURAL-01"
        and integrated.get("blind_processing") is True
        and integrated.get("ground_truth_used") is False
        and integrated.get("storage_segregated") is True,
        "integrated_loc_separate_from_urg_det": integrated.get("location", {}).get(
            "affected_by_urgency"
        )
        is False
        and integrated.get("location", {}).get("affected_by_detectability") is False,
        "meal_and_medication_not_invented": profile_manifest.get("checks", {}).get(
            "medication_or_meal_timing_invented"
        )
        is False,
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    _require(not failed, "Falha nos controles T2: " + ", ".join(failed))
    return checks, docs, snapshots


def build_package(
    output_dir: Path,
    frozen_at: str,
    frozen_at_source: str = "SYSTEM_CLOCK_AMERICA_BELEM",
) -> dict[str, Any]:
    frozen_at = _parse_datetime(frozen_at)
    output_dir = output_dir.resolve()
    try:
        output_dir.relative_to(CASE_ROOT)
    except ValueError as exc:
        raise FreezeError("O pacote T2 deve permanecer dentro de outputs/campo_rural01.") from exc
    _require(not output_dir.exists(), f"Destino T2 já existe e não pode ser sobrescrito: {output_dir}")

    snapshots = _critical_snapshots()
    checks, docs, snapshots = validate_package(snapshots)

    file_entries = [
        {
            "role": role,
            "path": _display_path(path),
            "sha256": snapshots[role]["sha256"],
            "bytes": snapshots[role]["bytes"],
        }
        for role, path in sorted(CRITICAL_FILES.items())
    ]
    freezer_entry = {
        "role": "t2_freezer_script",
        "path": _display_path(Path(__file__)),
        "sha256": _sha256(Path(__file__)),
        "bytes": Path(__file__).stat().st_size,
    }
    package_projection = {
        "scenario_id": "RURAL-01",
        "frozen_at": frozen_at,
        "frozen_at_source": frozen_at_source,
        "files": file_entries + [freezer_entry],
        "checks": checks,
    }
    package_sha256 = hashlib.sha256(_canonical_bytes(package_projection)).hexdigest()

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir.parent / f".{output_dir.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
    staging_dir.mkdir(parents=False, exist_ok=False)
    try:
        qa_path = staging_dir / "relatorio_qa_t2_rural01.json"
        qa = {
            "scenario_id": "RURAL-01",
            "stage": "T2_PRE_REVELACAO",
            "status": "PASS",
            "check_count": len(checks),
            "passed_check_count": sum(checks.values()),
            "checks": checks,
        }
        _write_json(qa_path, qa)

        core_top3 = docs["territorial_top3"]["areas"]
        report_path = staging_dir / "resumo_t2_rural01.md"
        report_lines = [
            "# RURAL-01 — congelamento T2 pré-revelação",
            "",
            f"- instante de congelamento: `{frozen_at}`;",
            f"- fonte do instante: `{frozen_at_source}`;",
            "- entrada espacial: um ponto de planejamento e raio direto de 1.500 m informado pela fonte;",
            "- setores avaliados: 24;",
            "- posição de avaliação utilizada: não;",
            "- perfil: abstenção, sem mudança do ranking territorial;",
            "- urgência: revisão prioritária;",
            "- detectabilidade: revisar;",
            "- fotografias: contexto sem efeito LOC e sem footprint automático;",
            "- divergência temporal das fotografias: preservada e pendente de confirmação.",
            "",
            "## Áreas prioritárias congeladas",
            "",
            "| Área | Setor | Direção | Anel | Escore |",
            "|---|---|---|---|---:|",
        ]
        for area in core_top3:
            report_lines.append(
                "| {area_label} | {sector_id} | {direction} | {ring_id} | {score:.9f} |".format(
                    **area
                )
            )
        report_lines.extend(
            [
                "",
                "As áreas são prioridades analíticas relativas dentro do raio informado. Não representam probabilidade de presença nem determinação autônoma de localização.",
                "",
            ]
        )
        report_path.write_text("\n".join(report_lines), encoding="utf-8")

        final_qa_path = output_dir / qa_path.name
        final_report_path = output_dir / report_path.name
        manifest_path = staging_dir / "manifesto_t2_rural01.json"
        manifest = {
            "manifest_version": "RURAL01-T2-PRE-REVEAL-v1.1",
            "scenario_id": "RURAL-01",
            "stage": "T2_PRE_REVELACAO",
            "status": "CONGELADO_PASS",
            "frozen_at": frozen_at,
            "frozen_at_source": frozen_at_source,
            "blind_processing": True,
            "storage_segregated": True,
            "ground_truth_used": False,
            "evaluation_position_received_in_package": False,
            "evaluation_may_start_after_this_manifest": True,
            "temporal_conflict_pending": True,
            "immutable_destination": True,
            "scientific_package_sha256": package_sha256,
            "files": file_entries
            + [
                freezer_entry,
                {
                    "role": "t2_quality_report",
                    "path": _display_path(final_qa_path),
                    "sha256": _sha256(qa_path),
                    "bytes": qa_path.stat().st_size,
                },
                {
                    "role": "t2_human_readable_summary",
                    "path": _display_path(final_report_path),
                    "sha256": _sha256(report_path),
                    "bytes": report_path.stat().st_size,
                },
            ],
            "checks": checks,
            "payload_sha256": "0" * 64,
        }
        projection = dict(manifest)
        projection.pop("payload_sha256")
        manifest["payload_sha256"] = hashlib.sha256(_canonical_bytes(projection)).hexdigest()
        _write_json(manifest_path, manifest)
        staging_dir.replace(output_dir)
        return manifest
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    frozen_at = datetime.now(ZoneInfo("America/Belem")).isoformat(timespec="seconds")
    result = build_package(
        args.output_dir.resolve(),
        frozen_at,
        "SYSTEM_CLOCK_AMERICA_BELEM",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
