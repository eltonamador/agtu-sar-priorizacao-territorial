#!/usr/bin/env python3
"""Verificador independente e somente leitura do processamento MATA-02/MZG2.

O programa não executa o motor, não altera artefatos e não corrige resultados. Ele
apenas audita um diretório de saída já produzido e emite um relatório JSON em
stdout. Qualquer falha de contrato resulta em código de saída diferente de zero.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EXPECTED_RADIUS_M = 6000.0
EXPECTED_SAMPLES_PER_SECTOR = 3600
EXPECTED_HYDRO_SEGMENTS = 28
EXPECTED_INTERPRETATION = (
    "PRIORIDADE_ANALITICA_TERRITORIAL_NAO_PROBABILIDADE_DE_PRESENCA"
)
EXPECTED_WEIGHTS = (0.30, 0.25, 0.20, 0.25)
RINGS = ("R01", "R02", "R03")
DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
EXPECTED_SECTOR_IDS = {f"{ring}-{direction}" for ring in RINGS for direction in DIRECTIONS}
FLOAT_TOL = 1e-8
AREA_REL_TOL = 1e-4

FEATURE_HINTS = ("feature", "caracter", "atribut")
RANKING_HINTS = ("ranking", "rank", "prior")
MANIFEST_HINTS = ("manifest", "manifesto")
DETERMINISM_HINTS = ("determin",)

SCORE_ALIASES = {
    "geo02": ("geo02_score", "geo_02_score", "geo02", "geo_02"),
    "geo03": ("geo03_score", "geo_03_score", "geo03", "geo_03"),
    "geo04": ("geo04_score", "geo_04_score", "geo04", "geo_04"),
    "geo05": ("geo05_score", "geo_05_score", "geo05", "geo_05"),
    "base": (
        "score_base",
        "base_score",
        "priority_score",
        "priority_score_base",
        "score",
    ),
}

REQUIRED_FALSE_FLAGS = (
    "ground_truth_available",
    "ground_truth_used",
    "hypothetical_elapsed_hours_used_in_base_ranking",
    "profile_used_in_quantitative_ranking",
    "directional_clue_used_in_quantitative_ranking",
    "photographs_used_in_quantitative_ranking",
    "drone_camera_coordinates_used_in_quantitative_ranking",
    "target_coordinate_available",
)

# Estes campos não podem estar presentes com conteúdo nos artefatos científicos.
# O arquivo de configuração de entrada não é varrido: ele pode documentar, de modo
# segregado, variáveis explicitamente excluídas do ranking.
PROHIBITED_DIRECT_FIELDS = {
    "ground_truth_lat",
    "ground_truth_lon",
    "ground_truth_coordinate",
    "ground_truth_coordinates",
    "target_lat",
    "target_lon",
    "target_coordinate",
    "target_coordinates",
    "declared_target_lat",
    "declared_target_lon",
    "declared_target_coordinate",
    "victim_lat",
    "victim_lon",
    "victim_coordinate",
    "victim_coordinates",
    "photo_path",
    "photo_paths",
    "photograph_path",
    "photograph_paths",
    "photographs",
    "photos",
    "images",
    "victim_profile",
    "profile_input",
    "behavioral_profile",
    "directional_clue",
    "directional_clues",
    "clue_input",
    "pista_direcional",
    "pistas_direcionais",
    "elapsed_hours",
    "hypothetical_elapsed_hours",
    "tempo_decorrido_horas",
    "exif_metadata",
    "photo_metadata",
    "photograph_metadata",
    "camera_lat",
    "camera_lon",
    "drone_camera_lat",
    "drone_camera_lon",
    "drone_camera_coordinate",
    "drone_camera_coordinates",
}


def keynorm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def textnorm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace(" ", "")
    if not text:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def as_int(value: Any) -> int | None:
    number = as_float(value)
    if number is None or not math.isclose(number, round(number), abs_tol=FLOAT_TOL):
        return None
    return int(round(number))


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    norm = textnorm(value)
    if norm in {"TRUE", "VERDADEIRO", "SIM", "YES", "Y", "1"}:
        return True
    if norm in {"FALSE", "FALSO", "NAO", "NO", "N", "0"}:
        return False
    return None


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or textnorm(value) in {"NULL", "NONE", "NA", "N_A"}
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value or "").strip()))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def normalized_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {keynorm(key): value for key, value in row.items()}


def first_value(mapping: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        alias_norm = keynorm(alias)
        if alias_norm in mapping and not is_empty(mapping[alias_norm]):
            return mapping[alias_norm]
    return None


def walk_json(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            child_path = path + (keynorm(raw_key),)
            yield child_path, child
            yield from walk_json(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = path + (str(index),)
            yield child_path, child
            yield from walk_json(child, child_path)


def canonical_sector(row: Mapping[str, Any]) -> str | None:
    norm = normalized_row(row)
    ring_raw = first_value(norm, ("ring_id", "ring", "anel", "anel_id"))
    direction_raw = first_value(norm, ("direction", "direction_id", "direcao", "azimuth_sector"))
    if ring_raw is not None and direction_raw is not None:
        ring_match = re.search(r"(?:R)?0?([123])", textnorm(ring_raw))
        direction = textnorm(direction_raw)
        if ring_match and direction in DIRECTIONS:
            return f"R0{ring_match.group(1)}-{direction}"

    sector_raw = first_value(norm, ("sector_id", "sector", "setor_id", "setor"))
    sector_text = textnorm(sector_raw)
    # Aceita tanto R01-N quanto IDs compostos como prefixo::R01::N.
    match = re.search(r"R0?([123])(?:_|::|-)(NE|NW|SE|SW|N|E|S|W)(?:$|_)", sector_text + "_")
    if match:
        return f"R0{match.group(1)}-{match.group(2)}"
    return None


def candidate_csvs(root: Path) -> list[tuple[Path, list[dict[str, str]]]]:
    candidates: list[tuple[Path, list[dict[str, str]]]] = []
    for path in sorted(root.rglob("*.csv")):
        try:
            rows = read_csv(path)
        except (OSError, UnicodeError, csv.Error):
            continue
        if rows:
            candidates.append((path, rows))
    return candidates


def select_feature_and_ranking(
    root: Path,
) -> tuple[Path, list[dict[str, str]], Path, list[dict[str, str]]]:
    candidates = candidate_csvs(root)
    feature_choices: list[tuple[int, Path, list[dict[str, str]]]] = []
    ranking_choices: list[tuple[int, Path, list[dict[str, str]]]] = []
    for path, rows in candidates:
        headers = {keynorm(key) for key in rows[0]}
        ids = {canonical_sector(row) for row in rows}
        has_24 = len(rows) == 24 and None not in ids and len(ids) == 24
        has_geo = all(any(keynorm(alias) in headers for alias in SCORE_ALIASES[name]) for name in ("geo02", "geo03", "geo04", "geo05"))
        has_base = any(keynorm(alias) in headers for alias in SCORE_ALIASES["base"])
        has_rank = any(key in headers for key in ("sector_rank", "rank_base_within_buffer", "rank", "ranking"))
        hint_text = keynorm(path.name)
        if has_24 and has_geo:
            feature_score = 100 + sum(hint in hint_text for hint in FEATURE_HINTS) * 10 - int(has_base)
            feature_choices.append((feature_score, path, rows))
        if has_24 and has_geo and has_base and has_rank:
            rank_score = 100 + sum(hint in hint_text for hint in RANKING_HINTS) * 10
            ranking_choices.append((rank_score, path, rows))
    if not feature_choices:
        raise ValueError("Nenhum CSV de 24 setores com GEO02-GEO05 foi localizado")
    if not ranking_choices:
        raise ValueError("Nenhum CSV de ranking de 24 setores com BASE foi localizado")
    _, feature_path, feature_rows = max(feature_choices, key=lambda item: (item[0], str(item[1])))
    _, ranking_path, ranking_rows = max(ranking_choices, key=lambda item: (item[0], str(item[1])))
    return feature_path, feature_rows, ranking_path, ranking_rows


@dataclass
class Audit:
    root: Path
    checks: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def check(self, condition: bool, code: str, message: str, evidence: Any = None) -> None:
        item: dict[str, Any] = {"code": code, "ok": bool(condition), "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        self.checks.append(item)
        if not condition:
            self.failures.append(f"{code}: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.failures


def collect_json_artifacts(root: Path) -> list[tuple[Path, Any]]:
    artifacts: list[tuple[Path, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            artifacts.append((path, read_json(path)))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    return artifacts


def scalar_occurrences(
    json_artifacts: Sequence[tuple[Path, Any]], aliases: Sequence[str]
) -> list[tuple[Path, str, Any]]:
    wanted = {keynorm(alias) for alias in aliases}
    found: list[tuple[Path, str, Any]] = []
    for file_path, document in json_artifacts:
        for path, value in walk_json(document):
            if path and path[-1] in wanted and not isinstance(value, (dict, list)):
                found.append((file_path, ".".join(path), value))
    return found


def csv_occurrences(
    tables: Sequence[tuple[Path, Sequence[Mapping[str, Any]]]], aliases: Sequence[str]
) -> list[tuple[Path, str, Any]]:
    wanted = {keynorm(alias) for alias in aliases}
    found: list[tuple[Path, str, Any]] = []
    for file_path, rows in tables:
        for row_index, row in enumerate(rows, start=2):
            for raw_key, value in row.items():
                if keynorm(raw_key) in wanted and not is_empty(value):
                    found.append((file_path, f"linha {row_index}.{raw_key}", value))
    return found


def all_occurrences(
    json_artifacts: Sequence[tuple[Path, Any]],
    tables: Sequence[tuple[Path, Sequence[Mapping[str, Any]]]],
    aliases: Sequence[str],
) -> list[tuple[Path, str, Any]]:
    return scalar_occurrences(json_artifacts, aliases) + csv_occurrences(tables, aliases)


def audit_sector_identity(audit: Audit, rows: Sequence[Mapping[str, Any]], label: str) -> None:
    ids = [canonical_sector(row) for row in rows]
    audit.check(len(rows) == 24, f"{label}.row_count", f"{label} deve conter exatamente 24 linhas", len(rows))
    audit.check(None not in ids, f"{label}.ids_parseable", f"Todos os IDs de {label} devem ser reconhecíveis", ids)
    actual = {sector for sector in ids if sector is not None}
    audit.check(
        actual == EXPECTED_SECTOR_IDS and len(ids) == len(set(ids)),
        f"{label}.ids_exact",
        f"{label} deve conter exatamente R01-R03 × 8 direções, sem duplicatas",
        {"missing": sorted(EXPECTED_SECTOR_IDS - actual), "extra": sorted(actual - EXPECTED_SECTOR_IDS)},
    )


def audit_samples(audit: Audit, rows: Sequence[Mapping[str, Any]]) -> None:
    families = {
        "terrain": {
            "expected": ("terrain_expected_sample_count", "terrain_samples_expected", "dem_expected_sample_count"),
            "valid": ("terrain_sample_count", "terrain_valid_sample_count", "terrain_samples_valid", "dem_sample_count"),
        },
        "worldcover": {
            "expected": ("worldcover_expected_sample_count", "worldcover_samples_expected", "landcover_expected_sample_count"),
            "valid": ("worldcover_sample_count", "worldcover_valid_sample_count", "worldcover_samples_valid", "landcover_sample_count"),
        },
    }
    for family, aliases in families.items():
        expected_values: list[int | None] = []
        valid_values: list[int | None] = []
        for row in rows:
            norm = normalized_row(row)
            expected_values.append(as_int(first_value(norm, aliases["expected"])))
            valid_values.append(as_int(first_value(norm, aliases["valid"])))
        audit.check(
            all(value == EXPECTED_SAMPLES_PER_SECTOR for value in expected_values),
            f"samples.{family}.expected",
            f"Cada setor deve declarar {EXPECTED_SAMPLES_PER_SECTOR} amostras esperadas de {family}",
            expected_values,
        )
        audit.check(
            all(value == EXPECTED_SAMPLES_PER_SECTOR for value in valid_values),
            f"samples.{family}.valid",
            f"Cada setor deve ter {EXPECTED_SAMPLES_PER_SECTOR} amostras válidas de {family}",
            valid_values,
        )


def audit_radius_and_area(
    audit: Audit,
    feature_rows: Sequence[Mapping[str, Any]],
    ranking_rows: Sequence[Mapping[str, Any]],
    json_artifacts: Sequence[tuple[Path, Any]],
) -> None:
    tables = [(Path("feature"), feature_rows), (Path("ranking"), ranking_rows)]
    radius_aliases = (
        "source_radius_m",
        "buffer_radius_m",
        "domain_radius_m",
        "received_source_radius_m",
        "authoritative_radius_m",
    )
    radius_values = [as_float(value) for _, _, value in all_occurrences(json_artifacts, tables, radius_aliases)]
    radius_values = [value for value in radius_values if value is not None]
    outer_values: list[float] = []
    for row in feature_rows:
        value = as_float(first_value(normalized_row(row), ("outer_radius_m", "ring_outer_radius_m")))
        if value is not None:
            outer_values.append(value)
    exact_radius_present = any(math.isclose(value, EXPECTED_RADIUS_M, abs_tol=1e-6) for value in radius_values)
    exact_outer = bool(outer_values) and math.isclose(max(outer_values), EXPECTED_RADIUS_M, abs_tol=1e-6)
    audit.check(
        exact_radius_present and exact_outer,
        "domain.radius_6000",
        "O domínio autoritativo e o raio externo máximo devem ser exatamente 6.000 m",
        {"radius_values": radius_values, "outer_radius_max": max(outer_values) if outer_values else None},
    )
    conflicting = [value for value in radius_values if not math.isclose(value, EXPECTED_RADIUS_M, abs_tol=1e-6)]
    audit.check(
        not conflicting,
        "domain.no_conflicting_radius",
        "Não pode existir raio autoritativo conflitante com 6.000 m",
        conflicting,
    )

    theoretical_total = math.pi * EXPECTED_RADIUS_M**2
    theoretical_sector = theoretical_total / 24.0
    areas: list[float | None] = []
    for row in feature_rows:
        norm = normalized_row(row)
        area = as_float(first_value(norm, ("polygon_planar_area_m2", "sector_area_m2", "area_m2")))
        areas.append(area)
    audit.check(
        all(area is not None and area > 0 for area in areas),
        "area.present_positive",
        "Todos os 24 setores devem ter área planar positiva",
        areas,
    )
    valid_areas = [area for area in areas if area is not None]
    if len(valid_areas) == 24:
        rel_errors = [abs(area - theoretical_sector) / theoretical_sector for area in valid_areas]
        total_rel_error = abs(sum(valid_areas) - theoretical_total) / theoretical_total
        conservation_values: list[float] = []
        for row in feature_rows:
            value = as_float(first_value(normalized_row(row), ("area_relative_error", "relative_area_error")))
            if value is not None:
                conservation_values.append(abs(value))
        audit.check(
            max(rel_errors) <= AREA_REL_TOL,
            "area.equal_area",
            f"Cada setor deve conservar 1/24 do buffer com erro relativo ≤ {AREA_REL_TOL}",
            {"max_relative_error": max(rel_errors), "theoretical_sector_area_m2": theoretical_sector},
        )
        audit.check(
            total_rel_error <= AREA_REL_TOL,
            "area.total_conservation",
            f"A soma das áreas deve conservar π·6000² com erro relativo ≤ {AREA_REL_TOL}",
            {"relative_error": total_rel_error, "sum_m2": sum(valid_areas), "theoretical_m2": theoretical_total},
        )
        if conservation_values:
            audit.check(
                max(conservation_values) <= AREA_REL_TOL,
                "area.declared_conservation",
                "Os erros de conservação declarados devem respeitar a tolerância",
                max(conservation_values),
            )


def row_score(row: Mapping[str, Any], score_name: str) -> float | None:
    return as_float(first_value(normalized_row(row), SCORE_ALIASES[score_name]))


def audit_scores_and_recomposition(
    audit: Audit,
    feature_rows: Sequence[Mapping[str, Any]],
    ranking_rows: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    for label, rows in (("feature", feature_rows), ("ranking", ranking_rows)):
        for score_name in ("geo02", "geo03", "geo04", "geo05"):
            values = [row_score(row, score_name) for row in rows]
            audit.check(
                all(value is not None and 0.0 <= value <= 1.0 for value in values),
                f"scores.{label}.{score_name}.range",
                f"{score_name.upper()} de {label} deve existir e pertencer a [0,1] em todos os setores",
                values,
            )

    actual_scores: dict[str, float] = {}
    residuals: list[float] = []
    for row in ranking_rows:
        sector = canonical_sector(row)
        components = [row_score(row, name) for name in ("geo02", "geo03", "geo04", "geo05")]
        base = row_score(row, "base")
        if sector is None or base is None or any(value is None for value in components):
            continue
        expected = sum(weight * float(value) for weight, value in zip(EXPECTED_WEIGHTS, components))
        residuals.append(abs(base - expected))
        actual_scores[sector] = base
    base_values = [row_score(row, "base") for row in ranking_rows]
    audit.check(
        all(value is not None and 0.0 <= value <= 1.0 for value in base_values),
        "scores.base.range",
        "O escore BASE completo deve existir e pertencer a [0,1] em todos os setores",
        base_values,
    )
    audit.check(
        len(residuals) == 24 and max(residuals, default=math.inf) <= FLOAT_TOL,
        "scores.base.recomposition",
        "BASE deve recompor exatamente 0,30·GEO02 + 0,25·GEO03 + 0,20·GEO04 + 0,25·GEO05",
        {"max_absolute_residual": max(residuals, default=None), "weights": EXPECTED_WEIGHTS},
    )
    return actual_scores


def audit_hydrology(
    audit: Audit,
    json_artifacts: Sequence[tuple[Path, Any]],
    feature_rows: Sequence[Mapping[str, Any]],
    ranking_rows: Sequence[Mapping[str, Any]],
) -> None:
    tables = [(Path("feature"), feature_rows), (Path("ranking"), ranking_rows)]
    branch_aliases = (
        "hydro_branch",
        "hydrography_branch",
        "geo03_branch",
        "geo03_data_branch",
        "selected_hydrography_branch",
        "hydrography_branch_id",
    )
    branches = [textnorm(value) for _, _, value in all_occurrences(json_artifacts, tables, branch_aliases)]
    audit.check(bool(branches), "hydro.branch.present", "O ramo hidrográfico selecionado deve ser declarado")
    audit.check(
        bool(branches) and all(value in {"H1", "BRANCH_H1", "RAMO_H1"} for value in branches),
        "hydro.branch.h1",
        "O processamento deve usar exclusivamente o ramo H1",
        branches,
    )

    count_values: list[int] = []
    exact_aliases = {
        "hydro_domain_segment_count",
        "hydrography_domain_segment_count",
        "hydrography_intersecting_segment_count",
        "intersecting_hydro_segments",
        "geo03_segment_count",
        "hydro_segment_count",
    }
    for file_path, document in json_artifacts:
        for path, value in walk_json(document):
            if not path:
                continue
            leaf = path[-1]
            parent_text = "_".join(path[:-1])
            hydrological_context = any(token in parent_text for token in ("hydro", "hidro", "geo03", "geo_03"))
            is_count_leaf = leaf in exact_aliases or (hydrological_context and leaf in {"segment_count", "segments_count", "feature_count", "features_count"})
            if is_count_leaf:
                parsed = as_int(value)
                if parsed is not None:
                    count_values.append(parsed)
    for _, _, value in csv_occurrences(tables, tuple(exact_aliases)):
        parsed = as_int(value)
        if parsed is not None:
            count_values.append(parsed)
    audit.check(bool(count_values), "hydro.count.present", "A contagem de segmentos hidrográficos deve ser declarada")
    audit.check(
        bool(count_values) and all(value == EXPECTED_HYDRO_SEGMENTS for value in count_values),
        "hydro.count.exact_28",
        "O recorte real deve registrar exatamente 28 segmentos hidrográficos intersectantes",
        sorted(set(count_values)),
    )

    output_kind = [
        textnorm(value)
        for _, _, value in all_occurrences(
            json_artifacts,
            tables,
            ("principal_output", "ranking_mode", "score_mode", "base_mode", "output_mode"),
        )
    ]
    diagnostic_markers = (
        "DIAGNOST",
        "BASE_AVAILABLE_COMPONENTS",
        "BASE_DISPONIVEIS",
        "AVAILABLE_COMPONENTS_ONLY",
        "COMPONENTES_DISPONIVEIS",
    )
    audit.check(
        not any(any(marker in value for marker in diagnostic_markers) for value in output_kind),
        "hydro.base_not_diagnostic",
        "Com H1/28, a saída não pode ser BASE-DISPONÍVEIS nem diagnóstica",
        output_kind,
    )


def expected_competition_ranks(scores: Mapping[str, float]) -> dict[str, int]:
    return {
        sector: 1 + sum(other > score + FLOAT_TOL for other in scores.values())
        for sector, score in scores.items()
    }


def audit_ranking_status(
    audit: Audit,
    ranking_rows: Sequence[Mapping[str, Any]],
    scores: Mapping[str, float],
    json_artifacts: Sequence[tuple[Path, Any]],
) -> None:
    expected_ranks = expected_competition_ranks(scores)
    rank_aliases = ("rank_base_within_buffer", "sector_rank", "rank", "ranking")
    rank_errors: list[dict[str, Any]] = []
    for row in ranking_rows:
        sector = canonical_sector(row)
        actual = as_int(first_value(normalized_row(row), rank_aliases))
        expected = expected_ranks.get(sector or "")
        if sector is None or actual is None or expected is None or actual != expected:
            rank_errors.append({"sector": sector, "actual": actual, "expected": expected})
    audit.check(not rank_errors, "ranking.ranks", "Os postos devem corresponder à ordenação decrescente de BASE", rank_errors)

    ordered = sorted(scores.values(), reverse=True)
    expected_margin = ordered[0] - ordered[1] if len(ordered) >= 2 else None
    margin_aliases = ("rank_margin", "top1_top2_margin", "margin", "decision_margin")
    margin_values = [
        as_float(value)
        for _, _, value in all_occurrences(
            json_artifacts,
            [(Path("ranking"), ranking_rows)],
            margin_aliases,
        )
    ]
    margin_values = [value for value in margin_values if value is not None]
    audit.check(bool(margin_values), "ranking.margin.present", "A margem Top-1−Top-2 deve ser declarada")
    audit.check(
        bool(margin_values)
        and expected_margin is not None
        and all(math.isclose(value, expected_margin, abs_tol=FLOAT_TOL) for value in margin_values),
        "ranking.margin.consistent",
        "A margem declarada deve ser igual a BASE(Top-1) − BASE(Top-2)",
        {"declared": sorted(set(margin_values)), "recomputed": expected_margin},
    )

    # O estado precisa derivar de um gate estruturado. Textos livres de warning não
    # são usados como evidência de decisão.
    gate_aliases = (
        "decision_gate_passed",
        "base_decision_gate_passed",
        "prioritization_gate_passed",
        "all_decision_gates_passed",
        "ranking_gate_passed",
    )
    gate_values = [
        as_bool(value)
        for _, _, value in all_occurrences(
            json_artifacts,
            [(Path("ranking"), ranking_rows)],
            gate_aliases,
        )
    ]
    gate_values = [value for value in gate_values if value is not None]
    audit.check(bool(gate_values), "status.structured_gate", "Um gate decisório booleano estruturado deve ser publicado")
    audit.check(
        len(set(gate_values)) <= 1,
        "status.gate_consistent",
        "Os valores estruturados do gate não podem ser contraditórios",
        gate_values,
    )
    expected_status = "PRIORIZADO" if gate_values and gate_values[0] else "REVISAR"
    status_values = [
        textnorm(value)
        for _, _, value in all_occurrences(
            json_artifacts,
            [(Path("ranking"), ranking_rows)],
            ("decision_status", "status", "ranking_status", "base_status"),
        )
        if textnorm(value) in {"PRIORIZADO", "REVISAR", "ABSTIDO"}
    ]
    audit.check(bool(status_values), "status.present", "O status decisório deve ser publicado")
    audit.check(
        bool(status_values) and all(value == expected_status for value in status_values),
        "status.consistent_with_gate",
        "O status deve ser derivado do gate estruturado e, com H1/28, não pode ser ABSTIDO",
        {"statuses": status_values, "expected": expected_status, "gate": gate_values},
    )


def audit_interpretation_and_blinding(
    audit: Audit,
    json_artifacts: Sequence[tuple[Path, Any]],
    feature_path: Path,
    feature_rows: Sequence[Mapping[str, Any]],
    ranking_path: Path,
    ranking_rows: Sequence[Mapping[str, Any]],
) -> None:
    tables = [(feature_path, feature_rows), (ranking_path, ranking_rows)]
    interpretations = [
        textnorm(value)
        for _, _, value in all_occurrences(
            json_artifacts,
            tables,
            ("score_meaning", "score_interpretation", "interpretation", "interpretacao_do_score"),
        )
    ]
    audit.check(bool(interpretations), "interpretation.present", "A interpretação do escore deve ser declarada")
    audit.check(
        bool(interpretations) and all(value == EXPECTED_INTERPRETATION for value in interpretations),
        "interpretation.not_probability",
        "O escore deve ser identificado exatamente como prioridade analítica, não probabilidade de presença",
        interpretations,
    )

    for flag in REQUIRED_FALSE_FLAGS:
        occurrences = all_occurrences(json_artifacts, tables, (flag,))
        values = [as_bool(value) for _, _, value in occurrences]
        audit.check(bool(occurrences), f"blinding.{flag}.present", f"O artefato deve declarar {flag}=false")
        audit.check(
            bool(occurrences) and all(value is False for value in values),
            f"blinding.{flag}.false",
            f"Todos os registros de {flag} devem ser booleanamente false",
            [value for _, _, value in occurrences],
        )

    leaks: list[dict[str, Any]] = []
    prohibited = {keynorm(key) for key in PROHIBITED_DIRECT_FIELDS}
    # Apenas artefatos de saída, nunca o config de entrada segregado.
    for file_path, document in json_artifacts:
        for path, value in walk_json(document):
            if path and path[-1] in prohibited and not is_empty(value):
                leaks.append({"file": str(file_path), "field": ".".join(path), "value_preview": str(value)[:120]})
    for file_path, rows in tables:
        for row_index, row in enumerate(rows, start=2):
            for raw_key, value in row.items():
                if keynorm(raw_key) in prohibited and not is_empty(value):
                    leaks.append({"file": str(file_path), "field": f"linha {row_index}.{raw_key}", "value_preview": str(value)[:120]})
    audit.check(
        not leaks,
        "blinding.no_prohibited_direct_inputs",
        "Fotos, perfil, pistas, tempo, metadados de câmera e alvo não podem contaminar os artefatos científicos",
        leaks,
    )


def resolve_manifest_path(raw_path: Any, manifest_path: Path, output_root: Path) -> Path | None:
    if is_empty(raw_path):
        return None
    candidate = Path(str(raw_path)).expanduser()
    possibilities = [candidate] if candidate.is_absolute() else [manifest_path.parent / candidate, output_root / candidate]
    for possibility in possibilities:
        try:
            resolved = possibility.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def manifest_entries(document: Any) -> list[Mapping[str, Any]]:
    if not isinstance(document, Mapping):
        return []
    for key in ("files", "arquivos", "artifacts", "artefatos", "entries", "itens"):
        value = document.get(key)
        if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
            return list(value)
    return []


def audit_manifests(
    audit: Audit,
    json_artifacts: Sequence[tuple[Path, Any]],
    feature_path: Path,
    ranking_path: Path,
) -> None:
    manifests = [
        (path, document)
        for path, document in json_artifacts
        if any(hint in keynorm(path.name) for hint in MANIFEST_HINTS)
    ]
    audit.check(bool(manifests), "manifest.present", "Ao menos um manifesto de hashes deve existir")
    covered: set[Path] = set()
    entry_count = 0
    for manifest_path, document in manifests:
        entries = manifest_entries(document)
        audit.check(bool(entries), "manifest.entries", f"Manifesto {manifest_path.name} deve conter uma lista de arquivos")
        for index, entry in enumerate(entries):
            entry_count += 1
            norm = normalized_row(entry)
            raw_path = first_value(norm, ("path", "file", "filepath", "arquivo", "relative_path"))
            declared_hash = first_value(norm, ("sha256", "sha_256", "hash_sha256", "hash"))
            context = f"{manifest_path.name}[{index}]"
            audit.check(not is_empty(raw_path), "manifest.path", f"{context} deve declarar o caminho")
            audit.check(valid_sha256(declared_hash), "manifest.sha_format", f"{context} deve declarar SHA-256 hexadecimal válido")
            resolved = resolve_manifest_path(raw_path, manifest_path, audit.root)
            audit.check(resolved is not None, "manifest.resolve", f"{context} deve resolver para um arquivo existente", raw_path)
            if resolved is None or not valid_sha256(declared_hash):
                continue
            actual_hash = sha256_file(resolved)
            audit.check(
                actual_hash.lower() == str(declared_hash).strip().lower(),
                "manifest.sha_match",
                f"{context} deve corresponder aos bytes reais",
                {"file": str(resolved), "declared": declared_hash, "actual": actual_hash},
            )
            covered.add(resolved.resolve())
    audit.check(entry_count > 0, "manifest.nonempty", "Os manifestos não podem estar vazios")
    audit.check(
        feature_path.resolve() in covered,
        "manifest.feature_covered",
        "O CSV de características deve estar coberto pelo manifesto",
        str(feature_path),
    )
    audit.check(
        ranking_path.resolve() in covered,
        "manifest.ranking_covered",
        "O CSV de ranking deve estar coberto pelo manifesto",
        str(ranking_path),
    )


def find_determinism_reports(json_artifacts: Sequence[tuple[Path, Any]]) -> list[tuple[Path, Any]]:
    return [
        (path, document)
        for path, document in json_artifacts
        if any(hint in keynorm(path.name) for hint in DETERMINISM_HINTS)
    ]


def determinism_entries(document: Any) -> list[Mapping[str, Any]]:
    if not isinstance(document, Mapping):
        return []
    for key in ("files", "arquivos", "artifacts", "artefatos", "comparisons", "comparacoes"):
        value = document.get(key)
        if isinstance(value, list) and all(isinstance(item, Mapping) for item in value):
            return list(value)
    return []


def audit_embedded_determinism(
    audit: Audit,
    json_artifacts: Sequence[tuple[Path, Any]],
    feature_path: Path,
    ranking_path: Path,
) -> None:
    reports = find_determinism_reports(json_artifacts)
    audit.check(bool(reports), "determinism.report_present", "Sem --compare-output-dir, exige-se relatório detalhado de duas execuções")
    covered: set[str] = set()
    detailed_entries = 0
    for report_path, document in reports:
        for entry in determinism_entries(document):
            norm = normalized_row(entry)
            raw_file = first_value(norm, ("file", "path", "arquivo", "relative_path"))
            run1 = first_value(norm, ("run1_sha256", "sha256_run1", "first_run_sha256", "run_a_sha256"))
            run2 = first_value(norm, ("run2_sha256", "sha256_run2", "second_run_sha256", "run_b_sha256"))
            equal = as_bool(first_value(norm, ("equal", "identical", "hashes_equal", "sha256_equal")))
            if is_empty(raw_file) or not valid_sha256(run1) or not valid_sha256(run2):
                continue
            detailed_entries += 1
            file_name = Path(str(raw_file)).name
            covered.add(file_name)
            audit.check(
                str(run1).lower() == str(run2).lower() and equal is True,
                "determinism.two_runs_equal",
                f"As duas execuções devem ter hashes idênticos para {file_name}",
                {"run1": run1, "run2": run2, "equal": equal},
            )
            actual_path = feature_path if file_name == feature_path.name else ranking_path if file_name == ranking_path.name else None
            if actual_path is not None:
                actual = sha256_file(actual_path)
                audit.check(
                    actual.lower() == str(run1).lower(),
                    "determinism.current_matches_run",
                    f"O artefato atual {file_name} deve coincidir com os hashes das duas execuções",
                    {"actual": actual, "reported": run1},
                )
    audit.check(
        detailed_entries > 0,
        "determinism.detailed_entries",
        "Um booleano isolado não basta: o relatório deve listar run1_sha256 e run2_sha256 por arquivo",
    )
    audit.check(
        feature_path.name in covered and ranking_path.name in covered,
        "determinism.scientific_outputs_covered",
        "O relatório de duas execuções deve cobrir características e ranking",
        {"covered": sorted(covered), "required": [feature_path.name, ranking_path.name]},
    )


def audit_output_dir(root: Path, require_embedded_determinism: bool) -> tuple[Audit, Path | None, Path | None]:
    audit = Audit(root=root)
    audit.check(root.exists() and root.is_dir(), "output.directory", "--output-dir deve apontar para diretório existente", str(root))
    if not audit.ok:
        return audit, None, None
    try:
        feature_path, feature_rows, ranking_path, ranking_rows = select_feature_and_ranking(root)
    except ValueError as error:
        audit.check(False, "artifacts.csv_discovery", str(error))
        return audit, None, None

    audit.evidence["feature_csv"] = str(feature_path)
    audit.evidence["ranking_csv"] = str(ranking_path)
    audit_sector_identity(audit, feature_rows, "feature")
    audit_sector_identity(audit, ranking_rows, "ranking")
    audit_samples(audit, feature_rows)
    json_artifacts = collect_json_artifacts(root)
    audit_radius_and_area(audit, feature_rows, ranking_rows, json_artifacts)
    scores = audit_scores_and_recomposition(audit, feature_rows, ranking_rows)
    audit_hydrology(audit, json_artifacts, feature_rows, ranking_rows)
    audit_ranking_status(audit, ranking_rows, scores, json_artifacts)
    audit_interpretation_and_blinding(
        audit, json_artifacts, feature_path, feature_rows, ranking_path, ranking_rows
    )
    audit_manifests(audit, json_artifacts, feature_path, ranking_path)
    if require_embedded_determinism:
        audit_embedded_determinism(audit, json_artifacts, feature_path, ranking_path)
    return audit, feature_path, ranking_path


def compare_two_runs(
    primary_audit: Audit,
    primary_feature: Path | None,
    primary_ranking: Path | None,
    secondary_root: Path,
) -> Audit:
    secondary_audit, secondary_feature, secondary_ranking = audit_output_dir(
        secondary_root, require_embedded_determinism=False
    )
    primary_audit.evidence["comparison_output_dir"] = str(secondary_root)
    primary_audit.check(
        secondary_audit.ok,
        "determinism.second_run_valid",
        "A segunda execução deve passar pela mesma auditoria científica",
        secondary_audit.failures,
    )
    # Anexa as checagens da segunda execução com prefixo, preservando a leitura do
    # relatório sem mascarar qualquer falha.
    for check in secondary_audit.checks:
        cloned = dict(check)
        cloned["code"] = f"run2.{check['code']}"
        primary_audit.checks.append(cloned)
    primary_audit.warnings.extend(f"run2: {item}" for item in secondary_audit.warnings)

    pairs = (
        ("feature", primary_feature, secondary_feature),
        ("ranking", primary_ranking, secondary_ranking),
    )
    for label, first, second in pairs:
        present = first is not None and second is not None
        primary_audit.check(present, f"determinism.{label}.present_both", f"As duas execuções devem conter {label}")
        if not present:
            continue
        first_hash = sha256_file(first)
        second_hash = sha256_file(second)
        primary_audit.check(
            first_hash == second_hash,
            f"determinism.{label}.sha256_equal",
            f"Os bytes de {label} devem ser idênticos em duas execuções independentes",
            {"run1": first_hash, "run2": second_hash, "run1_file": str(first), "run2_file": str(second)},
        )
    return secondary_audit


def report_dict(audit: Audit) -> dict[str, Any]:
    return {
        "verifier": "verify_mata02_mzg2.py",
        "mode": "READ_ONLY_STRICT",
        "output_dir": str(audit.root),
        "status": "PASS" if audit.ok else "FAIL",
        "summary": {
            "checks_total": len(audit.checks),
            "checks_passed": sum(bool(item["ok"]) for item in audit.checks),
            "checks_failed": sum(not bool(item["ok"]) for item in audit.checks),
            "warnings": len(audit.warnings),
        },
        "evidence": audit.evidence,
        "failures": audit.failures,
        "warnings": audit.warnings,
        "checks": audit.checks,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita, sem modificar arquivos, a saída cega MATA-02/MZG2."
    )
    parser.add_argument("--output-dir", required=True, type=Path, help="Diretório da primeira execução")
    parser.add_argument(
        "--compare-output-dir",
        type=Path,
        help="Diretório de uma segunda execução independente para prova de determinismo",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    compare_dir = args.compare_output_dir.expanduser().resolve() if args.compare_output_dir else None
    audit, feature_path, ranking_path = audit_output_dir(
        output_dir, require_embedded_determinism=compare_dir is None
    )
    if compare_dir is not None:
        compare_two_runs(audit, feature_path, ranking_path, compare_dir)
    report = report_dict(audit)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    summary = report["summary"]
    print(
        f"MATA-02/MZG2: {report['status']} — "
        f"{summary['checks_passed']}/{summary['checks_total']} checagens aprovadas; "
        f"{summary['checks_failed']} falha(s).",
        file=sys.stderr,
    )
    if audit.failures:
        for failure in audit.failures:
            print(f"- {failure}", file=sys.stderr)
    return 0 if audit.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
