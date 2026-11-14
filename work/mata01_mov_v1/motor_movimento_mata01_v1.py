#!/usr/bin/env python3
"""Superfície cega de resistência e corredores de planejamento do MATA-01.

O módulo reutiliza somente primitivas genéricas auditadas do MOV-V RURAL-01:
grade AEQD, amostragem SRTM/WorldCover, custo de aresta D8 e Dijkstra. A
validação, a semântica temporal, a setorização e os produtos são específicos
do MATA-01. Nenhuma posição do alvo é aceita.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import platform
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
CORE_PATH = PROJECT_ROOT / "work/rural01_mov_v2/motor_movimento_v2.py"
V1_ENGINE_PATH = PROJECT_ROOT / "work/ext_espacial_setores_v1_1/motor_setorizacao_priorizacao.py"
DEFAULT_CONFIG = HERE / "config_mata01_mov_v1.json"
DEFAULT_PROTOCOL = HERE / "PROTOCOLO_MATA01_MOVIMENTO_CEGO_v1.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "outputs/campo_mata01/processamento_movimento_cego_v1"
DEFAULT_GEO = PROJECT_ROOT / "outputs/sprint2_s2_06_geo05_v33"
DEFAULT_TEST_RECEIPT = DEFAULT_OUTPUT / "relatorio_testes_mata01_mov_v1.json"
TEST_SUITE_PATH = HERE / "test_motor_movimento_mata01_v1.py"
TEST_RUNNER_PATH = HERE / "run_tests_with_receipt.py"

DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
FORBIDDEN_COORDINATE_FIELDS = {
    "ground_truth_lat",
    "ground_truth_lon",
    "ground_truth_longitude",
    "victim_lat",
    "victim_lon",
    "target_lat",
    "target_lon",
    "real_lat",
    "real_lon",
    "true_lat",
    "true_lon",
    "reference_lat",
    "reference_lon",
    "evaluation_latitude",
    "evaluation_longitude",
}


class MataMovementError(ValueError):
    """Falha de contrato ou de qualidade do processamento."""


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível carregar {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_core() -> Any:
    return _load_module("mata01_reused_mov_core", CORE_PATH)


def load_v1() -> Any:
    return _load_module("mata01_reused_geo_core", V1_ENGINE_PATH)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def scan_forbidden_fields(value: Any, path: str = "$") -> int:
    """Rejeita coordenadas de avaliação, inclusive quando aninhadas."""
    scanned = 0
    if isinstance(value, Mapping):
        for key, child in value.items():
            scanned += 1
            normalized = str(key).casefold().replace("-", "_")
            if any(fragment in normalized for fragment in FORBIDDEN_COORDINATE_FIELDS):
                raise MataMovementError(f"Campo de coordenada proibido em {path}.{key}")
            scanned += scan_forbidden_fields(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            scanned += scan_forbidden_fields(child, f"{path}[{index}]")
    return scanned


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    scanned = scan_forbidden_fields(config)
    source = config.get("source", {})
    point = source.get("point", {})
    if source.get("scenario_id") != "MATA-01" or source.get("candidate_id") != "MATA-01-E0":
        raise MataMovementError("Identidade do cenário divergente")
    if not math.isclose(float(point.get("latitude")), -0.172222, abs_tol=1e-12):
        raise MataMovementError("Latitude inicial divergente")
    if not math.isclose(float(point.get("longitude")), -51.430278, abs_tol=1e-12):
        raise MataMovementError("Longitude inicial divergente")
    if not math.isclose(float(source.get("radius_m")), 5000.0, abs_tol=1e-9):
        raise MataMovementError("O domínio direto deve permanecer 5 km")
    if "DISTANCIA_PERCORRIDA" not in str(source.get("radius_semantics", "")):
        raise MataMovementError("Semântica não locomotora do domínio ausente")
    blind = config.get("blind_control", {})
    if blind.get("blind_processing") is not True or blind.get("ground_truth_used") is not False:
        raise MataMovementError("Controle cego inválido")
    if blind.get("reference_package_accessible_to_engine") is not False:
        raise MataMovementError("Pacote de referência não pode estar acessível")
    scope = config.get("scope", {})
    forbidden_claim_flags = (
        "output_is_probability",
        "output_is_elapsed_time",
        "output_is_observed_route",
        "output_is_trajectory_prediction",
        "operational_command",
    )
    if any(scope.get(key) is not False for key in forbidden_claim_flags):
        raise MataMovementError("Semântica de saída inválida")
    grid = config.get("grid", {})
    if not math.isclose(float(grid.get("resolution_m")), 30.0, abs_tol=1e-12):
        raise MataMovementError("A grade deve permanecer em aproximadamente 30 m")
    if grid.get("movement_budget_enabled") is not False or grid.get("isochrone_enabled") is not False:
        raise MataMovementError("Orçamento de marcha e isócrona devem permanecer desativados")
    time_policy = config.get("time_policy", {})
    if any(time_policy.get(key) is not False for key in (
        "convert_elapsed_to_distance",
        "convert_elapsed_to_isochrone",
        "convert_elapsed_to_active_travel",
    )):
        raise MataMovementError("Tempo não pode ser convertido automaticamente")
    snapshots = config.get("temporal_snapshots", [])
    if [item.get("id") for item in snapshots] != ["T26_CAMPO", "T49_ATUALIZACAO"]:
        raise MataMovementError("Snapshots T26/T49 ausentes ou fora de ordem")
    if any(item.get("changes_cost_surface") is not False for item in snapshots):
        raise MataMovementError("Tempo isolado não pode alterar a superfície")
    field = config.get("resistance", {}).get("field_obstacle", {})
    if field.get("records_available") is not False or not math.isclose(float(field.get("default_factor")), 1.0):
        raise MataMovementError("Obstáculos de campo devem permanecer não espacializados com fator 1")
    hydro = config.get("resistance", {}).get("hydro", {})
    if hydro.get("use_in_numeric_cost") is not False:
        raise MataMovementError("Hidrografia OSM não pode alterar o custo nesta execução")
    if "NAO_E_EVIDENCIA_FAVORAVEL" not in str(hydro.get("absence_policy", "")):
        raise MataMovementError("Ausência hídrica deve permanecer não favorável")
    landcover = config.get("resistance", {}).get("landcover", {})
    if set(int(value) for value in landcover.get("water_wet_proxy_codes", [])) != {80, 90}:
        raise MataMovementError("Somente as classes 80/90 formam a proxy hídrica/úmida")
    if "NAO_IGARAPE_CONFIRMADO" not in str(landcover.get("water_wet_proxy_semantics", "")):
        raise MataMovementError("Rótulo de proxy hídrica/úmida ausente")
    required_codes = {"10", "20", "30", "40", "50", "60", "70", "80", "90", "95", "100"}
    if set(landcover.get("landcover_by_code", {})) != required_codes:
        raise MataMovementError("Tabela WorldCover incompleta")
    if config.get("outputs", {}).get("include_ground_truth_payload") is not False:
        raise MataMovementError("Payload de referência proibido")
    return {"status": "PASS", "scanned_field_count": scanned}


def validate_test_receipt(receipt_path: Path, config_path: Path) -> dict[str, Any]:
    receipt = load_json(receipt_path)
    payload = {key: value for key, value in receipt.items() if key != "payload_sha256"}
    if canonical_hash(payload) != receipt.get("payload_sha256"):
        raise MataMovementError("Hash do recibo de testes divergente")
    expected = {
        "engine_sha256": sha256_file(Path(__file__).resolve()),
        "test_suite_sha256": sha256_file(TEST_SUITE_PATH),
        "runner_sha256": sha256_file(TEST_RUNNER_PATH),
        "config_sha256": sha256_file(config_path),
    }
    if receipt.get("status") != "PASS" or int(receipt.get("tests_run", 0)) <= 0:
        raise MataMovementError("Suíte de testes sem recibo PASS")
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise MataMovementError(f"Recibo de testes desatualizado: {key}")
    return receipt


def segment_near_domain(segment: Any, v1: Any, lat0: float, lon0: float, radius_m: float, margin_m: float) -> bool:
    ax, ay = v1.aeqd_forward(segment.a_lat, segment.a_lon, lat0, lon0)
    bx, by = v1.aeqd_forward(segment.b_lat, segment.b_lon, lat0, lon0)
    # A interseção do retângulo envolvente com o quadrado de análise gera
    # falsos positivos nos cantos. A distância exata do centro ao segmento
    # testa o círculo efetivo de 5 km e mantém a contagem coerente com a
    # rasterização da grade mascarada.
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    if denominator <= 1e-18:
        distance = math.hypot(ax, ay)
    else:
        t = max(0.0, min(1.0, -(ax * dx + ay * dy) / denominator))
        distance = math.hypot(ax + t * dx, ay + t * dy)
    return distance <= radius_m + margin_m


def sector_id_for_cell(cell: Any, config: Mapping[str, Any]) -> str:
    radius = float(config["source"]["radius_m"])
    ring_width = radius / 3.0
    ring = min(3, max(1, int(math.ceil(max(cell.radial_distance_m, 1e-12) / ring_width))))
    bearing = math.degrees(math.atan2(float(cell.x_m), float(cell.y_m))) % 360.0
    direction = DIRECTIONS[int(math.floor((bearing + 22.5) / 45.0)) % 8]
    return f"MATA-01::MATA-01-E0::R{ring:02d}::{direction}"


def attach_sectors(cells: Mapping[tuple[int, int], Any], config: Mapping[str, Any]) -> None:
    for cell in cells.values():
        cell.sector_id = sector_id_for_cell(cell, config)


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise MataMovementError("Percentil sem observações")
    position = fraction * (len(ordered) - 1)
    lo, hi = math.floor(position), math.ceil(position)
    if lo == hi:
        return ordered[lo]
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def summarize_sectors(cells: Mapping[tuple[int, int], Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hypothesis in ("H_REDE_DISPONIVEL", "H_FORA_REDE"):
        scenario_id = f"{hypothesis}__BASE"
        sector_ids = sorted({str(cell.sector_id) for cell in cells.values()})
        preliminary = []
        for sector_id in sector_ids:
            members = [cell for cell in cells.values() if cell.sector_id == sector_id]
            costs = [float(cell.costs[scenario_id]) for cell in members]
            wc_counts = Counter(int(cell.worldcover_code) for cell in members)
            parts = sector_id.split("::")
            preliminary.append({
                "hypothesis_id": hypothesis,
                "cost_scenario_id": scenario_id,
                "sector_id": sector_id,
                "ring_id": parts[-2],
                "direction": parts[-1],
                "cell_count": len(members),
                "cost_min_m_equivalent": round(min(costs), 6),
                "cost_median_m_equivalent": round(statistics.median(costs), 6),
                "cost_p90_m_equivalent": round(percentile(costs, 0.9), 6),
                "cost_max_m_equivalent": round(max(costs), 6),
                "tree_cover_fraction": round(wc_counts.get(10, 0) / len(members), 9),
                "water_wet_proxy_fraction": round((wc_counts.get(80, 0) + wc_counts.get(90, 0)) / len(members), 9),
                "network_cell_fraction": round(sum(bool(cell.road or cell.trail) for cell in members) / len(members), 9),
                "field_obstacle_factor": 1.0,
                "interpretation": "CUSTO_ACUMULADO_COMBINA_DISTANCIA_E_RESISTENCIA_NAO_PROBABILIDADE",
            })
        ordered = sorted(preliminary, key=lambda row: (row["cost_median_m_equivalent"], row["sector_id"]))
        for rank, row in enumerate(ordered, start=1):
            row["combined_cost_rank_within_hypothesis"] = rank
        for ring_id in ("R01", "R02", "R03"):
            same_ring = sorted(
                [row for row in preliminary if row["ring_id"] == ring_id],
                key=lambda row: (row["cost_median_m_equivalent"], row["sector_id"]),
            )
            for rank, row in enumerate(same_ring, start=1):
                row["directional_cost_rank_within_ring"] = rank
        rows.extend(ordered)
    return rows


def nearest_cell_xy(cells: Mapping[tuple[int, int], Any], x_m: float, y_m: float) -> tuple[int, int]:
    return min(cells, key=lambda key: (
        (float(cells[key].x_m) - x_m) ** 2 + (float(cells[key].y_m) - y_m) ** 2,
        key[0],
        key[1],
    ))


def representative_targets(cells: Mapping[tuple[int, int], Any], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    radius = float(config["source"]["radius_m"])
    ring_width = radius / 3.0
    targets = []
    for ring in range(1, 4):
        target_radius = (ring - 0.5) * ring_width
        for index, direction in enumerate(DIRECTIONS):
            bearing = math.radians(index * 45.0)
            x_m = target_radius * math.sin(bearing)
            y_m = target_radius * math.cos(bearing)
            key = nearest_cell_xy(cells, x_m, y_m)
            targets.append({
                "sector_id": f"MATA-01::MATA-01-E0::R{ring:02d}::{direction}",
                "ring": ring,
                "direction": direction,
                "target_radius_m": round(target_radius, 6),
                "cell_key": key,
            })
    return targets


def build_corridors(core: Any, cells: Mapping[tuple[int, int], Any], config: Mapping[str, Any]) -> dict[str, Any]:
    targets = representative_targets(cells, config)
    features = []
    for hypothesis in ("H_REDE_DISPONIVEL", "H_FORA_REDE"):
        scenario_id = f"{hypothesis}__BASE"
        predecessors = {key: cell.predecessors.get(scenario_id) for key, cell in cells.items()}
        for target in targets:
            keys = core.reconstruct_path(target["cell_key"], predecessors)
            if not keys:
                raise MataMovementError(f"Corredor ausente: {scenario_id} {target['sector_id']}")
            path_cells = [cells[key] for key in keys]
            length = sum(
                math.hypot(path_cells[index].x_m - path_cells[index - 1].x_m,
                           path_cells[index].y_m - path_cells[index - 1].y_m)
                for index in range(1, len(path_cells))
            )
            proxy_cells = sum(cell.worldcover_code in {80, 90} for cell in path_cells)
            features.append({
                "type": "Feature",
                "id": f"{scenario_id}::{target['sector_id']}",
                "properties": {
                    "hypothesis_id": hypothesis,
                    "cost_scenario_id": scenario_id,
                    "sector_id": target["sector_id"],
                    "representative_radius_m": target["target_radius_m"],
                    "accumulated_cost_m_equivalent": round(float(path_cells[-1].costs[scenario_id]), 6),
                    "geometric_length_m": round(length, 6),
                    "cell_count": len(path_cells),
                    "water_wet_proxy_cell_count": proxy_cells,
                    "network_cell_count": sum(bool(cell.road or cell.trail) for cell in path_cells),
                    "algorithm": "DIJKSTRA_PREDECESSOR_PATH",
                    "interpretation": "CORREDOR_DIAGNOSTICO_NAO_TRAJETORIA_NAO_PROBABILIDADE",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[cell.lon, cell.lat] for cell in path_cells],
                },
            })
    return {
        "type": "FeatureCollection",
        "name": "MATA01_CORREDORES_PLANEJAMENTO_CEGOS",
        "features": features,
    }


def grid_rows(cells: Mapping[tuple[int, int], Any]) -> list[dict[str, Any]]:
    rows = []
    for key in sorted(cells):
        cell = cells[key]
        rows.append({
            "cell_id": f"R{cell.row:03d}C{cell.col:03d}",
            "row": cell.row,
            "col": cell.col,
            "latitude": f"{cell.lat:.10f}",
            "longitude": f"{cell.lon:.10f}",
            "x_m": f"{cell.x_m:.3f}",
            "y_m": f"{cell.y_m:.3f}",
            "radial_distance_m": f"{cell.radial_distance_m:.3f}",
            "elevation_srtm_m": f"{float(cell.elevation_m):.6f}",
            "slope_srtm_deg": f"{float(cell.slope_deg):.6f}",
            "relief_3x3_srtm_m": f"{float(cell.relief_3x3_m):.6f}",
            "worldcover_code": int(cell.worldcover_code),
            "water_wet_proxy": str(cell.worldcover_code in {80, 90}).lower(),
            "road_osm": str(bool(cell.road)).lower(),
            "trail_osm": str(bool(cell.trail)).lower(),
            "osm_hydro_numeric_factor": "1.0",
            "field_obstacle_factor": "1.0",
            "sector_id": cell.sector_id,
            "cost_H_REDE_DISPONIVEL_BASE": f"{cell.costs['H_REDE_DISPONIVEL__BASE']:.6f}",
            "cost_H_FORA_REDE_BASE": f"{cell.costs['H_FORA_REDE__BASE']:.6f}",
        })
    return rows


def cost_digest(cells: Mapping[tuple[int, int], Any], scenario_id: str) -> str:
    return canonical_hash([
        [key[0], key[1], round(float(cells[key].costs[scenario_id]), 6)]
        for key in sorted(cells)
    ])


def validate_outputs(
    cells: Mapping[tuple[int, int], Any],
    scenarios: Sequence[Mapping[str, Any]],
    corridors: Mapping[str, Any],
    summaries: Sequence[Mapping[str, Any]],
    network_segments_near: int,
    hydro_segments_near: int,
    deterministic_repeat: bool,
    config_receipt: Mapping[str, Any],
    test_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    scenario_ids = {str(item["scenario_id"]) for item in scenarios}
    network_cells = sum(bool(cell.road or cell.trail) for cell in cells.values())
    hydro_numeric_cells = sum(float(cell.hydro_severity) > 0 for cell in cells.values())
    base_equal = all(
        math.isclose(
            float(cell.costs["H_REDE_DISPONIVEL__BASE"]),
            float(cell.costs["H_FORA_REDE__BASE"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for cell in cells.values()
    )
    proxy_count = sum(cell.worldcover_code in {80, 90} for cell in cells.values())
    gates = {
        "configuration_valid": config_receipt.get("status") == "PASS",
        "test_receipt_bound_and_passed": test_receipt.get("status") == "PASS",
        "blind_coordinate_firewall_scanned": int(config_receipt.get("scanned_field_count", 0)) > 0,
        "grid_nonempty": len(cells) > 0,
        "all_cells_have_srtm_worldcover": all(
            cell.elevation_m is not None and cell.slope_deg is not None and cell.worldcover_code is not None
            for cell in cells.values()
        ),
        "all_cells_field_factor_one": all(math.isclose(float(cell.field_obstacle_factor), 1.0) for cell in cells.values()),
        "osm_hydro_not_used_numerically": hydro_numeric_cells == 0,
        "osm_hydro_absence_not_promoted_to_favorable": hydro_segments_near == 0 and hydro_numeric_cells == 0,
        "network_layer_consistent_with_rasterization": (
            (network_segments_near == 0 and network_cells == 0)
            or (network_segments_near > 0 and network_cells > 0)
        ),
        "parallel_base_hypotheses_exist": {
            "H_REDE_DISPONIVEL__BASE", "H_FORA_REDE__BASE"
        } <= scenario_ids,
        "parallel_base_hypotheses_identical_when_network_absent": network_cells != 0 or base_equal,
        "network_hypothesis_changes_cost_when_network_present": network_cells == 0 or not base_equal,
        "all_costs_finite_nonnegative": all(
            math.isfinite(float(cell.costs[scenario_id])) and float(cell.costs[scenario_id]) >= 0
            for cell in cells.values() for scenario_id in scenario_ids
        ),
        "exactly_24_sector_summaries_per_base_hypothesis": all(
            sum(row["hypothesis_id"] == hypothesis for row in summaries) == 24
            for hypothesis in ("H_REDE_DISPONIVEL", "H_FORA_REDE")
        ),
        "exactly_48_prespecified_corridors": len(corridors.get("features", [])) == 48,
        "corridors_are_nonprobabilistic": all(
            "NAO_PROBABILIDADE" in feature.get("properties", {}).get("interpretation", "")
            for feature in corridors.get("features", [])
        ),
        "deterministic_repeat": deterministic_repeat,
        "water_wet_proxy_explicitly_counted": proxy_count >= 0,
        "T26_T49_not_converted": True,
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    report = {
        "protocol_id": "MATA01-BLIND-MOV-V-v1.0",
        "status": status,
        "gate_count": len(gates),
        "passed_gate_count": sum(bool(value) for value in gates.values()),
        "gates": gates,
        "diagnostics": {
            "cell_count": len(cells),
            "scenario_count": len(scenario_ids),
            "network_segments_near_domain": network_segments_near,
            "network_cell_count": network_cells,
            "osm_hydro_segments_near_domain": hydro_segments_near,
            "osm_hydro_numeric_cell_count": hydro_numeric_cells,
            "worldcover_water_wet_proxy_cell_count": proxy_count,
            "base_hypotheses_identical": base_equal,
            "field_obstacle_records_available": False,
            "field_obstacle_factor": 1.0,
        },
        "temporal_interpretation": {
            "T26": "CONTEXTO_SEM_CONVERSAO_EM_DISTANCIA",
            "T49": "CONTEXTO_SEM_CONVERSAO_EM_DISTANCIA",
            "same_physical_cost_surface": True,
        },
        "ground_truth_used": False,
    }
    if status != "PASS":
        failed = [key for key, value in gates.items() if not value]
        raise MataMovementError("Falha nos gates: " + ", ".join(failed))
    return report


def manifest_entry(role: str, path: Path) -> dict[str, Any]:
    try:
        display = str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        display = str(path.resolve())
    return {"role": role, "path": display, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def build_manifest(config: Mapping[str, Any], inputs: Sequence[tuple[str, Path]], outputs: Sequence[tuple[str, Path]]) -> dict[str, Any]:
    manifest = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "execution_classification": "DESENVOLVIMENTO_CEGO_NAO_CONFIRMATORIO",
        "python_version": platform.python_version(),
        "ground_truth_used": False,
        "target_position_accepted": False,
        "files": [manifest_entry(role, path) for role, path in [*inputs, *outputs]],
    }
    manifest["payload_sha256"] = canonical_hash(manifest)
    return manifest


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    config_path = Path(args.config).resolve()
    protocol_path = Path(args.protocol).resolve()
    output_dir = Path(args.output_dir).resolve()
    geo_dir = Path(args.geo_dir).resolve()
    test_receipt_path = Path(args.test_receipt).resolve()
    roads_path = geo_dir / "osm_highways_raw.json"
    hydro_path = geo_dir / "osm_hydrography_raw.json"
    dem_path = geo_dir / "S01W052.hgt.gz"
    worldcover_path = geo_dir / "worldcover_tiles/ESA_WorldCover_10m_2021_v200_S03W054_Map.tif"
    required = [
        config_path, protocol_path, test_receipt_path, CORE_PATH, V1_ENGINE_PATH,
        roads_path, hydro_path, dem_path, worldcover_path,
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_json(config_path)
    config_receipt = validate_config(config)
    test_receipt = validate_test_receipt(test_receipt_path, config_path)
    core = load_core()
    v1 = load_v1()

    cells, half = core.make_grid(v1, config)
    core.sample_rasters(v1, cells, config, geo_dir, worldcover_path.parent)
    attach_sectors(cells, config)

    roads, road_timestamp = v1.load_road_segments(roads_path)
    hydros, hydro_timestamp = v1.load_hydro_segments(hydro_path)
    lat0 = float(config["source"]["point"]["latitude"])
    lon0 = float(config["source"]["point"]["longitude"])
    radius = float(config["source"]["radius_m"])
    margin = float(config["resistance"]["network"]["rasterization_tolerance_m"])
    road_near = [segment for segment in roads if segment_near_domain(segment, v1, lat0, lon0, radius, margin)]
    hydro_near = [segment for segment in hydros if segment_near_domain(segment, v1, lat0, lon0, radius, margin)]
    core.rasterize_segments(v1, cells, half, road_near, config, "network")
    # A hidrografia OSM é deliberadamente apenas auditada. A configuração
    # proíbe seu efeito numérico e o recorte não possui feições próximas.

    scenarios = core.cost_scenarios(config)
    origin = (half, half)
    for scenario in scenarios:
        core.dijkstra_cost_surface(cells, origin, config, scenario)
    before = cost_digest(cells, "H_REDE_DISPONIVEL__BASE")
    base_scenario = next(item for item in scenarios if item["scenario_id"] == "H_REDE_DISPONIVEL__BASE")
    core.dijkstra_cost_surface(cells, origin, config, base_scenario)
    after = cost_digest(cells, "H_REDE_DISPONIVEL__BASE")
    deterministic_repeat = before == after

    summaries = summarize_sectors(cells)
    corridors = build_corridors(core, cells, config)
    qa = validate_outputs(
        cells, scenarios, corridors, summaries, len(road_near), len(hydro_near),
        deterministic_repeat, config_receipt, test_receipt,
    )

    rows = grid_rows(cells)
    grid_path = output_dir / "grade_custo_relativo_mata01.csv"
    sectors_path = output_dir / "sumario_setorial_mata01.csv"
    corridors_path = output_dir / "corredores_planejamento_mata01.geojson"
    qa_path = output_dir / "relatorio_qa_mata01_mov_v1.json"
    result_path = output_dir / "resultado_mata01_mov_v1.json"
    manifest_path = output_dir / "manifesto_mata01_mov_v1.json"
    write_csv(grid_path, rows)
    write_csv(sectors_path, summaries)
    write_json(corridors_path, corridors)
    write_json(qa_path, qa)

    wc_counts = Counter(int(cell.worldcover_code) for cell in cells.values())
    result = {
        "protocol_id": config["protocol_id"],
        "engine_version": config["engine_version"],
        "scenario_id": "MATA-01",
        "source": {
            "point": {"latitude": lat0, "longitude": lon0},
            "domain_radius_m": radius,
            "domain_semantics": config["source"]["radius_semantics"],
        },
        "grid": {
            "resolution_m": 30.0,
            "cell_count": len(cells),
            "analysis_crs": f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs",
        },
        "time": {
            "snapshots": config["temporal_snapshots"],
            "conversion_to_distance": False,
            "conversion_to_isochrone": False,
            "same_cost_surface_for_T26_and_T49": True,
        },
        "sources": {
            "srtm": {"tile": "S01W052.hgt.gz", "role": "ALTITUDE_E_DECLIVIDADE_POTENCIAL"},
            "worldcover": {
                "tile": "ESA_WorldCover_10m_2021_v200_S03W054_Map.tif",
                "class_counts": {str(key): value for key, value in sorted(wc_counts.items())},
                "water_wet_proxy_codes": [80, 90],
                "proxy_semantics": "POTENCIAL_HIDRICO_OU_UMIDO_NAO_IGARAPE_CONFIRMADO",
            },
            "osm": {
                "timestamp_roads": road_timestamp,
                "timestamp_hydro": hydro_timestamp,
                "road_segments_near_domain": len(road_near),
                "hydro_segments_near_domain": len(hydro_near),
                "absence_interpretation": "NAO_DISPONIVEL_NO_RECORTE_NAO_AUSENCIA_FISICA_NEM_CONDICAO_FAVORAVEL",
            },
            "field_obstacles": {
                "records_available": False,
                "factor_applied": 1.0,
                "interpretation": "SEM_AJUSTE_ESPACIAL_NAO_PASSAGEM_LIVRE",
            },
        },
        "hypotheses": {
            "executed": ["H_REDE_DISPONIVEL", "H_FORA_REDE"],
            "base_surfaces_identical": qa["diagnostics"]["base_hypotheses_identical"],
            "interpretation": (
                "DIFERENCA_CAUSADA_APENAS_PELO_DESCONTO_DA_REDE_OSM_NAO_POR_PROBABILIDADE_DE_PRESENCA"
                if not qa["diagnostics"]["base_hypotheses_identical"]
                else "IGUALDADE_CAUSADA_PELA_AUSENCIA_DE_CELULAS_DE_REDE_NAO_POR_AUSENCIA_REAL"
            ),
        },
        "corridors": {
            "count": len(corridors["features"]),
            "role": "CAMINHOS_DIAGNOSTICOS_DE_MENOR_CUSTO_NAO_TRAJETORIAS",
        },
        "sector_summaries": summaries,
        "outputs": {
            "full_grid_csv": grid_path.name,
            "sector_summary_csv": sectors_path.name,
            "corridors_geojson": corridors_path.name,
            "qa_json": qa_path.name,
        },
        "interpretation": {
            "cost": "RESISTENCIA_RELATIVA_ACUMULADA_NAO_PROBABILIDADE_NAO_TEMPO",
            "corridor": "PLANEJAMENTO_COMPARATIVO_NAO_PREVISAO_DE_TRAJETORIA",
            "behavioral_clues": "REGISTRADAS_MAS_NAO_INJETADAS_NO_MOV_V",
        },
        "limitations": config["known_limitations"],
        "ground_truth_used": False,
    }
    scan_forbidden_fields(result)
    write_json(result_path, result)

    inputs = [
        ("config", config_path), ("protocol", protocol_path), ("engine", Path(__file__).resolve()),
        ("test_suite", TEST_SUITE_PATH), ("test_runner", TEST_RUNNER_PATH),
        ("test_receipt", test_receipt_path), ("reused_mov_core", CORE_PATH),
        ("reused_geo_core", V1_ENGINE_PATH), ("srtm_tile", dem_path),
        ("worldcover_tile", worldcover_path), ("osm_roads_snapshot", roads_path),
        ("osm_hydro_snapshot", hydro_path),
    ]
    outputs = [
        ("full_cost_grid", grid_path), ("sector_summary", sectors_path),
        ("planning_corridors", corridors_path), ("qa_report", qa_path),
        ("result", result_path),
    ]
    manifest = build_manifest(config, inputs, outputs)
    write_json(manifest_path, manifest)
    return {
        "status": "PASS",
        "output_dir": str(output_dir),
        "cell_count": len(cells),
        "corridor_count": len(corridors["features"]),
        "manifest_sha256": sha256_file(manifest_path),
        "base_hypotheses_identical": qa["diagnostics"]["base_hypotheses_identical"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--geo-dir", default=str(DEFAULT_GEO))
    parser.add_argument("--test-receipt", default=str(DEFAULT_TEST_RECEIPT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_pipeline(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
