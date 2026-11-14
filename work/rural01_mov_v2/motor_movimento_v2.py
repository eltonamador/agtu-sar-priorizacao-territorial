#!/usr/bin/env python3
"""Motor cego de resistência e custo acumulado do cenário RURAL-01.

Esta extensão preserva integralmente o processamento territorial v1. Ela cria
uma grade regular de 30 m sobre o raio recebido de 1.500 m e calcula caminhos
de menor custo físico a partir do ponto inicial. O custo é expresso em metros
equivalentes de esforço; não é tempo, probabilidade de presença, localização
da pessoa nem ordem operacional.

Entradas locais:
* SRTM/Mapzen (elevação e gradiente entre células);
* ESA WorldCover 2021 (classe de cobertura);
* OpenStreetMap congelado (vias, trilhas e hidrografia);
* setores e ranking territorial cegos da v1.

As transformações de resistência são hipóteses heurísticas de desenvolvimento
declaradas na configuração. A composição principal desduplica hidrografia OSM
quando a própria classe WorldCover já representa água ou área úmida. Vegetação
vista de cima não prova transitabilidade do sub-bosque; por isso a saída mantém
revisão de campo obrigatória.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import importlib.util
import json
import math
import platform
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
V1_ENGINE_PATH = PROJECT_ROOT / "work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py"
DEFAULT_CONFIG_PATH = HERE / "config_mov_v2.json"
DEFAULT_PROTOCOL_PATH = HERE / "PROTOCOLO_RURAL01_MOVIMENTO_CEGO_v2_CONGELADO.md"
DEFAULT_V1_DIR = PROJECT_ROOT / "outputs/campo_rural01/processamento_cego_v1"
DEFAULT_GEO_DIR = PROJECT_ROOT / "outputs/sprint2_s2_06_geo05_v33"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/campo_rural01/processamento_movimento_cego_v2"
TEST_SUITE_PATH = HERE / "test_motor_movimento_v2.py"
TEST_RUNNER_PATH = HERE / "run_tests_with_receipt.py"
DEFAULT_TEST_RECEIPT_PATH = DEFAULT_OUTPUT_DIR / "relatorio_testes_mov_v2.json"

MANDATORY_FORBIDDEN_FRAGMENTS = {
    "ground_truth_lat",
    "ground_truth_lon",
    "ground_truth_longitude",
    "ground_truth_sector",
    "truth_",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "real_lat",
    "real_lon",
    "victim_lat",
    "victim_lon",
    "target_lat",
    "target_lon",
    "distance_to_truth",
    "distance_to_ground_truth",
    "distance_to_reference",
    "sector_contains_truth",
    "correct_sector",
    "evaluation_latitude",
    "evaluation_longitude",
}

SAFE_BLIND_CONTROL_VALUES = {
    "ground_truth_used": False,
    "ground_truth_used_required_value": False,
    "ground_truth_available_to_engine": False,
    "include_ground_truth_payload": False,
    "freeze_before_ground_truth_opening": True,
    "parameter_change_after_truth_opening": "FORBIDDEN",
}

DIRECTIONS_D8 = (
    (-1, -1, math.sqrt(2.0)),
    (-1, 0, 1.0),
    (-1, 1, math.sqrt(2.0)),
    (0, -1, 1.0),
    (0, 1, 1.0),
    (1, -1, math.sqrt(2.0)),
    (1, 0, 1.0),
    (1, 1, math.sqrt(2.0)),
)

COST_SEMANTICS = "METROS_EQUIVALENTES_DE_ESFORCO_NAO_TEMPO_NAO_PROBABILIDADE"
ENGINE_VERSION = "2.0.3-rural01-mov-v-t4"

HYDRO_OVERLAP_POLICY = "NO_MULTIPLY_OSM_HYDRO_ON_WORLDCOVER_WATER_WETLAND"
NETWORK_OVERLAP_POLICY = "MULTIPLICATIVE_DISCOUNT_WITH_SCALE_CONFLICT_DIAGNOSTIC"
HYDRO_DUPLICATION_COUNTERFACTUAL_ID = "COM_DUPLICACAO_HIDRO_COBERTURA"


def reference_cost_scenario_id(config: Mapping[str, Any]) -> str:
    """Cenário técnico explícito, usado apenas para controles comparativos.

    Ele não representa seleção da hipótese operacional. A ausência da
    declaração é erro de contrato, evitando qualquer fallback silencioso.
    """
    reference = config.get("reference_cost_scenario")
    if not isinstance(reference, Mapping) or not reference.get("cost_scenario_id"):
        raise MovementContractError("reference_cost_scenario explícito ausente")
    return str(reference["cost_scenario_id"])


def development_status(config: Mapping[str, Any]) -> str:
    return str(config.get("resistance", {}).get("status", "HEURISTICA_DESENVOLVIMENTO"))


class MovementContractError(ValueError):
    """Falha de contrato, fonte, configuração ou firewall metodológico."""


@dataclass
class Cell:
    """Célula da superfície de resistência em coordenadas locais."""

    row: int
    col: int
    x_m: float
    y_m: float
    lat: float
    lon: float
    radial_distance_m: float
    elevation_m: float | None = None
    slope_deg: float | None = None
    relief_3x3_m: float | None = None
    worldcover_code: int | None = None
    road: bool = False
    trail: bool = False
    hydro_severity: float = 0.0
    hydro_category: str | None = None
    field_obstacle_factor: float = 1.0
    field_obstacle_class: str | None = None
    sector_id: str | None = None
    v1_score: float | None = None
    v1_rank: int | None = None
    costs: dict[str, float] = field(default_factory=dict)
    predecessors: dict[str, tuple[int, int] | None] = field(default_factory=dict)


def _load_v1_engine() -> Any:
    spec = importlib.util.spec_from_file_location("mov_v2_v1_engine", V1_ENGINE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível importar o motor-base: {V1_ENGINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fields})


def _normalize_firewall_text(value: Any) -> tuple[str, str]:
    raw = str(value).casefold()
    normalized = "".join(char if char.isalnum() else "_" for char in raw).strip("_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized, normalized.replace("_", "")


def _firewall_excluded(path: str, excludes: Sequence[str]) -> bool:
    clean = path[2:] if path.startswith("$.") else path.lstrip("$")
    return any(clean == item or clean.startswith(f"{item}.") or clean.startswith(f"{item}[") for item in excludes)


def _firewall_policy(config: Mapping[str, Any] | None) -> tuple[set[str], tuple[str, ...]]:
    policy = config.get("firewall", {}) if isinstance(config, Mapping) else {}
    configured = policy.get("forbidden_fragments", []) if isinstance(policy, Mapping) else []
    fragments = {str(value).casefold() for value in configured} | set(MANDATORY_FORBIDDEN_FRAGMENTS)
    requested_excludes = tuple(str(value) for value in policy.get("scan_excludes", [])) if isinstance(policy, Mapping) else ()
    allowed_excludes = {
        "firewall.forbidden_fragments",
        "firewall.allowed_control_field",
        "firewall.allowed_control_fields",
        "firewall.scan_excludes",
        "qa.required_checks",
        "post_freeze_evaluation.prespecified_metrics",
    }
    if any(value not in allowed_excludes for value in requested_excludes):
        unknown = sorted(set(requested_excludes) - allowed_excludes)
        raise MovementContractError(f"Exclusão ampla ou desconhecida no firewall: {', '.join(unknown)}")
    return fragments, requested_excludes


def enforce_blind_firewall(
    value: Any,
    config: Mapping[str, Any] | None = None,
    *,
    source_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Varre recursivamente chaves, textos e caminhos do processamento cego.

    A função falha na primeira violação e, quando passa, devolve um recibo
    mensurável para que o QA não dependa de um ``True`` codificado à mão.
    """
    fragments, excludes = _firewall_policy(config)
    normalized_fragments = [_normalize_firewall_text(fragment) for fragment in sorted(fragments)]
    counts = {"keys": 0, "strings": 0, "paths": 0}

    def check_token(token: Any, path: str, kind: str) -> None:
        normalized, compact = _normalize_firewall_text(token)
        for fragment_normalized, fragment_compact in normalized_fragments:
            if not fragment_normalized:
                continue
            if fragment_normalized in normalized or fragment_compact in compact:
                raise MovementContractError(f"Conteúdo proibido no processamento cego ({kind}): {path}")

    def walk(node: Any, path: str = "$") -> None:
        if _firewall_excluded(path, excludes):
            return
        if isinstance(node, Mapping):
            for key, item in node.items():
                child = f"{path}.{key}"
                counts["keys"] += 1
                normalized_key, _ = _normalize_firewall_text(key)
                if normalized_key in SAFE_BLIND_CONTROL_VALUES:
                    expected = SAFE_BLIND_CONTROL_VALUES[normalized_key]
                    matches_expected = item == expected
                    if isinstance(expected, bool) and isinstance(item, str):
                        matches_expected = item.casefold() == str(expected).casefold()
                    if not matches_expected:
                        raise MovementContractError(f"Controle cego inválido em {child}: esperado {expected!r}")
                else:
                    check_token(key, child, "chave")
                walk(item, child)
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
        elif isinstance(node, str):
            counts["strings"] += 1
            check_token(node, path, "texto")
        elif isinstance(node, Path):
            counts["paths"] += 1
            check_token(str(node), path, "caminho")

    walk(value)
    for index, source_path in enumerate(source_paths):
        counts["paths"] += 1
        check_token(str(source_path), f"$paths[{index}]", "caminho")
    return {
        "status": "PASS",
        "scanned_key_count": counts["keys"],
        "scanned_string_count": counts["strings"],
        "scanned_path_count": counts["paths"],
        "forbidden_alias_count": len(fragments),
        "rules_sha256": canonical_hash(sorted(fragments)),
    }


def combine_firewall_receipts(receipts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not receipts or any(receipt.get("status") != "PASS" for receipt in receipts):
        raise MovementContractError("Recibos do firewall ausentes ou inválidos")
    rule_hashes = {str(receipt.get("rules_sha256")) for receipt in receipts}
    if len(rule_hashes) != 1:
        raise MovementContractError("Recibos do firewall usam regras divergentes")
    return {
        "status": "PASS",
        "scan_batch_count": len(receipts),
        "scanned_key_count": sum(int(receipt.get("scanned_key_count", 0)) for receipt in receipts),
        "scanned_string_count": sum(int(receipt.get("scanned_string_count", 0)) for receipt in receipts),
        "scanned_path_count": sum(int(receipt.get("scanned_path_count", 0)) for receipt in receipts),
        "forbidden_alias_count": max(int(receipt.get("forbidden_alias_count", 0)) for receipt in receipts),
        "rules_sha256": rule_hashes.pop(),
    }


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    firewall_receipt = enforce_blind_firewall(config, config)
    blind = config.get("blind_control")
    if not isinstance(blind, Mapping):
        raise MovementContractError("blind_control ausente")
    required_blind_flags = {
        "blind_processing": True,
        "ground_truth_used": False,
        "reference_package_accessible_to_engine": False,
        "reference_opening_allowed_only_after_T4": True,
    }
    for key, expected in required_blind_flags.items():
        if blind.get(key) is not expected:
            raise MovementContractError(f"blind_control.{key} deve ser {expected!r}")
    firewall = config.get("firewall")
    if not isinstance(firewall, Mapping):
        raise MovementContractError("firewall ausente")
    required_firewall_flags = {
        "enabled": True,
        "recursive": True,
        "case_insensitive": True,
        "ground_truth_used_required_value": False,
        "open_reference_only_after_output_freeze": True,
    }
    for key, expected in required_firewall_flags.items():
        if firewall.get(key) is not expected:
            raise MovementContractError(f"firewall.{key} deve ser {expected!r}")
    if firewall.get("violation_policy") != "ABORT_EXECUTION":
        raise MovementContractError("firewall.violation_policy deve ser ABORT_EXECUTION")
    configured_aliases = {str(value).casefold() for value in firewall.get("forbidden_fragments", [])}
    if not MANDATORY_FORBIDDEN_FRAGMENTS <= configured_aliases:
        missing = sorted(MANDATORY_FORBIDDEN_FRAGMENTS - configured_aliases)
        raise MovementContractError(f"Aliases obrigatórios ausentes do firewall: {', '.join(missing)}")
    source = config.get("source")
    if not isinstance(source, Mapping):
        raise MovementContractError("source ausente")
    if source.get("ground_truth_available_to_engine") is not False:
        raise MovementContractError("A fonte deve declarar ground_truth_available_to_engine=false")
    if config.get("outputs", {}).get("include_ground_truth_payload") is not False:
        raise MovementContractError("outputs.include_ground_truth_payload deve ser false")
    if config.get("freeze", {}).get("freeze_before_ground_truth_opening") is not True:
        raise MovementContractError("freeze_before_ground_truth_opening deve ser true")
    if config.get("freeze", {}).get("configuration_change_requires_new_version") is not True:
        raise MovementContractError("Mudança de configuração deve exigir nova versão")
    if config.get("post_freeze_evaluation", {}).get("enabled_before_reference_opening") is not False:
        raise MovementContractError("A avaliação de referência deve permanecer desativada antes da abertura")
    if config.get("post_freeze_evaluation", {}).get("retuning_after_reference_opening") is not False:
        raise MovementContractError("Retuning após abertura de referência deve permanecer proibido")
    if config.get("guardrails", {}).get("parameter_change_after_truth_opening") != "FORBIDDEN":
        raise MovementContractError("Mudança de parâmetro após abertura deve permanecer proibida")
    if config.get("guardrails", {}).get("development_only") is not True:
        raise MovementContractError("A configuração deve permanecer development_only")
    if config.get("guardrails", {}).get("confirmatory_eligible") is not False:
        raise MovementContractError("guardrails.confirmatory_eligible deve ser false")
    if not str(config.get("resistance", {}).get("status", "")).startswith("HEURISTICA_DESENVOLVIMENTO"):
        raise MovementContractError("A resistência deve ser declarada como heurística de desenvolvimento")
    if source.get("scenario_id") != "RURAL-01" or source.get("candidate_id") != "RURAL-01-E0":
        raise MovementContractError("Identidade do cenário divergente")
    point = source.get("point", {})
    lat = float(point["latitude"])
    lon = float(point["longitude"])
    radius = float(source["radius_m"])
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise MovementContractError("Coordenada inicial fora do domínio")
    if not math.isclose(radius, 1500.0, abs_tol=1e-9):
        raise MovementContractError("RURAL-01 v2 deve preservar o raio recebido de 1.500 m")
    if float(source.get("elapsed_hours", 0.0)) != 14.0 or source.get("elapsed_time_role") != "CONTEXTO_SEM_CONVERSAO_AUTOMATICA_EM_DISTANCIA_OU_CUSTO":
        raise MovementContractError("A janela contextual deve ser exatamente 14 h")
    grid = config.get("grid", {})
    resolution = float(grid.get("resolution_m", 0.0))
    budget = float(grid.get("movement_budget_cost_m", 0.0))
    if resolution <= 0 or radius / resolution > 200:
        raise MovementContractError("Resolução de grade inválida")
    if not math.isclose(budget, radius, abs_tol=1e-9):
        raise MovementContractError("O orçamento primário deve reutilizar o raio-fonte sem expansão")
    if config.get("scope", {}).get("output_unit") != "cost_m_equivalent" or config.get("scope", {}).get("output_is_probability") is not False:
        raise MovementContractError("Semântica do custo ausente ou divergente")
    hypotheses = config.get("hypotheses")
    profiles = config.get("sensitivity_profiles")
    if not isinstance(hypotheses, list) or len(hypotheses) < 2:
        raise MovementContractError("São exigidas ao menos duas hipóteses de rede")
    if not isinstance(profiles, list) or not any(item.get("id") == "BASE" for item in profiles):
        raise MovementContractError("Perfil de sensibilidade BASE ausente")
    scenario_ids = set()
    for hypothesis in hypotheses:
        if not isinstance(hypothesis.get("apply_network_discount"), bool):
            raise MovementContractError("apply_network_discount deve ser booleano")
        for profile in profiles:
            scenario_id = f"{hypothesis['id']}__{profile['id']}"
            if scenario_id in scenario_ids:
                raise MovementContractError(f"Cenário de custo duplicado: {scenario_id}")
            scenario_ids.add(scenario_id)
    if "primary_cost_scenario_id" in config:
        raise MovementContractError("primary_cost_scenario_id legado é proibido; não pode haver seleção implícita")
    selection = config.get("scenario_selection")
    if not isinstance(selection, Mapping):
        raise MovementContractError("scenario_selection ausente")
    if selection.get("selected_cost_scenario_id") is not None:
        raise MovementContractError("Nenhum cenário pode ser selecionado com regime de rota desconhecido")
    if selection.get("implicit_selection_forbidden") is not True or selection.get("base_profile_id") != "BASE":
        raise MovementContractError("Contrato de seleção simétrica das hipóteses BASE inválido")
    reference = config.get("reference_cost_scenario")
    if not isinstance(reference, Mapping):
        raise MovementContractError("reference_cost_scenario ausente")
    reference_id = reference_cost_scenario_id(config)
    if reference_id not in scenario_ids:
        raise MovementContractError("Cenário técnico referencial não existe")
    if reference.get("role") != "REFERENCIAL_NAO_SELECIONADO" or reference.get("selected") is not False:
        raise MovementContractError("Cenário técnico deve ser REFERENCIAL_NAO_SELECIONADO")
    landcover = config.get("resistance", {}).get("landcover", {}).get("landcover_by_code", {})
    required_codes = {"10", "20", "30", "40", "50", "60", "70", "80", "90", "95", "100"}
    if set(landcover) != required_codes:
        raise MovementContractError("Mapa WorldCover incompleto")
    if any(float(value) <= 0 for value in landcover.values()):
        raise MovementContractError("Resistências de cobertura devem ser positivas")
    hydro = config.get("resistance", {}).get("hydro", {})
    if hydro.get("overlap_policy") != HYDRO_OVERLAP_POLICY:
        raise MovementContractError("Política explícita de desduplicação hidro/cobertura ausente")
    overlap_codes = hydro.get("deduplicate_with_landcover_codes")
    if not isinstance(overlap_codes, list) or {int(value) for value in overlap_codes} != {80, 90, 95}:
        raise MovementContractError("Classes de desduplicação hidro/cobertura devem ser 80, 90 e 95")
    network = config.get("resistance", {}).get("network", {})
    if network.get("landcover_overlap_policy") != NETWORK_OVERLAP_POLICY:
        raise MovementContractError("Política explícita para conflito de escala rede/cobertura ausente")
    diagnostic_codes = network.get("diagnostic_conflict_landcover_codes")
    if not isinstance(diagnostic_codes, list) or not diagnostic_codes:
        raise MovementContractError("Classes diagnósticas de conflito rede/cobertura ausentes")
    counterfactuals = config.get("counterfactual_runs", [])
    if any(str(value) != HYDRO_DUPLICATION_COUNTERFACTUAL_ID for value in counterfactuals):
        raise MovementContractError("Contrafactual desconhecido")
    return firewall_receipt


def cost_scenarios(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for hypothesis in config["hypotheses"]:
        for profile in config["sensitivity_profiles"]:
            scenarios.append(
                {
                    "scenario_id": f"{hypothesis['id']}__{profile['id']}",
                    "hypothesis_id": hypothesis["id"],
                    "profile_id": profile["id"],
                    "apply_network_discount": bool(hypothesis["apply_network_discount"]),
                    **{key: value for key, value in profile.items() if key != "id"},
                }
            )
    reference_id = reference_cost_scenario_id(config)
    base_reference = next(scenario for scenario in scenarios if scenario["scenario_id"] == reference_id)
    for ablation_id in config.get("ablation_runs", []):
        ablation = dict(base_reference)
        ablation["scenario_id"] = f"ABL__{ablation_id}"
        ablation["profile_id"] = "ABLATION"
        ablation["ablation_id"] = str(ablation_id)
        if ablation_id == "SEM_HIDRO":
            ablation["hydro_max_factor"] = 1.0
        elif ablation_id == "SEM_COBERTURA":
            ablation["disable_landcover"] = True
        elif ablation_id == "SEM_RELEVO":
            ablation["slope_a"] = 0.0
            ablation["slope_b"] = 0.0
            ablation["slope_cap"] = 1.0
        elif ablation_id == "SEM_DESCONTO_REDE":
            ablation["apply_network_discount"] = False
        else:
            raise MovementContractError(f"Ablação desconhecida: {ablation_id}")
        scenarios.append(ablation)
    for counterfactual_id in config.get("counterfactual_runs", []):
        if counterfactual_id != HYDRO_DUPLICATION_COUNTERFACTUAL_ID:
            raise MovementContractError(f"Contrafactual desconhecido: {counterfactual_id}")
        counterfactual = dict(base_reference)
        counterfactual["scenario_id"] = f"SENS__{counterfactual_id}"
        counterfactual["profile_id"] = "CONTRAFACTUAL_NAO_PROMOVIDO"
        counterfactual["counterfactual_id"] = str(counterfactual_id)
        counterfactual["force_hydro_landcover_duplication"] = True
        scenarios.append(counterfactual)
    return scenarios


def make_grid(v1: Any, config: Mapping[str, Any]) -> tuple[dict[tuple[int, int], Cell], int]:
    source = config["source"]
    resolution = float(config["grid"]["resolution_m"])
    radius = float(source["radius_m"])
    half = int(round(radius / resolution))
    size = half * 2 + 1
    cells: dict[tuple[int, int], Cell] = {}
    for row in range(size):
        y_m = (half - row) * resolution
        for col in range(size):
            x_m = (col - half) * resolution
            distance = math.hypot(x_m, y_m)
            if distance > radius + 1e-9:
                continue
            lat, lon = v1.aeqd_inverse(x_m, y_m, float(source["point"]["latitude"]), float(source["point"]["longitude"]))
            cells[(row, col)] = Cell(
                row=row,
                col=col,
                x_m=round(x_m, 6),
                y_m=round(y_m, 6),
                lat=round(lat, 10),
                lon=round(lon, 10),
                radial_distance_m=round(distance, 6),
            )
    if (half, half) not in cells:
        raise MovementContractError("Célula de origem ausente")
    return cells, half


def _point_segment_distance_xy(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def rasterize_segments(
    v1: Any,
    cells: Mapping[tuple[int, int], Cell],
    half: int,
    segments: Sequence[Any],
    config: Mapping[str, Any],
    mode: str,
) -> None:
    """Rasteriza vias/trilhas ou hidrografia apenas dentro do círculo analisado."""
    source = config["source"]
    resolution = float(config["grid"]["resolution_m"])
    reach = float(config["resistance"]["network"]["rasterization_tolerance_m"])
    lat0 = float(source["point"]["latitude"])
    lon0 = float(source["point"]["longitude"])
    radius = float(source["radius_m"])
    for segment in segments:
        ax, ay = v1.aeqd_forward(segment.a_lat, segment.a_lon, lat0, lon0)
        bx, by = v1.aeqd_forward(segment.b_lat, segment.b_lon, lat0, lon0)
        if min(ax, bx) > radius + reach or max(ax, bx) < -radius - reach:
            continue
        if min(ay, by) > radius + reach or max(ay, by) < -radius - reach:
            continue
        min_col = max(0, int(math.floor((min(ax, bx) - reach) / resolution)) + half)
        max_col = min(2 * half, int(math.ceil((max(ax, bx) + reach) / resolution)) + half)
        min_row = max(0, half - int(math.ceil((max(ay, by) + reach) / resolution)))
        max_row = min(2 * half, half - int(math.floor((min(ay, by) - reach) / resolution)))
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                cell = cells.get((row, col))
                if cell is None:
                    continue
                if _point_segment_distance_xy(cell.x_m, cell.y_m, ax, ay, bx, by) > reach:
                    continue
                if mode == "network":
                    if segment.cls == "trail":
                        cell.trail = True
                    else:
                        cell.road = True
                elif mode == "hydro" and float(segment.severity) >= cell.hydro_severity:
                    cell.hydro_severity = float(segment.severity)
                    cell.hydro_category = str(segment.subtype)
                else:
                    if mode not in {"network", "hydro"}:
                        raise MovementContractError(f"Modo de rasterização desconhecido: {mode}")


def _point_in_ring_xy(point: tuple[float, float], ring: Sequence[Sequence[float]], v1: Any, lat0: float, lon0: float) -> bool:
    polygon = [v1.aeqd_forward(float(lat), float(lon), lat0, lon0) for lon, lat in ring[:-1]]
    return bool(v1._point_in_polygon_or_boundary(point, polygon))


def apply_field_obstacles(
    v1: Any,
    cells: Mapping[tuple[int, int], Cell],
    config: Mapping[str, Any],
    field_obstacles_path: Path | None,
) -> int:
    """Aplica apenas obstáculos observados e fornecidos explicitamente em GeoJSON."""
    if field_obstacles_path is None:
        return 0
    doc = load_json(field_obstacles_path)
    enforce_blind_firewall(doc, config)
    if doc.get("type") != "FeatureCollection":
        raise MovementContractError("Obstáculos de campo devem formar FeatureCollection")
    factors = config["resistance"]["field_obstacle"].get("multipliers")
    if not isinstance(factors, Mapping):
        raise MovementContractError("Configuração não define multiplicadores de obstáculo de campo")
    lat0 = float(config["source"]["point"]["latitude"])
    lon0 = float(config["source"]["point"]["longitude"])
    count = 0
    for feature in doc.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Polygon" or not geometry.get("coordinates"):
            raise MovementContractError("Somente polígonos são aceitos para obstáculos de campo")
        passability = str(feature.get("properties", {}).get("passage_class", "")).upper()
        if passability not in factors:
            raise MovementContractError(f"Classe de passabilidade desconhecida: {passability}")
        factor = float(factors[passability])
        ring = geometry["coordinates"][0]
        for cell in cells.values():
            if _point_in_ring_xy((cell.x_m, cell.y_m), ring, v1, lat0, lon0):
                if factor > cell.field_obstacle_factor:
                    cell.field_obstacle_factor = factor
                    cell.field_obstacle_class = passability
        count += 1
    return count


def sample_rasters(v1: Any, cells: Mapping[tuple[int, int], Cell], config: Mapping[str, Any], dem_dir: Path, worldcover_dir: Path) -> None:
    hgt = v1.HGTSampler(dem_dir)
    worldcover = v1.WorldCoverSampler(worldcover_dir)
    try:
        for cell in cells.values():
            metrics = hgt.metrics(cell.lat, cell.lon)
            if metrics is not None:
                cell.elevation_m = round(float(metrics[0]), 6)
                cell.slope_deg = round(float(metrics[1]), 6)
                cell.relief_3x3_m = round(float(metrics[2]), 6)
            # WorldCover tem resolução nominal de 10 m. A classe da célula de
            # 30 m é a maioria determinística de nove amostras centrais de
            # subcélula; em empate vence o menor código.
            codes: list[int] = []
            lat0 = float(config["source"]["point"]["latitude"])
            lon0 = float(config["source"]["point"]["longitude"])
            for dy in (-10.0, 0.0, 10.0):
                for dx in (-10.0, 0.0, 10.0):
                    sample_lat, sample_lon = v1.aeqd_inverse(cell.x_m + dx, cell.y_m + dy, lat0, lon0)
                    code = worldcover.sample(sample_lat, sample_lon)
                    if code is not None:
                        codes.append(int(code))
            if codes:
                counts = {code: codes.count(code) for code in sorted(set(codes))}
                cell.worldcover_code = min(counts, key=lambda code: (-counts[code], code))
    finally:
        worldcover.close()
    missing_worldcover = [f"R{cell.row:03d}C{cell.col:03d}" for cell in cells.values() if cell.worldcover_code is None]
    if missing_worldcover:
        preview = ", ".join(missing_worldcover[:5])
        raise MovementContractError(
            f"WorldCover ausente em {len(missing_worldcover)} células ({preview}); "
            "missing_cell_policy=INVALID_AND_REVIEW"
        )


def attach_v1_sectors(
    v1: Any,
    cells: Mapping[tuple[int, int], Cell],
    sectors_path: Path,
    ranking_path: Path,
    config: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], list[tuple[str, list[tuple[float, float]]]]]:
    sectors_doc = load_json(sectors_path)
    enforce_blind_firewall(sectors_doc, config)
    lat0 = float(config["source"]["point"]["latitude"])
    lon0 = float(config["source"]["point"]["longitude"])
    polygons: list[tuple[str, list[tuple[float, float]]]] = []
    for feature in sectors_doc.get("features", []):
        sector_id = str(feature.get("properties", {}).get("sector_id") or feature.get("id"))
        ring = feature.get("geometry", {}).get("coordinates", [[]])[0]
        if len(ring) < 4:
            raise MovementContractError(f"Geometria setorial inválida: {sector_id}")
        polygon = [v1.aeqd_forward(float(lat), float(lon), lat0, lon0) for lon, lat in ring[:-1]]
        polygons.append((sector_id, polygon))
    ranking: dict[str, Mapping[str, Any]] = {}
    with ranking_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            ranking[str(row["sector_id"])] = row
    enforce_blind_firewall(ranking, config)
    for cell in cells.values():
        matches = [sector_id for sector_id, polygon in polygons if v1._point_in_polygon_or_boundary((cell.x_m, cell.y_m), polygon)]
        if matches:
            cell.sector_id = sorted(matches)[0]
        else:
            # Alguns centros de célula exatamente no raio técnico de 1.500 m
            # ficam poucos milímetros fora do polígono geodésico discretizado
            # da v1. Nesses casos, reutilizamos a mesma regra polar da v1 em
            # vez de descartar a célula ou aumentar silenciosamente o domínio.
            index = v1._sector_index_for_xy(cell.x_m, cell.y_m, float(config["source"]["radius_m"]))
            if index is not None:
                directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
                ring_index, direction_index = divmod(index, 8)
                fallback = f"{config['source']['scenario_id']}::{config['source']['candidate_id']}::R{ring_index + 1:02d}::{directions[direction_index]}"
                if fallback in ranking:
                    cell.sector_id = fallback
        prior = ranking.get(str(cell.sector_id)) if cell.sector_id else None
        if prior:
            cell.v1_score = float(prior["score_base"])
            cell.v1_rank = int(float(prior["rank_base_within_buffer"]))
    if any(cell.sector_id is None for cell in cells.values()):
        missing = sum(cell.sector_id is None for cell in cells.values())
        raise MovementContractError(f"{missing} células não foram associadas aos setores v1")
    return ranking, polygons


def landcover_resistance(cell: Cell, config: Mapping[str, Any], scenario: Mapping[str, Any]) -> float:
    if scenario.get("disable_landcover") is True:
        return 1.0
    table = config["resistance"]["landcover"]["landcover_by_code"]
    if cell.worldcover_code is None:
        raise MovementContractError("Célula sem WorldCover é inválida e exige revisão")
    if str(cell.worldcover_code) not in table:
        raise MovementContractError(f"Classe WorldCover não reconhecida: {cell.worldcover_code}")
    base = float(table[str(cell.worldcover_code)])
    exponent = float(scenario["landcover_exponent"])
    return base**exponent


def hydro_landcover_overlap(cell: Cell, config: Mapping[str, Any]) -> bool:
    """Indica se a célula hídrica já é representada pelo WorldCover.

    A função não afirma que as duas fontes observam exatamente o mesmo objeto;
    ela apenas impede a multiplicação automática de duas proxies hídricas no
    mesmo pixel de análise.
    """
    codes = {int(value) for value in config["resistance"]["hydro"]["deduplicate_with_landcover_codes"]}
    return cell.hydro_severity > 0.0 and cell.worldcover_code in codes


def network_landcover_scale_conflict(cell: Cell, config: Mapping[str, Any]) -> bool:
    """Sinaliza via/trilha estreita inserida em cobertura potencialmente dominante."""
    codes = {int(value) for value in config["resistance"]["network"]["diagnostic_conflict_landcover_codes"]}
    return bool(cell.road or cell.trail) and cell.worldcover_code in codes


def cell_component_factors(cell: Cell, config: Mapping[str, Any], scenario: Mapping[str, Any]) -> dict[str, Any]:
    landcover = landcover_resistance(cell, config, scenario)
    network_factor = 1.0
    if bool(scenario["apply_network_discount"]):
        network = config["resistance"]["network"]
        if cell.road:
            network_factor = float(network["road_factor"])
        elif cell.trail:
            network_factor = float(network["trail_factor"])
    hydro_factor = 1.0
    if cell.hydro_severity > 0.0:
        hydro_max = float(scenario["hydro_max_factor"])
        duplicated_counterfactual = bool(scenario.get("force_hydro_landcover_duplication", False))
        if duplicated_counterfactual or not hydro_landcover_overlap(cell, config):
            hydro_factor = 1.0 + cell.hydro_severity * (hydro_max - 1.0)
    return {
        "landcover_factor": landcover,
        "network_factor": network_factor,
        "hydro_factor": hydro_factor,
        "field_factor": float(cell.field_obstacle_factor),
        "hydro_landcover_overlap": hydro_landcover_overlap(cell, config),
        "hydro_deduplication_applied": hydro_landcover_overlap(cell, config)
        and not bool(scenario.get("force_hydro_landcover_duplication", False)),
        "network_landcover_scale_conflict": network_landcover_scale_conflict(cell, config),
    }


def cell_base_resistance(cell: Cell, config: Mapping[str, Any], scenario: Mapping[str, Any]) -> float:
    factors = cell_component_factors(cell, config, scenario)
    return (
        factors["landcover_factor"]
        * factors["network_factor"]
        * factors["hydro_factor"]
        * factors["field_factor"]
    )


def slope_edge_multiplier(a: Cell, b: Cell, scenario: Mapping[str, Any]) -> float:
    if a.elevation_m is None or b.elevation_m is None:
        raise MovementContractError("Célula sem DEM não pode receber custo favorável")
    horizontal = math.hypot(b.x_m - a.x_m, b.y_m - a.y_m)
    if horizontal <= 0.0:
        return 1.0
    # A arquitetura conserva o sinal do gradiente, mas a configuração BASE
    # aplica abs(grade) e coeficientes iguais nos dois sentidos. Portanto a
    # execução é deliberadamente simétrica e não alega anisotropia calibrada.
    grade_signed = (float(b.elevation_m) - float(a.elevation_m)) / horizontal
    magnitude = abs(grade_signed)
    value = 1.0 + float(scenario["slope_a"]) * magnitude + float(scenario["slope_b"]) * magnitude * magnitude
    return min(float(scenario["slope_cap"]), max(1.0, value))


def dijkstra_cost_surface(
    cells: Mapping[tuple[int, int], Cell],
    origin: tuple[int, int],
    config: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], tuple[int, int] | None]]:
    resolution = float(config["grid"]["resolution_m"])
    scenario_id = str(scenario["scenario_id"])
    base = {key: cell_base_resistance(cell, config, scenario) for key, cell in cells.items()}
    distances = {key: math.inf for key in cells}
    predecessors: dict[tuple[int, int], tuple[int, int] | None] = {origin: None}
    distances[origin] = 0.0
    queue: list[tuple[float, int, int]] = [(0.0, origin[0], origin[1])]
    while queue:
        current, row, col = heapq.heappop(queue)
        key = (row, col)
        if current != distances[key]:
            continue
        for dr, dc, step_factor in DIRECTIONS_D8:
            neighbor_key = (row + dr, col + dc)
            neighbor = cells.get(neighbor_key)
            if neighbor is None:
                continue
            cell = cells[key]
            # A configuração congelável define os fatores da célula de
            # destino j. O relevo é calculado na aresta i→j.
            edge_base = base[neighbor_key]
            edge_slope = slope_edge_multiplier(cell, neighbor, scenario)
            increment = resolution * step_factor * edge_base * edge_slope
            candidate = current + increment
            if candidate + 1e-12 < distances[neighbor_key]:
                distances[neighbor_key] = candidate
                predecessors[neighbor_key] = key
                heapq.heappush(queue, (candidate, neighbor_key[0], neighbor_key[1]))
    for key, cell in cells.items():
        cell.costs[scenario_id] = round(distances[key], 6)
        cell.predecessors[scenario_id] = predecessors.get(key)
    return distances, predecessors


def reconstruct_path(
    endpoint: tuple[int, int],
    predecessors: Mapping[tuple[int, int], tuple[int, int] | None],
) -> list[tuple[int, int]]:
    if endpoint not in predecessors:
        return []
    path = [endpoint]
    seen = {endpoint}
    cursor = endpoint
    while predecessors.get(cursor) is not None:
        cursor = predecessors[cursor]  # type: ignore[assignment]
        if cursor in seen:
            raise MovementContractError("Ciclo inesperado no caminho de menor custo")
        seen.add(cursor)
        path.append(cursor)
    path.reverse()
    return path


def nearest_cell(cells: Mapping[tuple[int, int], Cell], lat: float, lon: float, v1: Any, config: Mapping[str, Any]) -> tuple[int, int]:
    x, y = v1.aeqd_forward(lat, lon, float(config["source"]["point"]["latitude"]), float(config["source"]["point"]["longitude"]))
    return min(cells, key=lambda key: (cells[key].x_m - x) ** 2 + (cells[key].y_m - y) ** 2)


def _quantile(values: Sequence[float], fraction: float) -> float | None:
    finite = sorted(value for value in values if math.isfinite(value))
    if not finite:
        return None
    position = fraction * (len(finite) - 1)
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return finite[lo]
    weight = position - lo
    return finite[lo] * (1.0 - weight) + finite[hi] * weight


def select_rank_band(rows: Sequence[Mapping[str, Any]], cutoff: int = 3) -> list[Mapping[str, Any]]:
    """Seleciona toda a faixa de ranks até o corte, preservando empates."""
    if cutoff < 1:
        raise MovementContractError("O corte de rank deve ser positivo")
    ordered = sorted(
        rows,
        key=lambda row: (int(row["mobility_rank_within_buffer"]), str(row["sector_id"])),
    )
    return [row for row in ordered if int(row["mobility_rank_within_buffer"]) <= cutoff]


def sector_summaries(cells: Mapping[tuple[int, int], Cell], config: Mapping[str, Any], scenarios: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    budget = float(config["grid"]["movement_budget_cost_m"])
    groups: dict[str, list[Cell]] = defaultdict(list)
    for cell in cells.values():
        if cell.sector_id is not None:
            groups[cell.sector_id].append(cell)
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        for sector_id in sorted(groups):
            sector_cells = groups[sector_id]
            values = [cell.costs[scenario_id] for cell in sector_cells]
            reached = [value for value in values if value <= budget]
            road_fraction = sum(cell.road for cell in sector_cells) / len(sector_cells)
            trail_fraction = sum(cell.trail for cell in sector_cells) / len(sector_cells)
            hydro_fraction = sum(cell.hydro_severity > 0 for cell in sector_cells) / len(sector_cells)
            tree_fraction = sum(cell.worldcover_code in {10, 95} for cell in sector_cells) / len(sector_cells)
            thresholds = config["resistance"]["slope"]["diagnostic_slope_thresholds_deg"]
            steep = float(thresholds[0])
            very_steep = float(thresholds[1])
            valid_slopes = [float(cell.slope_deg) for cell in sector_cells if cell.slope_deg is not None]
            steep_fraction = sum(value >= steep for value in valid_slopes) / len(valid_slopes) if valid_slopes else None
            very_steep_fraction = sum(value >= very_steep for value in valid_slopes) / len(valid_slopes) if valid_slopes else None
            reachable_fraction = len(reached) / len(values)
            accessibility_index = sum(math.exp(-value / budget) for value in values) / len(values)
            first = sector_cells[0]
            rows.append(
                {
                    "protocol_id": config["protocol_id"],
                    "scenario_id": config["source"]["scenario_id"],
                    "candidate_id": config["source"]["candidate_id"],
                    "cost_scenario_id": scenario_id,
                    "hypothesis_id": scenario["hypothesis_id"],
                    "sensitivity_profile": scenario["profile_id"],
                    "sector_id": sector_id,
                    "cell_count": len(values),
                    "valid_cell_count": len(values),
                    "valid_cell_coverage": 1.0,
                    "reachable_cell_count": len(reached),
                    "reachable_fraction": round(reachable_fraction, 9),
                    "minimum_cost_m_equivalent": round(min(values), 6),
                    "median_cost_m_equivalent": round(float(_quantile(values, 0.5)), 6),
                    "p90_cost_m_equivalent": round(float(_quantile(values, 0.9)), 6),
                    "maximum_cost_m_equivalent": round(max(values), 6),
                    "accessibility_index": round(accessibility_index, 9),
                    "road_cell_fraction": round(road_fraction, 9),
                    "trail_cell_fraction": round(trail_fraction, 9),
                    "hydro_cell_fraction": round(hydro_fraction, 9),
                    "tree_mangrove_cell_fraction": round(tree_fraction, 9),
                    "steep_cell_fraction": round(steep_fraction, 9) if steep_fraction is not None else None,
                    "very_steep_cell_fraction": round(very_steep_fraction, 9) if very_steep_fraction is not None else None,
                    "v1_score": first.v1_score,
                    "v1_rank": first.v1_rank,
                    "cost_semantics": COST_SEMANTICS,
                    "field_confirmation_required": True,
                    "ground_truth_used": False,
                }
            )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["cost_scenario_id"])].append(row)
    for scenario_rows in grouped.values():
        ordered = sorted(
            scenario_rows,
            key=lambda row: (-float(row["accessibility_index"]), -float(row["reachable_fraction"]), str(row["sector_id"])),
        )
        previous_key: tuple[float, float] | None = None
        previous_rank = 0
        for position, row in enumerate(ordered, start=1):
            metric_key = (round(float(row["accessibility_index"]), 9), round(float(row["reachable_fraction"]), 9))
            rank = previous_rank if metric_key == previous_key else position
            row["mobility_rank_within_buffer"] = rank
            previous_key, previous_rank = metric_key, rank
    return sorted(rows, key=lambda row: (str(row["cost_scenario_id"]), int(row["mobility_rank_within_buffer"])))


def cell_rows(cells: Mapping[tuple[int, int], Cell], config: Mapping[str, Any], scenarios: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    budget = float(config["grid"]["movement_budget_cost_m"])
    rows: list[dict[str, Any]] = []
    for key in sorted(cells):
        cell = cells[key]
        row: dict[str, Any] = {
            "scenario_id": config["source"]["scenario_id"],
            "candidate_id": config["source"]["candidate_id"],
            "cell_id": f"R{cell.row:03d}C{cell.col:03d}",
            "row": cell.row,
            "col": cell.col,
            "x_m": cell.x_m,
            "y_m": cell.y_m,
            "lat": cell.lat,
            "lon": cell.lon,
            "radial_distance_m": cell.radial_distance_m,
            "elevation_m": cell.elevation_m,
            "slope_deg": cell.slope_deg,
            "relief_3x3_m": cell.relief_3x3_m,
            "worldcover_code": cell.worldcover_code,
            "road_cell": cell.road,
            "trail_cell": cell.trail,
            "hydro_severity": round(cell.hydro_severity, 6),
            "hydro_category": cell.hydro_category,
            "hydro_landcover_overlap": hydro_landcover_overlap(cell, config),
            "hydro_landcover_overlap_policy": HYDRO_OVERLAP_POLICY,
            "network_landcover_scale_conflict": network_landcover_scale_conflict(cell, config),
            "network_landcover_overlap_policy": NETWORK_OVERLAP_POLICY,
            "field_obstacle_factor": cell.field_obstacle_factor,
            "field_obstacle_class": cell.field_obstacle_class,
            "sector_id": cell.sector_id,
            "v1_score": cell.v1_score,
            "v1_rank": cell.v1_rank,
            "dem_source": "MAPZEN_SKADI_SRTMGL1_LOCAL_SNAPSHOT",
            "landcover_source": "ESA_WORLDCOVER_2021_V200_LOCAL_SNAPSHOT",
            "network_source": "OPENSTREETMAP_LOCAL_SNAPSHOT",
            "hydro_source": "OPENSTREETMAP_LOCAL_SNAPSHOT",
            "source_confidence_class": "CARTOGRAFIA_PUBLICA",
            "understory_observability": "NAO_DISPONIVEL",
            "field_confirmation_required": True,
            "ground_truth_used": False,
        }
        for scenario in scenarios:
            scenario_id = str(scenario["scenario_id"])
            cost = cell.costs[scenario_id]
            factors = cell_component_factors(cell, config, scenario)
            predecessor = cell.predecessors.get(scenario_id)
            if predecessor is None:
                predecessor_direction = "ORIGIN" if cost == 0.0 else None
            else:
                dr = cell.row - predecessor[0]
                dc = cell.col - predecessor[1]
                predecessor_direction = {
                    (-1, -1): "NW",
                    (-1, 0): "N",
                    (-1, 1): "NE",
                    (0, -1): "W",
                    (0, 1): "E",
                    (1, -1): "SW",
                    (1, 0): "S",
                    (1, 1): "SE",
                }.get((dr, dc))
            row[f"cost__{scenario_id}"] = cost
            row[f"reachable__{scenario_id}"] = cost <= budget
            row[f"landcover_factor__{scenario_id}"] = round(factors["landcover_factor"], 9)
            row[f"network_factor__{scenario_id}"] = round(factors["network_factor"], 9)
            row[f"hydro_factor__{scenario_id}"] = round(factors["hydro_factor"], 9)
            row[f"hydro_deduplication_applied__{scenario_id}"] = bool(factors["hydro_deduplication_applied"])
            row[f"field_factor__{scenario_id}"] = round(factors["field_factor"], 9)
            row[f"cell_resistance__{scenario_id}"] = round(cell_base_resistance(cell, config, scenario), 9)
            row[f"predecessor_direction__{scenario_id}"] = predecessor_direction
        rows.append(row)
    return rows


def build_cost_points_geojson(rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any], scenario_id: str) -> dict[str, Any]:
    cost_key = f"cost__{scenario_id}"
    reach_key = f"reachable__{scenario_id}"
    landcover_key = f"landcover_factor__{scenario_id}"
    network_key = f"network_factor__{scenario_id}"
    hydro_key = f"hydro_factor__{scenario_id}"
    field_key = f"field_factor__{scenario_id}"
    resistance_key = f"cell_resistance__{scenario_id}"
    predecessor_key = f"predecessor_direction__{scenario_id}"
    properties_to_keep = {
        "cell_id",
        "sector_id",
        "elevation_m",
        "slope_deg",
        "worldcover_code",
        "road_cell",
        "trail_cell",
        "hydro_severity",
        "hydro_category",
        "hydro_landcover_overlap",
        "hydro_landcover_overlap_policy",
        "network_landcover_scale_conflict",
        "network_landcover_overlap_policy",
        "field_obstacle_factor",
        cost_key,
        reach_key,
        landcover_key,
        network_key,
        hydro_key,
        field_key,
        resistance_key,
        predecessor_key,
        "dem_source",
        "landcover_source",
        "network_source",
        "hydro_source",
        "source_confidence_class",
        "understory_observability",
        "field_confirmation_required",
        "ground_truth_used",
    }
    features = []
    for row in rows:
        props = {key: row.get(key) for key in properties_to_keep}
        props["hydro_deduplication_applied"] = row.get(f"hydro_deduplication_applied__{scenario_id}")
        props["cost_scenario_id"] = scenario_id
        props["cost_semantics"] = COST_SEMANTICS
        features.append(
            {
                "type": "Feature",
                "id": row["cell_id"],
                "properties": props,
                "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            }
        )
    return {
        "type": "FeatureCollection",
        "name": f"RURAL01_MOV_V2_COST_POINTS_{scenario_id}",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "ground_truth_used": False,
        "features": features,
    }


def _cell_polygon(v1: Any, cell: Cell, config: Mapping[str, Any]) -> list[list[float]]:
    half = float(config["grid"]["resolution_m"]) / 2.0
    lat0 = float(config["source"]["point"]["latitude"])
    lon0 = float(config["source"]["point"]["longitude"])
    ring = []
    for dx, dy in ((-half, -half), (half, -half), (half, half), (-half, half), (-half, -half)):
        lat, lon = v1.aeqd_inverse(cell.x_m + dx, cell.y_m + dy, lat0, lon0)
        ring.append([round(lon, 10), round(lat, 10)])
    return ring


def build_reachable_geojson(v1: Any, cells: Mapping[tuple[int, int], Cell], config: Mapping[str, Any], scenarios: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    budget = float(config["grid"]["movement_budget_cost_m"])
    features = []
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        if scenario["profile_id"] != "BASE":
            continue
        polygons = []
        for key in sorted(cells):
            cell = cells[key]
            if cell.costs[scenario_id] <= budget:
                polygons.append([_cell_polygon(v1, cell, config)])
        features.append(
            {
                "type": "Feature",
                "id": scenario_id,
                "properties": {
                    "cost_scenario_id": scenario_id,
                    "hypothesis_id": scenario["hypothesis_id"],
                    "sensitivity_profile": scenario["profile_id"],
                    "movement_budget_cost_m": budget,
                    "cost_semantics": COST_SEMANTICS,
                    "cell_count": len(polygons),
                    "field_confirmation_required": True,
                    "ground_truth_used": False,
                },
                "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "RURAL01_MOV_V2_REACHABLE_BASE",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "ground_truth_used": False,
        "features": features,
    }


def build_corridors_geojson(
    cells: Mapping[tuple[int, int], Cell],
    config: Mapping[str, Any],
    scenarios: Sequence[Mapping[str, Any]],
    sectors_doc: Mapping[str, Any],
    top3_doc: Mapping[str, Any],
    v1: Any,
    configuration_sha256: str,
) -> dict[str, Any]:
    features = []
    base_scenarios = [scenario for scenario in scenarios if scenario["profile_id"] == "BASE"]
    top3_by_sector = {str(area["sector_id"]): area for area in top3_doc.get("areas", [])}
    sector_targets = []
    for feature in sectors_doc.get("features", []):
        props = feature.get("properties", {})
        sector_id = str(props.get("sector_id") or feature.get("id"))
        sector_targets.append(
            {
                "sector_id": sector_id,
                "representative_lat": float(props["representative_lat"]),
                "representative_lon": float(props["representative_lon"]),
                "v1_rank": props.get("rank_base_within_buffer"),
            }
        )
    for target in sorted(sector_targets, key=lambda item: item["sector_id"]):
        endpoint = nearest_cell(cells, target["representative_lat"], target["representative_lon"], v1, config)
        prior_top = top3_by_sector.get(target["sector_id"])
        for scenario in base_scenarios:
            scenario_id = str(scenario["scenario_id"])
            path_keys = reconstruct_path(endpoint, {key: cell.predecessors.get(scenario_id) for key, cell in cells.items()})
            if not path_keys:
                continue
            coordinates = [[cells[key].lon, cells[key].lat] for key in path_keys]
            geometric_length_m = sum(
                math.hypot(
                    cells[current].x_m - cells[previous].x_m,
                    cells[current].y_m - cells[previous].y_m,
                )
                for previous, current in zip(path_keys, path_keys[1:])
            )
            start_key = path_keys[0]
            end_key = path_keys[-1]
            features.append(
                {
                    "type": "Feature",
                    "id": f"{target['sector_id']}::{scenario_id}",
                    "properties": {
                        "area_label": prior_top.get("area_label") if prior_top else None,
                        "sector_id": target["sector_id"],
                        "v1_top3_member": prior_top is not None,
                        "v1_rank": target["v1_rank"],
                        "cost_scenario_id": scenario_id,
                        "hypothesis_id": scenario["hypothesis_id"],
                        "sensitivity_profile": scenario["profile_id"],
                        "start_cell_id": f"R{start_key[0]:03d}C{start_key[1]:03d}",
                        "end_cell_id": f"R{end_key[0]:03d}C{end_key[1]:03d}",
                        "path_cost_m_equivalent": cells[endpoint].costs[scenario_id],
                        "geometric_length_m": round(geometric_length_m, 6),
                        "path_node_count": len(path_keys),
                        "algorithm": str(config["corridor_rule"]["algorithm"]),
                        "configuration_sha256": configuration_sha256,
                        "interpretation": "CORREDOR_DIAGNOSTICO_DE_MENOR_CUSTO_ATE_REPRESENTANTE_V1",
                        "operational_route": False,
                        "field_confirmation_required": True,
                        "ground_truth_used": False,
                    },
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                }
            )
    return {
        "type": "FeatureCollection",
        "name": "RURAL01_MOV_V2_DIAGNOSTIC_CORRIDORS",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "ground_truth_used": False,
        "features": features,
    }


def build_result(
    cells: Mapping[tuple[int, int], Cell],
    config: Mapping[str, Any],
    scenarios: Sequence[Mapping[str, Any]],
    summaries: Sequence[Mapping[str, Any]],
    field_obstacle_count: int,
    source_timestamps: Mapping[str, Any],
) -> dict[str, Any]:
    budget = float(config["grid"]["movement_budget_cost_m"])
    reference_id = reference_cost_scenario_id(config)
    reference_summary = [row for row in summaries if row["cost_scenario_id"] == reference_id]
    reference_rank_band = select_rank_band(reference_summary, 3)
    counterfactual_id = f"SENS__{HYDRO_DUPLICATION_COUNTERFACTUAL_ID}"
    hydro_overlap_cells = [cell for cell in cells.values() if hydro_landcover_overlap(cell, config)]
    network_conflict_cells = [cell for cell in cells.values() if network_landcover_scale_conflict(cell, config)]
    scenario_summary = []
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        costs = [cell.costs[scenario_id] for cell in cells.values()]
        reached = [value for value in costs if value <= budget]
        ranks = [row for row in summaries if row["cost_scenario_id"] == scenario_id]
        rank_band = select_rank_band(ranks, 3)
        scenario_summary.append(
            {
                "cost_scenario_id": scenario_id,
                "hypothesis_id": scenario["hypothesis_id"],
                "sensitivity_profile": scenario["profile_id"],
                "reachable_cell_count": len(reached),
                "reachable_cell_fraction": round(len(reached) / len(costs), 9),
                "median_cost_m_equivalent": round(float(_quantile(costs, 0.5)), 6),
                "p90_cost_m_equivalent": round(float(_quantile(costs, 0.9)), 6),
                "top3_rank_band_sectors": [row["sector_id"] for row in rank_band],
                "rank_cutoff": 3,
                "rank_band_member_count": len(rank_band),
                "ground_truth_used": False,
            }
        )
    reference_costs = [cell.costs[reference_id] for cell in cells.values()]
    counterfactual_costs = [cell.costs[counterfactual_id] for cell in cells.values()]
    reference_rank_band_ids = {str(row["sector_id"]) for row in reference_rank_band}
    counterfactual_top_rows = select_rank_band(
        [row for row in summaries if row["cost_scenario_id"] == counterfactual_id],
        3,
    )
    counterfactual_top_ids = {str(row["sector_id"]) for row in counterfactual_top_rows}
    top3_union = reference_rank_band_ids | counterfactual_top_ids
    output = {
        "protocol_id": config["protocol_id"],
        "engine_version": str(config.get("engine_version", ENGINE_VERSION)),
        "scenario_id": config["source"]["scenario_id"],
        "candidate_id": config["source"]["candidate_id"],
        "execution_classification": "DESENVOLVIMENTO_CEGO_NAO_CONFIRMATORIO",
        "development_status": development_status(config),
        "review_status": "REVISAR",
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "source": dict(config["source"]),
        "elapsed_hours_role": "CONTEXTO_NAO_CONVERTIDO_AUTOMATICAMENTE_EM_DISTANCIA_OU_TEMPO_ATIVO",
        "grid": {
            "resolution_m": config["grid"]["resolution_m"],
            "cell_count": len(cells),
            "movement_budget_cost_m": budget,
            "extent_limited_to_source_radius": True,
            "analysis_crs_method": "LOCAL_AEQD_CENTERED_ON_SOURCE_POINT",
            "analysis_crs_definition": (
                f"+proj=aeqd +lat_0={config['source']['point']['latitude']} "
                f"+lon_0={config['source']['point']['longitude']} +R=6371008.8 +units=m +no_defs"
            ),
        },
        "cost_semantics": COST_SEMANTICS,
        "reference_cost_scenario": {
            "cost_scenario_id": reference_id,
            "role": "REFERENCIAL_NAO_SELECIONADO",
            "selected": False,
            "purpose": "CONTROLES_DE_DEDUPLICACAO_CONTRAFACTUAL_E_REPETIBILIDADE",
        },
        "hypothesis_selection_status": "NENHUMA_HIPOTESE_SELECIONADA_REGIME_DESCONHECIDO",
        "field_obstacle_count": field_obstacle_count,
        "field_obstacle_used": field_obstacle_count > 0,
        "source_timestamps": dict(source_timestamps),
        "relationship_to_prior_geo_modules": config["scope"]["relationship_to_geo02_05"],
        "overlap_controls": {
            "hydro_landcover_policy": HYDRO_OVERLAP_POLICY,
            "hydro_landcover_overlap_cell_count": len(hydro_overlap_cells),
            "hydro_landcover_overlap_fraction": round(len(hydro_overlap_cells) / len(cells), 9),
            "hydro_factor_neutralized_in_reference_on_overlap": True,
            "counterfactual_cost_scenario_id": counterfactual_id,
            "counterfactual_is_promoted": False,
            "counterfactual_cells_with_higher_accumulated_cost": sum(
                old > new + 1e-9 for old, new in zip(counterfactual_costs, reference_costs)
            ),
            "counterfactual_median_cost_delta_m_equivalent": round(
                float(_quantile(counterfactual_costs, 0.5)) - float(_quantile(reference_costs, 0.5)),
                6,
            ),
            "counterfactual_top3_jaccard": round(
                len(reference_rank_band_ids & counterfactual_top_ids) / len(top3_union), 9
            ) if top3_union else 1.0,
            "network_landcover_policy": NETWORK_OVERLAP_POLICY,
            "network_landcover_scale_conflict_cell_count": len(network_conflict_cells),
            "network_landcover_scale_conflict_fraction": round(len(network_conflict_cells) / len(cells), 9),
        },
        "base_hypothesis_top3": {
            str(scenario["hypothesis_id"]): [
                {
                    "sector_id": row["sector_id"],
                    "mobility_rank": row["mobility_rank_within_buffer"],
                    "accessibility_index": row["accessibility_index"],
                    "reachable_fraction": row["reachable_fraction"],
                    "v1_rank": row["v1_rank"],
                }
                for row in select_rank_band(
                    [item for item in summaries if item["cost_scenario_id"] == scenario["scenario_id"]],
                    3,
                )
            ]
            for scenario in scenarios
            if scenario["profile_id"] == "BASE"
        },
        "top3_rank_band_policy": "INCLUDE_ALL_SECTORS_WITH_MOBILITY_RANK_LE_3_INCLUDING_TIES",
        "scenario_summary": scenario_summary,
        "interpretation": {
            "cost": "RESISTENCIA_RELATIVA_ACUMULADA_NAO_PROBABILIDADE_NAO_TEMPO",
            "reachable": "ALCANCAVEL_SOB_ORCAMENTO_HEURISTICO_DE_ESFORCO_DENTRO_DO_RAIO_FONTE",
            "corridors": "CAMINHOS_DIAGNOSTICOS_DE_MENOR_CUSTO_NAO_ROTAS_CONFIRMADAS",
            "sector_rank": "COMPARACAO_DE_ACESSIBILIDADE_FISICA_NAO_LOCALIZACAO_DA_PESSOA",
            "operational_command": False,
        },
        "limitations": list(config.get("known_limitations", [])),
    }
    enforce_blind_firewall(output, config)
    return output


def build_manifest(
    config: Mapping[str, Any],
    config_path: Path,
    protocol_path: Path,
    input_paths: Sequence[tuple[str, Path]],
    output_paths: Sequence[tuple[str, Path]],
) -> dict[str, Any]:
    files = []
    for role, path in list(input_paths) + list(output_paths):
        try:
            manifested_path = str(path.resolve().relative_to(PROJECT_ROOT))
        except ValueError:
            manifested_path = str(path.resolve())
        files.append(
            {
                "role": role,
                "path": manifested_path,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    manifest = {
        "protocol_id": config["protocol_id"],
        "engine_version": str(config.get("engine_version", ENGINE_VERSION)),
        "python_version": platform.python_version(),
        "execution_classification": "DESENVOLVIMENTO_CEGO_NAO_CONFIRMATORIO",
        "development_status": development_status(config),
        "confirmatory_eligible": False,
        "ground_truth_used": False,
        "configuration_sha256": sha256_file(config_path),
        "protocol_sha256": sha256_file(protocol_path),
        "files": files,
    }
    manifest["payload_sha256"] = canonical_hash({key: value for key, value in manifest.items() if key != "payload_sha256"})
    enforce_blind_firewall(manifest, config)
    return manifest


def verify_manifest_integrity(manifest: Mapping[str, Any], project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    expected_payload = str(manifest.get("payload_sha256", ""))
    actual_payload = canonical_hash({key: value for key, value in manifest.items() if key != "payload_sha256"})
    if not expected_payload or expected_payload != actual_payload:
        raise MovementContractError("Hash canônico do manifesto divergente")
    verified = 0
    for entry in manifest.get("files", []):
        path = Path(str(entry["path"]))
        if not path.is_absolute():
            path = project_root / path
        if not path.is_file():
            raise MovementContractError(f"Arquivo manifestado ausente: {path}")
        if path.stat().st_size != int(entry["bytes"]):
            raise MovementContractError(f"Tamanho divergente no manifesto: {path}")
        if sha256_file(path) != str(entry["sha256"]):
            raise MovementContractError(f"SHA-256 divergente no manifesto: {path}")
        verified += 1
    return {"status": "PASS", "verified_file_count": verified, "payload_sha256": actual_payload}


def validate_test_receipt(receipt_path: Path, config_path: Path) -> dict[str, Any]:
    receipt = load_json(receipt_path)
    expected_payload = str(receipt.get("payload_sha256", ""))
    actual_payload = canonical_hash({key: value for key, value in receipt.items() if key != "payload_sha256"})
    if expected_payload != actual_payload:
        raise MovementContractError("Recibo da suíte tem hash canônico divergente")
    expected_hashes = {
        "engine_sha256": sha256_file(Path(__file__).resolve()),
        "test_suite_sha256": sha256_file(TEST_SUITE_PATH),
        "config_sha256": sha256_file(config_path),
        "runner_sha256": sha256_file(TEST_RUNNER_PATH),
    }
    if (
        receipt.get("status") != "PASS"
        or int(receipt.get("tests_run", 0)) <= 0
        or int(receipt.get("failure_count", -1)) != 0
        or int(receipt.get("error_count", -1)) != 0
    ):
        raise MovementContractError("A suíte de testes não possui recibo PASS válido")
    for key, expected in expected_hashes.items():
        if receipt.get(key) != expected:
            raise MovementContractError(f"Recibo da suíte não corresponde ao arquivo atual: {key}")
    return dict(receipt)


def validate_outputs(
    config: Mapping[str, Any],
    cells: Mapping[tuple[int, int], Cell],
    scenarios: Sequence[Mapping[str, Any]],
    summaries: Sequence[Mapping[str, Any]],
    result: Mapping[str, Any],
    corridors: Mapping[str, Any],
    repeated_cost_run_deterministic: bool,
    firewall_receipt: Mapping[str, Any],
    test_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    budget = float(config["grid"]["movement_budget_cost_m"])
    scenario_ids = [str(scenario["scenario_id"]) for scenario in scenarios]
    origin_cells = [cell for cell in cells.values() if cell.x_m == 0.0 and cell.y_m == 0.0]
    predecessor_monotonic = True
    predecessor_complete = True
    for cell in cells.values():
        for scenario_id in scenario_ids:
            predecessor = cell.predecessors.get(scenario_id)
            if cell in origin_cells:
                predecessor_complete = predecessor_complete and predecessor is None
            else:
                predecessor_complete = predecessor_complete and predecessor is not None
            if predecessor is not None:
                predecessor_monotonic = predecessor_monotonic and cells[predecessor].costs[scenario_id] < cell.costs[scenario_id]
    soft_strong_ordered = all(
        cell.costs[f"{hypothesis}__FORTE"] + 1e-9 >= cell.costs[f"{hypothesis}__SUAVE"]
        for cell in cells.values()
        for hypothesis in ("H_REDE_DISPONIVEL", "H_FORA_REDE")
    )
    network_optional_never_worsens = all(
        cell.costs["H_REDE_DISPONIVEL__BASE"] <= cell.costs["H_FORA_REDE__BASE"] + 1e-9
        for cell in cells.values()
    )
    base_scenario_ids = [
        str(scenario["scenario_id"])
        for scenario in scenarios
        if scenario.get("profile_id") == config["scenario_selection"]["base_profile_id"]
    ]
    base_cost_ranges = {
        scenario_id: [cell.costs[scenario_id] for cell in cells.values()]
        for scenario_id in base_scenario_ids
    }
    reference_id = reference_cost_scenario_id(config)
    reference_costs = [cell.costs[reference_id] for cell in cells.values()]
    base_scenario = next(
        scenario for scenario in scenarios if scenario["scenario_id"] == reference_id
    )
    counterfactual_id = f"SENS__{HYDRO_DUPLICATION_COUNTERFACTUAL_ID}"
    overlap_cells = [cell for cell in cells.values() if hydro_landcover_overlap(cell, config)]
    hydro_deduplication_valid = bool(overlap_cells) and all(
        math.isclose(float(cell_component_factors(cell, config, base_scenario)["hydro_factor"]), 1.0, abs_tol=1e-12)
        for cell in overlap_cells
    )
    counterfactual_not_promoted = (
        counterfactual_id in scenario_ids
        and reference_id != counterfactual_id
        and all(
            cell.costs[counterfactual_id] + 1e-9 >= cell.costs[reference_id]
            for cell in cells.values()
        )
        and any(
            cell.costs[counterfactual_id] > cell.costs[reference_id] + 1e-9
            for cell in cells.values()
        )
    )
    ablations_not_more_costly = all(
        all(cell.costs[ablation] <= cell.costs[reference_id] + 1e-9 for cell in cells.values())
        for ablation in ("ABL__SEM_HIDRO", "ABL__SEM_COBERTURA", "ABL__SEM_RELEVO", "ABL__SEM_DESCONTO_REDE")
        if ablation != "ABL__SEM_DESCONTO_REDE"
    )
    required_corridor_fields = {
        "start_cell_id",
        "end_cell_id",
        "geometric_length_m",
        "algorithm",
        "hypothesis_id",
        "configuration_sha256",
    }
    corridor_metadata_complete = all(
        required_corridor_fields <= set(feature.get("properties", {}))
        and float(feature["properties"]["geometric_length_m"]) >= 0.0
        for feature in corridors.get("features", [])
    )
    firewall_passed = (
        firewall_receipt.get("status") == "PASS"
        and int(firewall_receipt.get("scan_batch_count", 0)) > 0
        and int(firewall_receipt.get("scanned_key_count", 0)) > 0
        and int(firewall_receipt.get("scanned_string_count", 0)) > 0
        and int(firewall_receipt.get("scanned_path_count", 0)) > 0
    )
    gates = {
        "configuration_valid": True,
        "blind_control_is_false": result.get("ground_truth_used") is False,
        "firewall_scan_passed": firewall_passed,
        "test_suite_receipt_passed_and_bound_to_current_files": (
            test_receipt.get("status") == "PASS" and int(test_receipt.get("tests_run", 0)) > 0
        ),
        "source_radius_preserved": math.isclose(float(result["source"]["radius_m"]), 1500.0, abs_tol=1e-9),
        "elapsed_14h_is_context_only": result.get("elapsed_hours_role") == "CONTEXTO_NAO_CONVERTIDO_AUTOMATICAMENTE_EM_DISTANCIA_OU_TEMPO_ATIVO",
        "crs_metric_and_manifested": (
            config["grid"].get("analysis_crs_method") == "LOCAL_AEQD_CENTERED_ON_SOURCE_POINT"
            and "+proj=aeqd" in str(result.get("grid", {}).get("analysis_crs_definition", ""))
            and "+units=m" in str(result.get("grid", {}).get("analysis_crs_definition", ""))
        ),
        "grid_aligned_and_unique": len(cells) == len({(cell.row, cell.col) for cell in cells.values()}),
        "grid_has_origin": len(origin_cells) == 1,
        "source_accumulated_cost_zero": len(origin_cells) == 1 and all(origin_cells[0].costs[sid] == 0.0 for sid in scenario_ids),
        "diagonal_distance_correct": math.isclose(DIRECTIONS_D8[0][2], math.sqrt(2.0), abs_tol=1e-15),
        "all_cells_have_raster_samples": all(cell.elevation_m is not None and cell.worldcover_code is not None for cell in cells.values()),
        "all_cells_have_sector": all(cell.sector_id is not None for cell in cells.values()),
        "all_costs_are_finite_nonnegative": all(
            scenario_id in cell.costs and math.isfinite(cell.costs[scenario_id]) and cell.costs[scenario_id] >= 0.0
            for cell in cells.values()
            for scenario_id in scenario_ids
        ),
        "all_scenarios_have_24_sector_rows": all(
            sum(row["cost_scenario_id"] == scenario_id for row in summaries) == 24 for scenario_id in scenario_ids
        ),
        "reference_scenario_is_explicit_and_not_selected": (
            reference_id in scenario_ids
            and result.get("reference_cost_scenario", {}).get("role") == "REFERENCIAL_NAO_SELECIONADO"
            and result.get("reference_cost_scenario", {}).get("selected") is False
            and result.get("hypothesis_selection_status") == "NENHUMA_HIPOTESE_SELECIONADA_REGIME_DESCONHECIDO"
        ),
        "network_and_off_network_base_exist": {
            row["hypothesis_id"] for row in result["scenario_summary"] if row["sensitivity_profile"] == "BASE"
        } >= {"H_REDE_DISPONIVEL", "H_FORA_REDE"},
        "some_cells_exceed_budget_in_each_base_hypothesis": all(
            any(value > budget for value in values) for values in base_cost_ranges.values()
        ),
        "some_non_origin_cells_are_reachable_in_each_base_hypothesis": all(
            sum(0.0 < value <= budget for value in values) > 0 for values in base_cost_ranges.values()
        ),
        "field_review_is_required": all(row.get("field_confirmation_required") is True for row in summaries),
        "predecessors_complete_and_monotonic": predecessor_complete and predecessor_monotonic,
        "strong_profile_not_cheaper_than_soft": soft_strong_ordered,
        "network_discount_never_zero": float(config["resistance"]["network"]["road_factor"]) > 0.0 and float(config["resistance"]["network"]["trail_factor"]) > 0.0,
        "network_hypothesis_never_worsens_cost": network_optional_never_worsens,
        "component_ablations_not_more_costly": ablations_not_more_costly,
        "repeated_cost_run_deterministic": repeated_cost_run_deterministic,
        "mov_v_separate_from_mov_e_and_det": config["separation_contract"].get("aggregate_mov_v_mov_e_det") is False,
        "time_conversion_disabled": config["time_policy"].get("convert_to_distance") is False and config["time_policy"].get("convert_to_isochrone") is False,
        "understory_limitation_exposed": config["resistance"]["landcover"].get("understory_observability") == "NAO_DISPONIVEL",
        "directional_anisotropy_not_claimed": config["resistance"]["slope"].get("directional_anisotropy_effective") is False,
        "hydro_landcover_deduplication_enabled": hydro_deduplication_valid,
        "hydro_duplication_counterfactual_not_promoted": counterfactual_not_promoted,
        "network_landcover_scale_conflict_exposed": (
            result.get("overlap_controls", {}).get("network_landcover_policy") == NETWORK_OVERLAP_POLICY
            and int(result.get("overlap_controls", {}).get("network_landcover_scale_conflict_cell_count", 0)) > 0
        ),
        "mov_v_not_additive_to_geo02_05": config["scope"].get("relationship_to_geo02_05")
        == "ALTERNATIVE_PATH_BASED_REPRESENTATION_NOT_ADDITIVE_FIFTH_COMPONENT",
        "corridor_count_is_prespecified_48": len(corridors.get("features", [])) == 48,
        "corridor_metadata_complete": corridor_metadata_complete,
        "corridors_cover_all_24_sectors_per_base_hypothesis": all(
            len({feature["properties"]["sector_id"] for feature in corridors.get("features", []) if feature["properties"]["cost_scenario_id"] == scenario_id}) == 24
            for scenario_id in ("H_REDE_DISPONIVEL__BASE", "H_FORA_REDE__BASE")
        ),
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    report = {
        "protocol_id": config["protocol_id"],
        "status": status,
        "gate_count": len(gates),
        "passed_gate_count": sum(bool(value) for value in gates.values()),
        "gates": gates,
        "firewall_receipt": dict(firewall_receipt),
        "test_suite_receipt": {
            "status": test_receipt.get("status"),
            "tests_run": test_receipt.get("tests_run"),
            "payload_sha256": test_receipt.get("payload_sha256"),
        },
        "diagnostics": {
            "cell_count": len(cells),
            "cost_scenario_count": len(scenario_ids),
            "base_hypothesis_cost_ranges_m_equivalent": {
                scenario_id: {
                    "minimum": round(min(values), 6),
                    "maximum": round(max(values), 6),
                }
                for scenario_id, values in base_cost_ranges.items()
            },
            "reference_cost_scenario_id": reference_id,
            "reference_minimum_cost_m_equivalent": round(min(reference_costs), 6),
            "reference_maximum_cost_m_equivalent": round(max(reference_costs), 6),
            "directional_anisotropy_effective": False,
            "hydro_landcover_overlap_cell_count": len(overlap_cells),
            "network_landcover_scale_conflict_cell_count": int(
                result.get("overlap_controls", {}).get("network_landcover_scale_conflict_cell_count", 0)
            ),
        },
        "ground_truth_used": False,
    }
    enforce_blind_firewall(report, config)
    if status != "PASS":
        failed = [key for key, value in gates.items() if not value]
        raise MovementContractError(f"Falha nos gates: {', '.join(failed)}")
    return report


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    v1 = _load_v1_engine()
    config_path = Path(args.config).resolve()
    protocol_path = Path(args.protocol).resolve()
    output_dir = Path(args.output_dir).resolve()
    sectors_path = Path(args.sectors).resolve()
    ranking_path = Path(args.ranking).resolve()
    top3_path = Path(args.top3).resolve()
    roads_path = Path(args.roads).resolve()
    hydro_path = Path(args.hydro).resolve()
    dem_dir = Path(args.dem_dir).resolve()
    worldcover_dir = Path(args.worldcover_dir).resolve()
    test_receipt_path = Path(args.test_receipt).resolve()
    field_path = Path(args.field_obstacles).resolve() if args.field_obstacles else None
    required = [
        config_path,
        protocol_path,
        sectors_path,
        ranking_path,
        top3_path,
        roads_path,
        hydro_path,
        dem_dir,
        worldcover_dir,
        V1_ENGINE_PATH,
        TEST_SUITE_PATH,
        TEST_RUNNER_PATH,
        test_receipt_path,
    ]
    if field_path is not None:
        required.append(field_path)
    for path in required:
        if not path.exists():
            raise FileNotFoundError(path)

    config = load_json(config_path)
    firewall_receipts: list[Mapping[str, Any]] = [validate_config(config)]
    firewall_receipts.append(enforce_blind_firewall({}, config, source_paths=[*required, output_dir]))
    test_receipt = validate_test_receipt(test_receipt_path, config_path)
    firewall_receipts.append(enforce_blind_firewall(test_receipt, config))
    top3_doc = load_json(top3_path)
    sectors_doc = load_json(sectors_path)
    firewall_receipts.append(enforce_blind_firewall(top3_doc, config))
    firewall_receipts.append(enforce_blind_firewall(sectors_doc, config))
    # Os documentos OSM entram no motor por meio do carregador v1. A leitura
    # adicional abaixo existe apenas para que o firewall examine também seus
    # textos, e não somente os caminhos ou objetos já transformados.
    firewall_receipts.append(enforce_blind_firewall(load_json(roads_path), config))
    firewall_receipts.append(enforce_blind_firewall(load_json(hydro_path), config))
    with ranking_path.open("r", encoding="utf-8", newline="") as handle:
        firewall_receipts.append(enforce_blind_firewall(list(csv.DictReader(handle)), config))
    if field_path is not None:
        firewall_receipts.append(enforce_blind_firewall(load_json(field_path), config))
    cells, half = make_grid(v1, config)
    sample_rasters(v1, cells, config, dem_dir, worldcover_dir)
    roads, road_timestamp = v1.load_road_segments(roads_path)
    hydros, hydro_timestamp = v1.load_hydro_segments(hydro_path)
    rasterize_segments(v1, cells, half, roads, config, "network")
    rasterize_segments(v1, cells, half, hydros, config, "hydro")
    field_count = apply_field_obstacles(v1, cells, config, field_path)
    attach_v1_sectors(v1, cells, sectors_path, ranking_path, config)

    scenarios = cost_scenarios(config)
    origin = (half, half)
    for scenario in scenarios:
        dijkstra_cost_surface(cells, origin, config, scenario)

    repeated_cost_run_deterministic = True
    for base_scenario in (scenario for scenario in scenarios if scenario["profile_id"] == "BASE"):
        scenario_id = str(base_scenario["scenario_id"])
        first_projection = [
            (key, cells[key].costs[scenario_id], cells[key].predecessors[scenario_id]) for key in sorted(cells)
        ]
        dijkstra_cost_surface(cells, origin, config, base_scenario)
        second_projection = [
            (key, cells[key].costs[scenario_id], cells[key].predecessors[scenario_id]) for key in sorted(cells)
        ]
        repeated_cost_run_deterministic = repeated_cost_run_deterministic and first_projection == second_projection

    rows = cell_rows(cells, config, scenarios)
    summaries = sector_summaries(cells, config, scenarios)
    base_surface_docs = {
        str(scenario["hypothesis_id"]): build_cost_points_geojson(rows, config, str(scenario["scenario_id"]))
        for scenario in scenarios
        if scenario["profile_id"] == "BASE"
    }
    reachable = build_reachable_geojson(v1, cells, config, scenarios)
    corridors = build_corridors_geojson(
        cells,
        config,
        scenarios,
        sectors_doc,
        top3_doc,
        v1,
        sha256_file(config_path),
    )
    result = build_result(
        cells,
        config,
        scenarios,
        summaries,
        field_count,
        {"osm_road_timestamp": road_timestamp, "osm_hydro_timestamp": hydro_timestamp},
    )
    for value in (rows, summaries, *base_surface_docs.values(), reachable, corridors, result):
        firewall_receipts.append(enforce_blind_firewall(value, config))
    firewall_receipt = combine_firewall_receipts(firewall_receipts)
    qa = validate_outputs(
        config,
        cells,
        scenarios,
        summaries,
        result,
        corridors,
        repeated_cost_run_deterministic,
        firewall_receipt,
        test_receipt,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "grid": output_dir / "grade_resistencia.csv",
        "sectors": output_dir / "setores_mov_v2.csv",
        "cost_network": output_dir / "superficie_custo_H_REDE_DISPONIVEL.geojson",
        "cost_off_network": output_dir / "superficie_custo_H_FORA_REDE.geojson",
        "reachable": output_dir / "areas_alcancaveis_mov_v2.geojson",
        "corridors": output_dir / "corredores_mov_v2.geojson",
        "result": output_dir / "resultado_mov_v2.json",
        "qa": output_dir / "relatorio_qa_mov_v2.json",
        "manifest": output_dir / "manifesto_mov_v2.json",
    }
    write_csv(files["grid"], rows)
    write_csv(files["sectors"], summaries)
    write_json(files["cost_network"], base_surface_docs["H_REDE_DISPONIVEL"])
    write_json(files["cost_off_network"], base_surface_docs["H_FORA_REDE"])
    write_json(files["reachable"], reachable)
    write_json(files["corridors"], corridors)
    write_json(files["result"], result)
    write_json(files["qa"], qa)

    input_paths = [
        ("engine", Path(__file__).resolve()),
        ("imported_engine", V1_ENGINE_PATH),
        ("config", config_path),
        ("protocol", protocol_path),
        ("v1_sectors", sectors_path),
        ("v1_ranking", ranking_path),
        ("v1_top3", top3_path),
        ("source_geo02_osm", roads_path),
        ("source_geo03_osm", hydro_path),
        ("test_suite", TEST_SUITE_PATH),
        ("test_runner", TEST_RUNNER_PATH),
        ("test_suite_receipt", test_receipt_path),
    ]
    input_paths.extend(("source_geo04_dem", path) for path in sorted(dem_dir.glob("*.hgt.gz")))
    input_paths.extend(("source_geo05_worldcover", path) for path in sorted(worldcover_dir.glob("*.tif")))
    if field_path is not None:
        input_paths.append(("field_obstacles", field_path))
    output_paths = [(f"output_{key}", path) for key, path in files.items() if key != "manifest"]
    manifest = build_manifest(config, config_path, protocol_path, input_paths, output_paths)
    write_json(files["manifest"], manifest)
    manifest_verification = verify_manifest_integrity(manifest)
    return {
        "status": qa["status"],
        "output_dir": str(output_dir),
        "cell_count": len(cells),
        "cost_scenario_count": len(scenarios),
        "field_obstacle_count": field_count,
        "reference_cost_scenario": result["reference_cost_scenario"],
        "hypothesis_selection_status": result["hypothesis_selection_status"],
        "base_hypothesis_top3": result["base_hypothesis_top3"],
        "manifest": str(files["manifest"]),
        "manifest_verification": manifest_verification,
        "test_suite_receipt_status": test_receipt["status"],
        "ground_truth_used": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--sectors", default=str(DEFAULT_V1_DIR / "setores_rural01.geojson"))
    parser.add_argument("--ranking", default=str(DEFAULT_V1_DIR / "ranking_base_rural01.csv"))
    parser.add_argument("--top3", default=str(DEFAULT_V1_DIR / "top3_rural01.json"))
    parser.add_argument("--roads", default=str(DEFAULT_GEO_DIR / "osm_highways_raw.json"))
    parser.add_argument("--hydro", default=str(DEFAULT_GEO_DIR / "osm_hydrography_raw.json"))
    parser.add_argument("--dem-dir", default=str(DEFAULT_GEO_DIR))
    parser.add_argument("--worldcover-dir", default=str(DEFAULT_GEO_DIR / "worldcover_tiles"))
    parser.add_argument("--test-receipt", default=str(DEFAULT_TEST_RECEIPT_PATH))
    parser.add_argument("--field-obstacles", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_pipeline(args)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
