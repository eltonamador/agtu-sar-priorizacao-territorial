#!/usr/bin/env python3
"""Valida e separa a preparação da validação independente REP-S.

O utilitário implementa um *firewall* lógico entre:

* a entrada cega que pode ser entregue ao motor espacial; e
* o arquivo reservado de ``ground truth``, que somente deve ser aberto depois
  do congelamento das saídas do modelo.

Nenhuma coordenada de referência é incluída nos manifestos ou relatórios. O
manifesto público contém somente contagens, estado dos gates e hashes SHA-256,
o que permite comprovar a anterioridade do arquivo reservado sem revelar seu
conteúdo.

Uso principal::

    python export_rep_s_firewall.py prepare kit_rep_s.xlsx pacote_rep_s
    python export_rep_s_firewall.py freeze-output saida_modelo \
        pacote_rep_s/manifesto_preparacao_rep_s.json \
        --config config_buffer_v1.json --engine motor_buffer_adaptativo.py \
        --test-evidence resultado_testes.json --repeat-output saida_modelo_repetida \
        --engine-manifest saida_modelo/manifest_execucao.json \
        --repeat-engine-manifest saida_modelo_repetida/manifest_execucao.json

O primeiro comando requer as abas ``ENTRADA_CEGA`` e
``GROUND_TRUTH_LOCKED``. ``PLANO_SITES`` também é obrigatório em qualquer
pacote que contenha REP-S. Linhas inteiramente vazias são ignoradas.
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from openpyxl import load_workbook
except ImportError as exc:  # pragma: no cover - depende do ambiente de execução
    raise SystemExit(
        "Dependência ausente: instale/forneça openpyxl para ler o workbook REP-S."
    ) from exc


PROTOCOL_ID = "EXT-ESP-REP-S-v1.0"
SCRIPT_VERSION = "1.2.0"

BLIND_SHEET = "ENTRADA_CEGA"
GT_SHEET = "GROUND_TRUTH_LOCKED"
PLAN_SHEET = "PLANO_SITES"

BLIND_REQUIRED_COLUMNS = (
    "scenario_id",
    "candidate_id",
    "site_id",
    "estimated_lat",
    "estimated_lon",
    "base_radius_m",
    "detection_quality",
    "r0_semantics",
    "execution_phase",
)

GT_REQUIRED_COLUMNS = (
    "site_id",
    "scenario_id",
    "ground_truth_lat",
    "ground_truth_lon",
    "collection_method",
    "ground_truth_status",
    "custody_status",
)

BLIND_FORBIDDEN_EXACT = {
    "ground_truth",
    "ground_truth_lat",
    "ground_truth_lon",
    "ground_truth_used",
    "gt_lat",
    "gt_lon",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "latitude_real",
    "longitude_real",
    "posicao_real",
    "position_real",
    "distance_to_ground_truth_m",
    "distance_to_reference_m",
    "generator_distance_m",
    "is_correct_candidate",
    "relevant_candidate",
    "rank_against_truth",
    "victim_lat",
    "victim_lon",
    "target_lat",
    "target_lon",
    "actual_lat",
    "actual_lon",
    "distance_to_truth",
    "hit_truth",
    "inside_buffer",
}

BLIND_FORBIDDEN_FRAGMENTS = (
    "ground_truth",
    "reference_lat",
    "reference_lon",
    "true_lat",
    "true_lon",
    "latitude_real",
    "longitude_real",
    "posicao_real",
    "position_real",
    "distance_to_ground",
    "distance_to_reference",
    "generator_distance",
    "correct_candidate",
    "relevant_candidate",
    "rank_against_truth",
    "victim_lat",
    "victim_lon",
    "target_lat",
    "target_lon",
    "actual_lat",
    "actual_lon",
    "distance_to_truth",
    "hit_truth",
    "inside_buffer",
)

GT_FORBIDDEN_EXACT = {
    "candidate_id",
    "estimated_lat",
    "estimated_lon",
    "candidate_lat",
    "candidate_lon",
    "adaptive_radius_m",
    "priority_score",
    "candidate_rank",
    "selected_candidate",
}

GT_FORBIDDEN_FRAGMENTS = (
    "candidate_rank",
    "priority_score",
    "selected_candidate",
    "adaptive_radius",
)

R0_SEMANTICS = {"nominal_base", "source_adjusted", "diagnostic_legacy"}
CONFIRMATORY_PHASES = {"REP-S", "REP_S", "REP_S_INDEPENDENTE"}
DEVELOPMENT_PHASES = {"DEV-S", "DEV_S", "DEV_S_AJUSTE"}
ALLOWED_PHASES = CONFIRMATORY_PHASES | DEVELOPMENT_PHASES
ALLOWED_MODALITIES = {"REP-S-FIELD-PILOT", "REP-S-OP"}
ALLOWED_ACQUISITION_STATUSES = {
    "PLANEJADO",
    "COLETADO",
    "CANCELADO",
    "EXCLUÍDO_COM_JUSTIFICATIVA",
}
ALLOWED_GT_STATUSES = {
    "revisar": "REVISAR",
    "valido": "VÁLIDO",
    "excluido_com_justificativa": "EXCLUÍDO_COM_JUSTIFICATIVA",
}
ALLOWED_CUSTODY_STATUSES = {
    "aberto": "ABERTO",
    "reservado": "RESERVADO",
    "lacrado": "LACRADO",
    "aberto_apos_t2": "ABERTO_APÓS_T2",
}
PRE_FREEZE_CUSTODY_STATUSES = {"RESERVADO", "LACRADO"}

# Valores deliberadamente fechados: a modalidade determina quem produziu a
# entrada candidata. Texto livre impediria auditar a independência da fonte.
FIELD_PILOT_DATA_ORIGINS = {
    "gerador_congelado",
    "gerador_pre_especificado",
    "simulacao_congelada",
}
OPERATIONAL_DATA_ORIGINS = {
    "sistema_aerotransportado",
    "sistema_aerotransportado_operacional",
    "fonte_operacional_aerotransportada",
}
SCIENTIFIC_OUTPUT_SUFFIXES = {".csv", ".json", ".geojson"}
EVIDENCE_LOG_SUFFIXES = {".log", ".txt"}
SUPPORTED_MODEL_OUTPUT_SUFFIXES = SCIENTIFIC_OUTPUT_SUFFIXES | EVIDENCE_LOG_SUFFIXES

# Colunas de interface calculadas pelo template. Elas ajudam o preenchimento,
# mas não pertencem ao conjunto científico nem podem ser exportadas ao motor.
WORKBOOK_HELPER_COLUMNS = {"row_status"}


class RepSPreparationError(ValueError):
    """Erro controlado de esquema, conteúdo ou congelamento REP-S."""


class WorkbookSchemaError(RepSPreparationError):
    """O workbook não contém as abas/colunas exigidas ou viola o firewall."""


class WorkbookValueError(RepSPreparationError):
    """Uma linha contém valor ausente, inconsistente ou fora de domínio."""


class FreezeStateError(RepSPreparationError):
    """Uma transição de congelamento é inválida ou não verificável."""


def normalized_token(value: Any) -> str:
    """Converte um rótulo em token estável ``snake_case`` sem acentos."""

    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def canonical_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise WorkbookValueError("Valor numérico não finito encontrado.")
        return format(value, ".15g")
    return str(value).strip()


def _canonical_enum(
    value: Any,
    allowed: Mapping[str, str],
    *,
    sheet: str,
    row_number: int,
    field: str,
) -> str:
    """Valida um enum sem depender de acentos ou caixa na entrada."""

    if is_blank(value):
        raise WorkbookValueError(
            f"{sheet}, linha {row_number}: campo obrigatório vazio: {field}."
        )
    token = normalized_token(value)
    if token not in allowed:
        raise WorkbookValueError(
            f"{sheet}, linha {row_number}: {field} fora do domínio permitido."
        )
    return allowed[token]


def _require_sim(value: Any, *, sheet: str, row_number: int, field: str) -> str:
    if normalized_token(value) != "sim":
        raise WorkbookValueError(
            f"{sheet}, linha {row_number}: {field} deve ser SIM antes de consultar resultados."
        )
    return "SIM"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_timestamp(value: str | None = None) -> str:
    """Retorna timestamp real ou valida um timestamp injetado para auditoria/testes."""

    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RepSPreparationError(
                "--timestamp deve estar em ISO 8601, por exemplo 2026-10-14T12:00:00Z."
            ) from exc
        if parsed.tzinfo is None:
            raise RepSPreparationError("--timestamp deve incluir fuso horário.")
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_cell_value(value: Any, *, sheet: str, row_number: int, field: str) -> Any:
    """Rejeita fórmulas e valores textuais com fórmulas em campos de dados."""

    if isinstance(value, str) and value.startswith("="):
        raise WorkbookValueError(
            f"{sheet}, linha {row_number}, campo {field}: fórmulas não são aceitas "
            "nos dados congeláveis; substitua pelo valor literal."
        )
    return value


def _read_sheet_rows(
    workbook_path: Path,
    sheet_name: str,
    *,
    header_markers: Sequence[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Lê uma aba e localiza sua linha de cabeçalho por marcadores.

    O kit humano usa três linhas iniciais para título e instruções; por isso o
    leitor não presume que o cabeçalho esteja na primeira linha. A busca fica
    limitada às 50 primeiras linhas para que uma tabela mal estruturada falhe
    explicitamente, em vez de selecionar por engano conteúdo textual posterior.
    """

    workbook = load_workbook(workbook_path, read_only=True, data_only=False)
    try:
        if sheet_name not in workbook.sheetnames:
            raise WorkbookSchemaError(f"Aba obrigatória ausente: {sheet_name}.")
        sheet = workbook[sheet_name]
        iterator = sheet.iter_rows(values_only=False)
        header_cells = None
        header_row_number = None
        required_markers = set(header_markers)
        for candidate_row_number, candidate_cells in enumerate(iterator, start=1):
            tokens = {normalized_token(cell.value) for cell in candidate_cells}
            if required_markers.issubset(tokens):
                header_cells = candidate_cells
                header_row_number = candidate_row_number
                break
            if candidate_row_number >= 50:
                break
        if header_cells is None or header_row_number is None:
            raise WorkbookSchemaError(
                f"Aba {sheet_name}: não foi possível localizar o cabeçalho pelos campos "
                f"{', '.join(header_markers)} nas 50 primeiras linhas."
            )

        headers: list[str] = []
        seen: set[str] = set()
        for cell in header_cells:
            header = normalized_token(cell.value)
            if not header:
                headers.append("")
                continue
            if header in seen:
                raise WorkbookSchemaError(
                    f"Aba {sheet_name}: cabeçalho duplicado após normalização: {header}."
                )
            headers.append(header)
            seen.add(header)

        while headers and headers[-1] == "":
            headers.pop()
        if not headers:
            raise WorkbookSchemaError(f"Aba {sheet_name} não possui cabeçalhos utilizáveis.")
        if "" in headers:
            raise WorkbookSchemaError(
                f"Aba {sheet_name}: há coluna sem cabeçalho entre colunas preenchidas."
            )

        kept_indexes = [
            index for index, header in enumerate(headers)
            if header not in WORKBOOK_HELPER_COLUMNS
        ]
        headers = [headers[index] for index in kept_indexes]

        records: list[dict[str, Any]] = []
        for row_number, cells in enumerate(iterator, start=header_row_number + 1):
            source_cells = list(cells)
            values = [
                source_cells[index].value if index < len(source_cells) else None
                for index in kept_indexes
            ]
            if all(is_blank(value) for value in values):
                continue
            record: dict[str, Any] = {}
            for header, value in zip(headers, values):
                record[header] = _safe_cell_value(
                    value, sheet=sheet_name, row_number=row_number, field=header
                )
            record["__row_number__"] = row_number
            records.append(record)
        return headers, records
    finally:
        workbook.close()


def _require_columns(headers: Sequence[str], required: Sequence[str], sheet: str) -> None:
    missing = [column for column in required if column not in headers]
    if missing:
        raise WorkbookSchemaError(
            f"Aba {sheet}: colunas obrigatórias ausentes: {', '.join(missing)}."
        )


def _reject_forbidden_columns(
    headers: Iterable[str],
    *,
    exact: set[str],
    fragments: Sequence[str],
    sheet: str,
) -> None:
    offending = sorted(
        header
        for header in headers
        if header in exact or any(fragment in header for fragment in fragments)
    )
    if offending:
        raise WorkbookSchemaError(
            f"Aba {sheet}: colunas proibidas pelo firewall: {', '.join(offending)}."
        )


def _required_text(record: Mapping[str, Any], field: str, *, sheet: str) -> str:
    row = int(record["__row_number__"])
    value = record.get(field)
    if is_blank(value):
        raise WorkbookValueError(f"{sheet}, linha {row}: campo obrigatório vazio: {field}.")
    text = canonical_text(value)
    if text.startswith(("=", "+", "@")):
        raise WorkbookValueError(
            f"{sheet}, linha {row}, campo {field}: prefixo textual inseguro para CSV."
        )
    return text


def _as_float(
    record: Mapping[str, Any],
    field: str,
    *,
    sheet: str,
    required: bool = True,
) -> float | None:
    row = int(record["__row_number__"])
    value = record.get(field)
    if is_blank(value):
        if required:
            raise WorkbookValueError(f"{sheet}, linha {row}: campo obrigatório vazio: {field}.")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WorkbookValueError(
            f"{sheet}, linha {row}: {field} deve ser numérico."
        ) from exc
    if not math.isfinite(number):
        raise WorkbookValueError(
            f"{sheet}, linha {row}: {field} deve ser um número finito."
        )
    return number


def _validate_coordinate(
    record: Mapping[str, Any],
    field: str,
    *,
    minimum: float,
    maximum: float,
    sheet: str,
) -> None:
    number = _as_float(record, field, sheet=sheet)
    assert number is not None
    if not minimum <= number <= maximum:
        # Não ecoar o valor, especialmente para preservar o GT em relatórios.
        raise WorkbookValueError(
            f"{sheet}, linha {record['__row_number__']}: {field} fora do domínio permitido."
        )


def normalize_phase(value: Any, *, sheet: str, row_number: int) -> str:
    phase = canonical_text(value).strip().upper().replace(" ", "_")
    if phase not in ALLOWED_PHASES:
        raise WorkbookValueError(
            f"{sheet}, linha {row_number}: execution_phase inválida. "
            "Use DEV-S ou REP-S (as variantes documentadas também são aceitas)."
        )
    if phase in CONFIRMATORY_PHASES:
        return "REP-S"
    return "DEV-S"


def validate_blind_rows(
    headers: Sequence[str], records: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    _require_columns(headers, BLIND_REQUIRED_COLUMNS, BLIND_SHEET)
    _reject_forbidden_columns(
        headers,
        exact=BLIND_FORBIDDEN_EXACT,
        fragments=BLIND_FORBIDDEN_FRAGMENTS,
        sheet=BLIND_SHEET,
    )
    if not records:
        raise WorkbookValueError(f"Aba {BLIND_SHEET}: nenhuma linha de dados preenchida.")

    candidate_keys: set[tuple[str, str]] = set()
    scenario_to_site: dict[str, str] = {}
    phases_by_site: dict[str, set[str]] = defaultdict(set)
    output: list[dict[str, Any]] = []

    for source in records:
        row = int(source["__row_number__"])
        scenario_id = _required_text(source, "scenario_id", sheet=BLIND_SHEET)
        candidate_id = _required_text(source, "candidate_id", sheet=BLIND_SHEET)
        site_id = _required_text(source, "site_id", sheet=BLIND_SHEET)
        phase = normalize_phase(source.get("execution_phase"), sheet=BLIND_SHEET, row_number=row)

        key = (scenario_id, candidate_id)
        if key in candidate_keys:
            raise WorkbookValueError(
                f"{BLIND_SHEET}, linha {row}: chave duplicada scenario_id + candidate_id."
            )
        candidate_keys.add(key)

        prior_site = scenario_to_site.setdefault(scenario_id, site_id)
        if prior_site != site_id:
            raise WorkbookValueError(
                f"{BLIND_SHEET}, linha {row}: um scenario_id não pode pertencer a mais de um site_id."
            )
        phases_by_site[site_id].add(phase)

        _validate_coordinate(
            source, "estimated_lat", minimum=-90.0, maximum=90.0, sheet=BLIND_SHEET
        )
        _validate_coordinate(
            source, "estimated_lon", minimum=-180.0, maximum=180.0, sheet=BLIND_SHEET
        )
        radius = _as_float(source, "base_radius_m", sheet=BLIND_SHEET)
        quality = _as_float(source, "detection_quality", sheet=BLIND_SHEET)
        assert radius is not None and quality is not None
        if radius <= 0:
            raise WorkbookValueError(
                f"{BLIND_SHEET}, linha {row}: base_radius_m deve ser maior que zero."
            )
        if not 0 <= quality <= 1:
            raise WorkbookValueError(
                f"{BLIND_SHEET}, linha {row}: detection_quality deve estar entre 0 e 1."
            )

        semantics = _required_text(source, "r0_semantics", sheet=BLIND_SHEET).lower()
        if semantics not in R0_SEMANTICS:
            raise WorkbookValueError(
                f"{BLIND_SHEET}, linha {row}: r0_semantics inválida."
            )
        if phase == "REP-S" and semantics == "diagnostic_legacy":
            raise WorkbookValueError(
                f"{BLIND_SHEET}, linha {row}: diagnostic_legacy não é elegível para REP-S."
            )
        if phase == "REP-S":
            _required_text(source, "data_origin", sheet=BLIND_SHEET)
            if semantics != "source_adjusted":
                _required_text(source, "r0_provenance", sheet=BLIND_SHEET)
            if semantics == "nominal_base" and not math.isclose(
                radius, 2000.0, rel_tol=0.0, abs_tol=1e-9
            ):
                raise WorkbookValueError(
                    f"{BLIND_SHEET}, linha {row}: nominal_base em REP-S exige "
                    "base_radius_m = 2000."
                )
        if semantics == "source_adjusted":
            missing_source_metadata = [
                field
                for field in ("factors_applied", "r0_provenance")
                if field not in headers or is_blank(source.get(field))
            ]
            if missing_source_metadata:
                raise WorkbookValueError(
                    f"{BLIND_SHEET}, linha {row}: source_adjusted exige "
                    + " e ".join(missing_source_metadata)
                    + "."
                )

        for optional_nonnegative in ("position_dispersion_m", "information_age_min"):
            if optional_nonnegative in headers:
                number = _as_float(
                    source,
                    optional_nonnegative,
                    sheet=BLIND_SHEET,
                    required=False,
                )
                if number is not None and number < 0:
                    raise WorkbookValueError(
                        f"{BLIND_SHEET}, linha {row}: {optional_nonnegative} não pode ser negativo."
                    )

        normalized = {
            header: (phase if header == "execution_phase" else canonical_text(source.get(header)))
            for header in headers
        }
        if "source_row_hash" in normalized:
            hash_payload = {
                key: value
                for key, value in normalized.items()
                if key != "source_row_hash"
            }
            normalized["source_row_hash"] = hashlib.sha256(
                json.dumps(
                    hash_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        output.append(normalized)

    split_sites = sorted(site for site, phases in phases_by_site.items() if len(phases) != 1)
    if split_sites:
        raise WorkbookValueError(
            "Partição inválida: um mesmo site_id foi distribuído entre DEV-S e REP-S. "
            f"Sites afetados: {', '.join(split_sites)}."
        )
    return output


def validate_gt_rows(
    headers: Sequence[str], records: Sequence[dict[str, Any]]
) -> list[dict[str, Any]]:
    _require_columns(headers, GT_REQUIRED_COLUMNS, GT_SHEET)
    _reject_forbidden_columns(
        headers,
        exact=GT_FORBIDDEN_EXACT,
        fragments=GT_FORBIDDEN_FRAGMENTS,
        sheet=GT_SHEET,
    )
    if not records:
        raise WorkbookValueError(f"Aba {GT_SHEET}: nenhuma linha de dados preenchida.")

    keys: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for source in records:
        row = int(source["__row_number__"])
        site_id = _required_text(source, "site_id", sheet=GT_SHEET)
        scenario_id = _required_text(source, "scenario_id", sheet=GT_SHEET)
        key = (site_id, scenario_id)
        if key in keys:
            raise WorkbookValueError(
                f"{GT_SHEET}, linha {row}: chave duplicada site_id + scenario_id."
            )
        keys.add(key)
        _validate_coordinate(
            source, "ground_truth_lat", minimum=-90.0, maximum=90.0, sheet=GT_SHEET
        )
        _validate_coordinate(
            source, "ground_truth_lon", minimum=-180.0, maximum=180.0, sheet=GT_SHEET
        )
        _required_text(source, "collection_method", sheet=GT_SHEET)
        ground_truth_status = _canonical_enum(
            source.get("ground_truth_status"),
            ALLOWED_GT_STATUSES,
            sheet=GT_SHEET,
            row_number=row,
            field="ground_truth_status",
        )
        custody_status = _canonical_enum(
            source.get("custody_status"),
            ALLOWED_CUSTODY_STATUSES,
            sheet=GT_SHEET,
            row_number=row,
            field="custody_status",
        )
        if custody_status not in PRE_FREEZE_CUSTODY_STATUSES:
            raise WorkbookValueError(
                f"{GT_SHEET}, linha {row}: custody_status deve ser RESERVADO ou "
                "LACRADO durante a preparação."
            )
        if "horizontal_precision_m" in headers:
            precision = _as_float(
                source, "horizontal_precision_m", sheet=GT_SHEET, required=False
            )
            if precision is not None and precision < 0:
                raise WorkbookValueError(
                    f"{GT_SHEET}, linha {row}: horizontal_precision_m não pode ser negativa."
                )
        normalized = {header: canonical_text(source.get(header)) for header in headers}
        normalized["ground_truth_status"] = ground_truth_status
        normalized["custody_status"] = custody_status
        output.append(normalized)
    return output


def validate_plan_rows(
    headers: Sequence[str],
    records: Sequence[dict[str, Any]],
) -> dict[str, dict[str, str]]:
    """Valida o plano prospectivo e retorna metadados congelados por site."""

    if not headers:
        return {}
    if "assigned_phase" in headers:
        phase_field = "assigned_phase"
    elif "execution_phase" in headers:
        phase_field = "execution_phase"
    else:
        phase_field = "phase"
    _require_columns(
        headers,
        (
            "site_id",
            phase_field,
            "validation_modality",
            "partition_assigned_before_outcomes",
            "source_is_new_for_rep_s",
            "acquisition_status",
        ),
        PLAN_SHEET,
    )
    assignments: dict[str, dict[str, str]] = {}
    for source in records:
        row = int(source["__row_number__"])
        site_id = _required_text(source, "site_id", sheet=PLAN_SHEET)
        phase = normalize_phase(source.get(phase_field), sheet=PLAN_SHEET, row_number=row)
        modality = _required_text(
            source, "validation_modality", sheet=PLAN_SHEET
        ).upper()
        if modality not in ALLOWED_MODALITIES:
            raise WorkbookValueError(
                f"{PLAN_SHEET}, linha {row}: validation_modality inválida."
            )
        partition_before_outcomes = _require_sim(
            source.get("partition_assigned_before_outcomes"),
            sheet=PLAN_SHEET,
            row_number=row,
            field="partition_assigned_before_outcomes",
        )
        source_is_new = canonical_text(source.get("source_is_new_for_rep_s")).upper()
        if source_is_new not in {"SIM", "NÃO", "NAO"}:
            raise WorkbookValueError(
                f"{PLAN_SHEET}, linha {row}: source_is_new_for_rep_s deve ser SIM ou NÃO."
            )
        if phase == "REP-S" and normalized_token(source_is_new) != "sim":
            raise WorkbookValueError(
                f"{PLAN_SHEET}, linha {row}: source_is_new_for_rep_s deve ser SIM para REP-S."
            )
        source_is_new = "SIM" if normalized_token(source_is_new) == "sim" else "NÃO"
        acquisition_status = _required_text(
            source, "acquisition_status", sheet=PLAN_SHEET
        ).upper()
        if acquisition_status not in ALLOWED_ACQUISITION_STATUSES:
            raise WorkbookValueError(
                f"{PLAN_SHEET}, linha {row}: acquisition_status fora do domínio permitido."
            )
        # Uma linha só chega ao pacote de execução quando há entrada cega e GT
        # correspondentes; logo estados apenas prospectivos/excluídos não são
        # coerentes neste estágio.
        if acquisition_status != "COLETADO":
            raise WorkbookValueError(
                f"{PLAN_SHEET}, linha {row}: acquisition_status deve ser COLETADO "
                "para um site incluído no pacote de execução."
            )
        if site_id in assignments:
            raise WorkbookValueError(
                f"{PLAN_SHEET}, linha {row}: site_id duplicado no plano amostral."
            )
        assignments[site_id] = {
            "phase": phase,
            "validation_modality": modality,
            "partition_assigned_before_outcomes": partition_before_outcomes,
            "source_is_new_for_rep_s": source_is_new,
            "acquisition_status": acquisition_status,
        }
    return assignments


def _validate_relations(
    blind_rows: Sequence[Mapping[str, str]],
    gt_rows: Sequence[Mapping[str, str]],
    planned_sites: Mapping[str, Mapping[str, str]],
) -> list[dict[str, str]]:
    blind_keys = {(row["site_id"], row["scenario_id"]) for row in blind_rows}
    gt_keys = {(row["site_id"], row["scenario_id"]) for row in gt_rows}
    missing_gt = blind_keys - gt_keys
    orphan_gt = gt_keys - blind_keys
    if missing_gt:
        raise WorkbookValueError(
            "Há cenários da entrada cega sem registro correspondente no ground truth reservado."
        )
    if orphan_gt:
        raise WorkbookValueError(
            "Há registros de ground truth reservado sem cenário correspondente na entrada cega."
        )

    phase_by_site: dict[str, str] = {}
    for row in blind_rows:
        site_id = row["site_id"]
        phase = row["execution_phase"]
        prior = phase_by_site.setdefault(site_id, phase)
        if prior != phase:
            raise WorkbookValueError("Partição por site inconsistente na entrada cega.")

    if planned_sites:
        missing_in_plan = sorted(set(phase_by_site) - set(planned_sites))
        extra_in_plan = sorted(set(planned_sites) - set(phase_by_site))
        mismatch = sorted(
            site
            for site, phase in phase_by_site.items()
            if planned_sites.get(site, {}).get("phase") not in (None, phase)
        )
        if missing_in_plan:
            raise WorkbookValueError(
                "Sites da entrada cega ausentes do PLANO_SITES: " + ", ".join(missing_in_plan)
            )
        if extra_in_plan:
            raise WorkbookValueError(
                "Sites planejados sem dados na entrada cega: " + ", ".join(extra_in_plan)
            )
        if mismatch:
            raise WorkbookValueError(
                "A fase congelada no PLANO_SITES diverge da entrada cega: " + ", ".join(mismatch)
            )

        for row in blind_rows:
            site_id = row["site_id"]
            plan = planned_sites[site_id]
            modality = plan["validation_modality"]
            data_origin = normalized_token(row.get("data_origin"))
            if modality == "REP-S-FIELD-PILOT":
                accepted = FIELD_PILOT_DATA_ORIGINS
                expected = "GERADOR_CONGELADO/GERADOR_PRE_ESPECIFICADO/SIMULACAO_CONGELADA"
            else:
                accepted = OPERATIONAL_DATA_ORIGINS
                expected = "SISTEMA_AEROTRANSPORTADO (ou variante operacional documentada)"
            if data_origin not in accepted:
                raise WorkbookValueError(
                    f"{BLIND_SHEET}: data_origin incompatível com {modality} no site "
                    f"{site_id}; use {expected}."
                )

    scenarios_by_site: dict[str, set[str]] = defaultdict(set)
    candidate_count_by_site: Counter[str] = Counter()
    for row in blind_rows:
        scenarios_by_site[row["site_id"]].add(row["scenario_id"])
        candidate_count_by_site[row["site_id"]] += 1
    return [
        {
            "site_id": site,
            "execution_phase": phase_by_site[site],
            "scenario_count": str(len(scenarios_by_site[site])),
            "candidate_count": str(candidate_count_by_site[site]),
        }
        for site in sorted(phase_by_site)
    ]


def _write_csv(path: Path, headers: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _ensure_output_paths_available(paths: Sequence[Path], overwrite: bool) -> None:
    existing = [str(path) for path in paths if path.exists()]
    if existing and not overwrite:
        raise FreezeStateError(
            "Arquivos de saída já existem; use --overwrite somente se a substituição foi deliberada: "
            + ", ".join(existing)
        )


def _workbook_sheetnames(workbook_path: Path) -> list[str]:
    workbook = load_workbook(workbook_path, read_only=True, data_only=False)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def prepare_package(
    workbook_path: Path,
    output_dir: Path,
    *,
    overwrite: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Valida o workbook e cria arquivos fisicamente separados por finalidade."""

    workbook_path = workbook_path.resolve()
    output_dir = output_dir.resolve()
    if not workbook_path.is_file():
        raise WorkbookSchemaError(f"Workbook não encontrado: {workbook_path}.")

    sheetnames = _workbook_sheetnames(workbook_path)
    blind_headers, blind_source = _read_sheet_rows(
        workbook_path,
        BLIND_SHEET,
        header_markers=("scenario_id", "candidate_id", "site_id"),
    )
    gt_headers, gt_source = _read_sheet_rows(
        workbook_path,
        GT_SHEET,
        header_markers=("site_id", "scenario_id", "ground_truth_lat", "ground_truth_lon"),
    )
    if PLAN_SHEET in sheetnames:
        plan_headers, plan_source = _read_sheet_rows(
            workbook_path,
            PLAN_SHEET,
            header_markers=("site_id",),
        )
        if not plan_source:
            raise WorkbookValueError(
                f"Aba {PLAN_SHEET}: nenhuma linha de planejamento preenchida."
            )
        planned_sites = validate_plan_rows(plan_headers, plan_source)
    else:
        planned_sites = {}

    blind_rows = validate_blind_rows(blind_headers, blind_source)
    gt_rows = validate_gt_rows(gt_headers, gt_source)
    if any(row["execution_phase"] == "REP-S" for row in blind_rows) and not planned_sites:
        raise WorkbookValueError(
            f"A aba {PLAN_SHEET} é obrigatória quando o pacote contém REP-S."
        )
    partition_rows = _validate_relations(blind_rows, gt_rows, planned_sites)

    public_dir = output_dir / "public"
    locked_dir = output_dir / "locked"
    blind_csv = public_dir / "rep_s_input_blind.csv"
    partition_csv = public_dir / "rep_s_partition.csv"
    gt_csv = locked_dir / "rep_s_ground_truth_locked.csv"
    public_manifest_path = public_dir / "manifesto_entrada_cega.json"
    locked_manifest_path = locked_dir / "manifesto_ground_truth_locked.json"
    root_manifest_path = output_dir / "manifesto_preparacao_rep_s.json"
    report_path = output_dir / "relatorio_validacao_rep_s.json"

    all_outputs = (
        blind_csv,
        partition_csv,
        gt_csv,
        public_manifest_path,
        locked_manifest_path,
        root_manifest_path,
        report_path,
    )
    _ensure_output_paths_available(all_outputs, overwrite)

    _write_csv(blind_csv, blind_headers, blind_rows)
    _write_csv(partition_csv, tuple(partition_rows[0].keys()), partition_rows)
    _write_csv(gt_csv, gt_headers, gt_rows)

    created_at = utc_timestamp(timestamp)
    blind_hash = sha256_file(blind_csv)
    partition_hash = sha256_file(partition_csv)
    gt_hash = sha256_file(gt_csv)
    workbook_hash = sha256_file(workbook_path)
    phase_counts = Counter(row["execution_phase"] for row in partition_rows)

    gates = [
        {"gate_id": "G01", "status": "PASS", "evidence": "plano prospectivo e partição por site congelados antes dos resultados"},
        {"gate_id": "G02", "status": "PASS", "evidence": "entrada cega e ground truth exportados para arquivos fisicamente separados"},
        {"gate_id": "G03", "status": "PASS", "evidence": "IDs e chaves únicos; candidatos do mesmo site na mesma fase"},
        {"gate_id": "G04", "status": "PASS", "evidence": "entrada cega sem campos de ground truth"},
        {"gate_id": "G05", "status": "PASS", "evidence": "semântica e proveniência de r0 validadas"},
        {"gate_id": "G06", "status": "PENDENTE", "evidence": "conferir hashes de configuração/motor e aprovar a suíte de testes"},
        {"gate_id": "G07", "status": "PENDENTE", "evidence": "comprovar duas execuções determinísticas e saídas válidas"},
        {"gate_id": "G08", "status": "PENDENTE", "evidence": "congelar todas as saídas antes de abrir o ground truth"},
        {"gate_id": "G09", "status": "PENDENTE", "evidence": "registrar abertura do ground truth somente após G08"},
        {"gate_id": "G10", "status": "PENDENTE", "evidence": "avaliação sem ajuste retrospectivo"},
    ]

    public_manifest = {
        "protocol_id": PROTOCOL_ID,
        "script_version": SCRIPT_VERSION,
        "state": "ENTRADA_CEGA_CONGELADA",
        "created_at_utc": created_at,
        "input_workbook_sha256": workbook_hash,
        "blind_input": {
            "relative_path": "public/rep_s_input_blind.csv",
            "sha256": blind_hash,
            "row_count": len(blind_rows),
            "site_count": len(partition_rows),
            "scenario_count": len({row["scenario_id"] for row in blind_rows}),
        },
        "partition": {
            "relative_path": "public/rep_s_partition.csv",
            "sha256": partition_hash,
            "phase_site_counts": dict(sorted(phase_counts.items())),
        },
        "ground_truth": {
            "separate_locked_file_frozen": True,
            "sha256_commitment": gt_hash,
            "coordinates_disclosed": False,
            "opened_by_model": False,
        },
        "gates": gates,
    }
    locked_manifest = {
        "protocol_id": PROTOCOL_ID,
        "script_version": SCRIPT_VERSION,
        "state": "GROUND_TRUTH_FECHADO",
        "created_at_utc": created_at,
        "ground_truth_file": {
            "relative_path": "locked/rep_s_ground_truth_locked.csv",
            "sha256": gt_hash,
            "row_count": len(gt_rows),
            "site_count": len({row["site_id"] for row in gt_rows}),
            "coordinates_in_manifest": False,
        },
        "release_condition": "SAIDA_DO_MODELO_CONGELADA",
    }
    root_manifest = {
        "protocol_id": PROTOCOL_ID,
        "script_version": SCRIPT_VERSION,
        "state": "ENTRADA_CEGA_CONGELADA",
        "created_at_utc": created_at,
        "input_workbook": {"name": workbook_path.name, "sha256": workbook_hash},
        "artifacts": {
            "blind_input": {"path": "public/rep_s_input_blind.csv", "sha256": blind_hash},
            "partition": {"path": "public/rep_s_partition.csv", "sha256": partition_hash},
            "ground_truth_locked": {
                "path": "locked/rep_s_ground_truth_locked.csv",
                "sha256": gt_hash,
                "coordinates_disclosed": False,
            },
            "public_manifest": {"path": "public/manifesto_entrada_cega.json"},
            "locked_manifest": {"path": "locked/manifesto_ground_truth_locked.json"},
        },
        "counts": {
            "blind_rows": len(blind_rows),
            "ground_truth_rows": len(gt_rows),
            "sites": len(partition_rows),
            "scenarios": len({row["scenario_id"] for row in blind_rows}),
        },
        "firewall": {
            "public_and_locked_directories_separated": True,
            "prospective_plan_and_modality_validated": True,
            "rep_s_source_newness_validated": True,
            "ground_truth_fields_rejected_from_blind_input": True,
            "candidate_outputs_rejected_from_ground_truth": True,
            "ground_truth_and_custody_enums_validated": True,
            "manifest_contains_ground_truth_coordinates": False,
            "next_required_state": "MOTOR_VERIFICADO",
        },
    }
    report = {
        "protocol_id": PROTOCOL_ID,
        "status": "VALIDADO_PARA_PREPARACAO",
        "created_at_utc": created_at,
        "checks": gates,
        "summary": {
            "blind_rows": len(blind_rows),
            "ground_truth_rows": len(gt_rows),
            "sites": len(partition_rows),
            "phase_site_counts": dict(sorted(phase_counts.items())),
        },
        "ground_truth_values_in_report": False,
        "next_action": "Entregar somente a pasta public ao motor; congelar a saída antes de abrir locked.",
    }

    _write_json(public_manifest_path, public_manifest)
    _write_json(locked_manifest_path, locked_manifest)
    _write_json(root_manifest_path, root_manifest)
    _write_json(report_path, report)
    return root_manifest


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeStateError(f"Manifesto inválido ou ilegível: {path}.") from exc
    if not isinstance(payload, dict):
        raise FreezeStateError("O manifesto de preparação deve conter um objeto JSON.")
    return payload


def _validate_output_fields(fields: Iterable[Any]) -> None:
    """Rejeita campos de GT; ``ground_truth_used`` é tratado pelo valor."""

    normalized = [normalized_token(field) for field in fields]
    normalized = [field for field in normalized if field != "ground_truth_used"]
    _reject_forbidden_columns(
        normalized,
        exact=BLIND_FORBIDDEN_EXACT,
        fragments=BLIND_FORBIDDEN_FRAGMENTS,
        sheet="SAIDA_MODELO",
    )


def _inspect_csv_output(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                raw_headers = next(reader)
            except StopIteration as exc:
                raise FreezeStateError("Há arquivo CSV vazio na saída do modelo.") from exc
            if not raw_headers or all(is_blank(value) for value in raw_headers):
                raise FreezeStateError("Há arquivo CSV sem cabeçalho na saída do modelo.")
            _validate_output_fields(raw_headers)
            normalized_headers = [normalized_token(value) for value in raw_headers]
            gt_indexes = [
                index for index, field in enumerate(normalized_headers)
                if field == "ground_truth_used"
            ]
            row_count = 0
            for row in reader:
                if not any(not is_blank(value) for value in row):
                    continue
                row_count += 1
                for index in gt_indexes:
                    value = row[index] if index < len(row) else None
                    if not isinstance(value, str) or value.strip().lower() != "false":
                        raise FreezeStateError(
                            "ground_truth_used em CSV deve conter somente o booleano false."
                        )
    except UnicodeDecodeError as exc:
        raise FreezeStateError("Há arquivo CSV que não está codificado como texto UTF-8.") from exc
    if row_count == 0:
        raise FreezeStateError("Há arquivo CSV sem registros na saída do modelo.")
    return row_count


def _validate_json_firewall(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            token = normalized_token(key)
            if token == "ground_truth_used":
                if nested is not False or type(nested) is not bool:
                    raise FreezeStateError(
                        "ground_truth_used em JSON/GeoJSON deve ser o booleano false."
                    )
                continue
            _validate_output_fields((key,))
            _validate_json_firewall(nested)
    elif isinstance(value, list):
        for nested in value:
            _validate_json_firewall(nested)


def _inspect_json_output(path: Path) -> int:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FreezeStateError("Há arquivo JSON que não está codificado como texto UTF-8.") from exc
    if not raw.strip():
        raise FreezeStateError("Há arquivo JSON vazio na saída do modelo.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FreezeStateError("Há arquivo JSON/GeoJSON inválido na saída do modelo.") from exc
    if payload is None or payload == {} or payload == [] or payload == "":
        raise FreezeStateError("Há estrutura JSON vazia na saída do modelo.")
    _validate_json_firewall(payload)

    if isinstance(payload, Mapping):
        object_type = canonical_text(payload.get("type")).lower()
        if object_type == "featurecollection":
            features = payload.get("features")
            if not isinstance(features, list) or not features:
                raise FreezeStateError("Há GeoJSON FeatureCollection sem feições.")
            return len(features)
        if object_type == "feature":
            geometry = payload.get("geometry")
            if not isinstance(geometry, Mapping) or not geometry:
                raise FreezeStateError("Há feição GeoJSON sem geometria verificável.")
            return 1
        return len(payload)
    if isinstance(payload, list):
        return len(payload)
    return 1


def _inspect_text_log(path: Path) -> int:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FreezeStateError("Há log que não está codificado como texto UTF-8.") from exc
    if not raw.strip():
        raise FreezeStateError("Há log vazio entre as evidências de execução.")
    identifiers = re.findall(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_]*", raw)
    _validate_output_fields(identifiers)
    for match in re.finditer(
        r"\bground_truth_used\b\s*[:=]\s*([^\s,;]+)", raw, re.IGNORECASE
    ):
        value = match.group(1).strip().strip('"\'').lower()
        if value != "false":
            raise FreezeStateError(
                "ground_truth_used em log deve registrar somente false."
            )
    return sum(1 for line in raw.splitlines() if line.strip())


def _inspect_output_file(path: Path) -> tuple[int, str]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_MODEL_OUTPUT_SUFFIXES:
        raise FreezeStateError(
            "A saída contém formato não permitido; use CSV, JSON, GeoJSON ou logs de texto."
        )
    if not path.is_file() or path.stat().st_size == 0:
        raise FreezeStateError("Há artefato vazio ou não regular na saída do modelo.")
    if suffix == ".csv":
        return _inspect_csv_output(path), "CSV"
    if suffix in {".json", ".geojson"}:
        return _inspect_json_output(path), "GEOJSON" if suffix == ".geojson" else "JSON"
    return _inspect_text_log(path), "LOG"


def _collect_output_files(path: Path) -> list[Path]:
    if path.is_file():
        files = [path]
    elif path.is_dir():
        descendants = sorted(path.rglob("*"))
        if any(candidate.is_symlink() for candidate in descendants):
            raise FreezeStateError(
                "A saída não pode conter links simbólicos; congele apenas artefatos regulares."
            )
        candidates = [candidate for candidate in descendants if candidate.is_file()]
        if not candidates:
            raise FreezeStateError("Diretório de saída do modelo está vazio.")
        unsupported = [
            candidate for candidate in candidates
            if candidate.suffix.lower() not in SUPPORTED_MODEL_OUTPUT_SUFFIXES
        ]
        if unsupported:
            raise FreezeStateError(
                "A saída contém formato não permitido; use CSV, JSON, GeoJSON ou logs de texto."
            )
        files = candidates
    else:
        raise FreezeStateError("Saída do modelo não encontrada ou não é arquivo/diretório regular.")
    return files


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _validate_engine_manifest(
    path: Path,
    *,
    expected_input_sha256: str,
    expected_config_sha256: str,
    expected_engine_sha256: str,
) -> dict[str, Any]:
    """Valida o manifesto efetivamente emitido pelo motor EXT-ESP-BUF."""

    _inspect_json_output(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - já inspecionado
        raise FreezeStateError("Manifesto do motor inválido ou ilegível.") from exc
    if not isinstance(payload, Mapping):
        raise FreezeStateError("Manifesto do motor deve conter um objeto JSON.")
    if payload.get("ground_truth_used") is not False or type(payload.get("ground_truth_used")) is not bool:
        raise FreezeStateError(
            "O manifesto do motor deve declarar ground_truth_used como booleano false."
        )
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise FreezeStateError("Manifesto do motor não contém a lista files[].")

    by_role: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in files:
        if not isinstance(item, Mapping):
            raise FreezeStateError("Manifesto do motor contém item files[] inválido.")
        role = normalized_token(item.get("role"))
        if role not in {"input", "config", "engine", "output"}:
            raise FreezeStateError("Manifesto do motor contém role não reconhecida.")
        if not _valid_sha256(item.get("sha256")):
            raise FreezeStateError("Manifesto do motor contém SHA-256 inválido.")
        by_role[role].append(item)

    for role in ("input", "config", "engine"):
        if len(by_role[role]) != 1:
            raise FreezeStateError(
                f"Manifesto do motor deve conter exatamente um item role={role}."
            )
    if not by_role["output"]:
        raise FreezeStateError("Manifesto do motor não declara resultados role=output.")
    expected = {
        "input": expected_input_sha256,
        "config": expected_config_sha256,
        "engine": expected_engine_sha256,
    }
    for role, expected_hash in expected.items():
        if by_role[role][0].get("sha256") != expected_hash:
            raise FreezeStateError(
                f"Hash role={role} do manifesto do motor diverge do artefato congelado."
            )
    return {
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "output_hashes": [str(item["sha256"]) for item in by_role["output"]],
        "ground_truth_used": False,
    }


def _bundle_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    if len(entries) == 1:
        return str(entries[0]["sha256"])
    return hashlib.sha256(
        json.dumps(list(entries), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _inspect_run_bundle(
    output_path: Path,
    engine_manifest_path: Path,
    *,
    expected_input_sha256: str,
    expected_config_sha256: str,
    expected_engine_sha256: str,
) -> dict[str, Any]:
    """Separa resultados científicos de manifesto/logs e congela ambos."""

    files = _collect_output_files(output_path)
    manifest_path = engine_manifest_path.resolve()
    if not manifest_path.is_file() or manifest_path.stat().st_size == 0:
        raise FreezeStateError("Manifesto do motor ausente ou vazio.")
    manifest = _validate_engine_manifest(
        manifest_path,
        expected_input_sha256=expected_input_sha256,
        expected_config_sha256=expected_config_sha256,
        expected_engine_sha256=expected_engine_sha256,
    )
    expected_outputs = Counter(manifest["output_hashes"])

    scientific_entries: list[dict[str, Any]] = []
    evidence_entries: list[dict[str, Any]] = [
        {
            "kind": "engine_manifest",
            "sha256": manifest["sha256"],
            "size_bytes": manifest["size_bytes"],
        }
    ]
    total_records = 0
    manifest_in_bundle = False
    for artifact in files:
        if artifact.resolve() == manifest_path:
            manifest_in_bundle = True
            continue
        record_count, format_name = _inspect_output_file(artifact)
        artifact_hash = sha256_file(artifact)
        entry = {
            "format": format_name,
            "sha256": artifact_hash,
            "size_bytes": artifact.stat().st_size,
        }
        if expected_outputs[artifact_hash] > 0:
            expected_outputs[artifact_hash] -= 1
            scientific_entries.append(entry)
            total_records += record_count
            continue
        stem = normalized_token(artifact.stem)
        if artifact.suffix.lower() in EVIDENCE_LOG_SUFFIXES or "log" in stem:
            evidence_entries.append({"kind": "execution_log", **entry})
            continue
        raise FreezeStateError(
            "A execução contém artefato científico não declarado no manifesto do motor."
        )

    if any(count for count in expected_outputs.values()):
        raise FreezeStateError(
            "Há resultado role=output no manifesto do motor sem arquivo correspondente."
        )
    if not scientific_entries:
        raise FreezeStateError("Nenhum resultado científico verificável foi encontrado.")
    scientific_entries.sort(key=lambda item: (item["format"], item["sha256"], item["size_bytes"]))
    evidence_entries.sort(key=lambda item: (item["kind"], item["sha256"], item["size_bytes"]))
    return {
        "kind": "file" if output_path.is_file() else "directory",
        "scientific_sha256": _bundle_hash(scientific_entries),
        "scientific_entries": scientific_entries,
        "file_count": len(scientific_entries),
        "record_count": total_records,
        "size_bytes": sum(int(item["size_bytes"]) for item in scientific_entries),
        "formats": sorted({str(item["format"]) for item in scientific_entries}),
        "evidence_sha256": _bundle_hash(evidence_entries),
        "evidence_entries": evidence_entries,
        "manifest_in_output_bundle": manifest_in_bundle,
    }


def _hash_nonempty_artifact(path: Path | None, *, label: str) -> dict[str, Any]:
    if path is None:
        raise FreezeStateError(f"Evidência obrigatória ausente: {label}.")
    resolved = path.resolve()
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise FreezeStateError(f"Evidência obrigatória inválida ou vazia: {label}.")
    return {
        "sha256": sha256_file(resolved),
        "size_bytes": resolved.stat().st_size,
        "_path": resolved,
    }


def _validate_test_evidence(path: Path | None) -> dict[str, Any]:
    evidence = _hash_nonempty_artifact(path, label="resultado dos testes")
    resolved = evidence["_path"]
    try:
        raw = resolved.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FreezeStateError("A evidência de testes deve ser texto UTF-8 ou JSON.") from exc

    tests_run: int | None = None
    passed = False
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, Mapping):
        status = normalized_token(payload.get("status"))
        try:
            tests_run = int(payload.get("tests_run", 0))
            failures = int(payload.get("failures", payload.get("failed", 0)))
            errors = int(payload.get("errors", 0))
        except (TypeError, ValueError) as exc:
            raise FreezeStateError("Evidência JSON de testes possui contagens inválidas.") from exc
        declared_success = payload.get("successful")
        status_passed = status in {"pass", "passed", "aprovado", "ok"}
        successful_passed = declared_success is True and type(declared_success) is bool
        passed = (status_passed or successful_passed) and tests_run > 0
        passed = passed and failures == 0 and errors == 0
    else:
        failed_marker = re.search(r"\b(?:FAILED|FAILURES?|ERRORS?)\b", raw, re.IGNORECASE)
        unittest_count = re.search(r"Ran\s+(\d+)\s+tests?", raw, re.IGNORECASE)
        pytest_count = re.search(r"(\d+)\s+passed\b", raw, re.IGNORECASE)
        success_marker = re.search(r"^OK\s*$", raw, re.IGNORECASE | re.MULTILINE)
        if unittest_count and success_marker and not failed_marker:
            tests_run = int(unittest_count.group(1))
            passed = tests_run > 0
        elif pytest_count and not failed_marker:
            tests_run = int(pytest_count.group(1))
            passed = tests_run > 0
    if not passed or tests_run is None:
        raise FreezeStateError(
            "A evidência de testes não comprova suíte executada sem falhas/erros."
        )
    return {
        "sha256": evidence["sha256"],
        "size_bytes": evidence["size_bytes"],
        "tests_run": tests_run,
        "status": "PASS",
        "_path": resolved,
    }


def _contains_path(container: Path, target: Path) -> bool:
    try:
        target.relative_to(container)
    except ValueError:
        return False
    return True


def _ensure_ground_truth_not_opened(
    preparation_manifest_path: Path,
    preparation: Mapping[str, Any],
    paths_to_read: Sequence[Path],
) -> None:
    relative = (
        preparation.get("artifacts", {})
        .get("ground_truth_locked", {})
        .get("path")
    )
    if not isinstance(relative, str) or not relative:
        raise FreezeStateError("Manifesto não identifica o artefato reservado de ground truth.")
    ground_truth_path = (preparation_manifest_path.parent / relative).resolve()
    for candidate in paths_to_read:
        resolved = candidate.resolve()
        if resolved == ground_truth_path or (resolved.is_dir() and _contains_path(resolved, ground_truth_path)):
            raise FreezeStateError(
                "Uma evidência/saída selecionada contém o arquivo reservado; operação bloqueada."
            )


def freeze_model_output(
    model_output_path: Path,
    preparation_manifest_path: Path,
    *,
    config_path: Path | None = None,
    engine_path: Path | None = None,
    test_evidence_path: Path | None = None,
    repeat_output_path: Path | None = None,
    engine_manifest_path: Path | None = None,
    repeat_engine_manifest_path: Path | None = None,
    output_manifest_path: Path | None = None,
    overwrite: bool = False,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Congela duas execuções idênticas sem ler o ground truth reservado."""

    model_output_path = model_output_path.resolve()
    preparation_manifest_path = preparation_manifest_path.resolve()
    if not model_output_path.exists():
        raise FreezeStateError("Saída do modelo não encontrada.")
    if not preparation_manifest_path.is_file():
        raise FreezeStateError("Manifesto de preparação não encontrado.")
    preparation = _read_json_object(preparation_manifest_path)
    if preparation.get("protocol_id") != PROTOCOL_ID:
        raise FreezeStateError("Manifesto pertence a outro protocolo.")
    if preparation.get("state") != "ENTRADA_CEGA_CONGELADA":
        raise FreezeStateError("O pacote não está no estado ENTRADA_CEGA_CONGELADA.")

    if repeat_output_path is None:
        raise FreezeStateError(
            "Evidência obrigatória ausente: segunda execução determinística (--repeat-output)."
        )
    repeat_output_path = repeat_output_path.resolve()
    if not repeat_output_path.exists():
        raise FreezeStateError("A segunda execução determinística não foi encontrada.")
    if model_output_path == repeat_output_path:
        raise FreezeStateError("As duas execuções devem usar conjuntos de saída distintos.")

    missing_evidence = [
        label
        for path, label in (
            (config_path, "configuração congelada"),
            (engine_path, "motor congelado"),
            (test_evidence_path, "resultado dos testes"),
            (engine_manifest_path, "manifesto da primeira execução"),
            (repeat_engine_manifest_path, "manifesto da segunda execução"),
        )
        if path is None
    ]
    if missing_evidence:
        raise FreezeStateError(
            "Evidência obrigatória ausente: " + ", ".join(missing_evidence) + "."
        )
    assert config_path is not None and engine_path is not None and test_evidence_path is not None
    assert engine_manifest_path is not None and repeat_engine_manifest_path is not None
    engine_manifest_path = engine_manifest_path.resolve()
    repeat_engine_manifest_path = repeat_engine_manifest_path.resolve()
    if engine_manifest_path == repeat_engine_manifest_path:
        raise FreezeStateError("Cada execução deve possuir manifesto próprio do motor.")
    # Este bloqueio ocorre antes de qualquer leitura/hash das evidências para
    # que nem uma seleção acidental do arquivo reservado revele seu conteúdo.
    _ensure_ground_truth_not_opened(
        preparation_manifest_path,
        preparation,
        [
            model_output_path,
            repeat_output_path,
            config_path,
            engine_path,
            test_evidence_path,
            engine_manifest_path,
            repeat_engine_manifest_path,
        ],
    )

    config_evidence = _hash_nonempty_artifact(config_path, label="configuração congelada")
    engine_evidence = _hash_nonempty_artifact(engine_path, label="motor congelado")
    test_evidence = _validate_test_evidence(test_evidence_path)

    blind_artifact = preparation.get("artifacts", {}).get("blind_input", {})
    expected_input_hash = blind_artifact.get("sha256")
    if not _valid_sha256(expected_input_hash):
        raise FreezeStateError(
            "Manifesto de preparação não contém SHA-256 válido de rep_s_input_blind.csv."
        )
    blind_relative_path = blind_artifact.get("path")
    if not isinstance(blind_relative_path, str) or not blind_relative_path:
        raise FreezeStateError(
            "Manifesto de preparação não identifica rep_s_input_blind.csv."
        )
    blind_file = (preparation_manifest_path.parent / blind_relative_path).resolve()
    if not blind_file.is_file() or sha256_file(blind_file) != expected_input_hash:
        raise FreezeStateError(
            "rep_s_input_blind.csv não confere com o compromisso do manifesto de preparação."
        )

    first_run = _inspect_run_bundle(
        model_output_path,
        engine_manifest_path,
        expected_input_sha256=expected_input_hash,
        expected_config_sha256=config_evidence["sha256"],
        expected_engine_sha256=engine_evidence["sha256"],
    )
    second_run = _inspect_run_bundle(
        repeat_output_path,
        repeat_engine_manifest_path,
        expected_input_sha256=expected_input_hash,
        expected_config_sha256=config_evidence["sha256"],
        expected_engine_sha256=engine_evidence["sha256"],
    )
    if first_run["scientific_entries"] != second_run["scientific_entries"]:
        raise FreezeStateError(
            "As duas execuções não são determinísticas: os resultados científicos divergem."
        )

    if output_manifest_path is None:
        output_manifest_path = model_output_path.with_name("manifesto_saida_modelo_congelada.json")
    output_manifest_path = output_manifest_path.resolve()
    for bundle_path in (model_output_path, repeat_output_path):
        if bundle_path.is_dir() and _contains_path(bundle_path, output_manifest_path):
            raise FreezeStateError(
                "O manifesto de congelamento deve ficar fora dos diretórios de execução."
            )
    _ensure_output_paths_available((output_manifest_path,), overwrite)

    gt_commitment = (
        preparation.get("artifacts", {})
        .get("ground_truth_locked", {})
        .get("sha256")
    )
    if not isinstance(gt_commitment, str) or not re.fullmatch(r"[0-9a-f]{64}", gt_commitment):
        raise FreezeStateError("Manifesto de preparação não contém compromisso SHA-256 válido do GT.")

    payload = {
        "protocol_id": PROTOCOL_ID,
        "script_version": SCRIPT_VERSION,
        "state": "SAIDA_DO_MODELO_CONGELADA",
        "created_at_utc": utc_timestamp(timestamp),
        "model_output": {
            "scope": "scientific_results_only",
            "sha256": first_run["scientific_sha256"],
            "kind": first_run["kind"],
            "file_count": first_run["file_count"],
            "record_count": first_run["record_count"],
            "size_bytes": first_run["size_bytes"],
            "formats": first_run["formats"],
        },
        "execution_evidence": {
            "run_1": {
                "sha256": first_run["evidence_sha256"],
                "artifact_count": len(first_run["evidence_entries"]),
                "artifacts": first_run["evidence_entries"],
            },
            "run_2": {
                "sha256": second_run["evidence_sha256"],
                "artifact_count": len(second_run["evidence_entries"]),
                "artifacts": second_run["evidence_entries"],
            },
            "equality_required": False,
            "purpose": "freeze_manifests_and_logs_without_determinism_comparison",
        },
        "preparation_manifest": {
            "name": preparation_manifest_path.name,
            "sha256": sha256_file(preparation_manifest_path),
        },
        "reproducibility_evidence": {
            "configuration": {
                "sha256": config_evidence["sha256"],
                "size_bytes": config_evidence["size_bytes"],
            },
            "engine": {
                "sha256": engine_evidence["sha256"],
                "size_bytes": engine_evidence["size_bytes"],
            },
            "tests": {
                "sha256": test_evidence["sha256"],
                "size_bytes": test_evidence["size_bytes"],
                "tests_run": test_evidence["tests_run"],
                "status": test_evidence["status"],
            },
            "deterministic_runs": {
                "comparison_scope": "scientific_results_only",
                "run_1_sha256": first_run["scientific_sha256"],
                "run_2_sha256": second_run["scientific_sha256"],
                "matching": True,
                "verified_by_content_hash": True,
            },
        },
        "gates": {"G06": "PASS", "G07": "PASS", "G08": "PASS"},
        "ground_truth": {
            "sha256_commitment": gt_commitment,
            "coordinates_disclosed": False,
            "opened_by_freeze_command": False,
            "release_authorized_after_this_state": True,
            "authorization_basis": "G06_G07_G08_PASS",
        },
        "next_required_state": "GROUND_TRUTH_ABERTO",
    }
    _write_json(output_manifest_path, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Firewall e congelamento da preparação REP-S independente."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser(
        "prepare", help="Validar workbook e separar entrada cega/ground truth."
    )
    prepare.add_argument("workbook", type=Path)
    prepare.add_argument("output_dir", type=Path)
    prepare.add_argument("--overwrite", action="store_true")
    prepare.add_argument("--timestamp", help="ISO 8601 com fuso; destinado a reprodutibilidade/auditoria.")

    freeze = subparsers.add_parser(
        "freeze-output", help="Congelar a saída do modelo antes da abertura do ground truth."
    )
    freeze.add_argument("model_output", type=Path)
    freeze.add_argument("preparation_manifest", type=Path)
    freeze.add_argument(
        "--config", type=Path, required=True,
        help="Arquivo da configuração congelada cuja hash será registrada.",
    )
    freeze.add_argument(
        "--engine", type=Path, required=True,
        help="Arquivo do motor congelado cuja hash será registrada.",
    )
    freeze.add_argument(
        "--test-evidence", type=Path, required=True,
        help="JSON/log que comprove uma suíte executada e integralmente aprovada.",
    )
    freeze.add_argument(
        "--repeat-output", type=Path, required=True,
        help="Segunda execução; somente os resultados científicos devem coincidir.",
    )
    freeze.add_argument(
        "--engine-manifest", type=Path, required=True,
        help="Manifesto JSON emitido pelo motor na primeira execução.",
    )
    freeze.add_argument(
        "--repeat-engine-manifest", type=Path, required=True,
        help="Manifesto JSON emitido pelo motor na segunda execução.",
    )
    freeze.add_argument("--output-manifest", type=Path)
    freeze.add_argument("--overwrite", action="store_true")
    freeze.add_argument("--timestamp", help="ISO 8601 com fuso; destinado a reprodutibilidade/auditoria.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            payload = prepare_package(
                args.workbook,
                args.output_dir,
                overwrite=args.overwrite,
                timestamp=args.timestamp,
            )
        else:
            payload = freeze_model_output(
                args.model_output,
                args.preparation_manifest,
                config_path=args.config,
                engine_path=args.engine,
                test_evidence_path=args.test_evidence,
                repeat_output_path=args.repeat_output,
                engine_manifest_path=args.engine_manifest,
                repeat_engine_manifest_path=args.repeat_engine_manifest,
                output_manifest_path=args.output_manifest,
                overwrite=args.overwrite,
                timestamp=args.timestamp,
            )
    except RepSPreparationError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
