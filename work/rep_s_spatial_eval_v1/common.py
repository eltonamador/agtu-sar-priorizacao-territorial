#!/usr/bin/env python3
"""Utilitarios compartilhados do protocolo REP-S-SPATIAL-EVAL-v1.0."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "config_rep_s_spatial_eval_v1.json"
EXPECTED_CONFIG_SHA256 = "12819b0b7d623d48ef0d6d3955f62f06cccf37b54a01506fe5a0793649e9d4ab"
EARTH_RADIUS_M = 6_371_008.8


class ProtocolError(RuntimeError):
    """Falha de contrato, integridade, estado ou avaliacao."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stable_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def fold_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value if value is not None else ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold().strip()


def parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    token = fold_text(value)
    if token in {"true", "1", "sim", "yes"}:
        return True
    if token in {"false", "0", "nao", "no"}:
        return False
    raise ProtocolError(f"{field} deve ser booleano; recebido {value!r}.")


def parse_finite_float(value: Any, field: str) -> float:
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"{field} deve ser numerico; recebido {value!r}.") from exc
    if not math.isfinite(number):
        raise ProtocolError(f"{field} deve ser finito.")
    return number


def read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"JSON invalido ou inacessivel: {path}") from exc


def atomic_write_bytes(path: str | Path, payload: bytes) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_json(path: str | Path, value: Any) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    atomic_write_bytes(path, payload)


def csv_payload(headers: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> bytes:
    import io

    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=list(headers), lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({header: row.get(header, "") for header in headers})
    return text.getvalue().encode("utf-8")


def write_csv(path: str | Path, headers: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    atomic_write_bytes(path, csv_payload(headers, rows))


def read_csv(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            headers = list(reader.fieldnames or [])
            if not headers:
                raise ProtocolError(f"CSV sem cabecalho: {path}")
            if len(headers) != len(set(headers)):
                raise ProtocolError(f"CSV com cabecalhos duplicados: {path}")
            return headers, [dict(row) for row in reader]
    except OSError as exc:
        raise ProtocolError(f"CSV inacessivel: {path}") from exc


def load_config(path: str | Path = DEFAULT_CONFIG) -> tuple[dict[str, Any], str]:
    config_path = Path(path).resolve()
    observed = sha256_file(config_path)
    if observed != EXPECTED_CONFIG_SHA256:
        raise ProtocolError(
            "Falha de integridade: config_rep_s_spatial_eval_v1.json diverge do hash congelado."
        )
    config = read_json(config_path)
    if config.get("protocol_id") != "REP-S-SPATIAL-EVAL-v1.0":
        raise ProtocolError("protocol_id divergente do protocolo congelado.")
    if config.get("status") != "CONGELADO_ANTES_DA_COLETA":
        raise ProtocolError("O protocolo nao esta marcado como congelado antes da coleta.")
    return config, observed


def resolve_dependency(config_path: Path, relative_path: str) -> Path:
    return (config_path.resolve().parent / relative_path).resolve()


def validate_dependencies(config: Mapping[str, Any], config_path: str | Path) -> list[dict[str, Any]]:
    base = Path(config_path).resolve()
    verified: list[dict[str, Any]] = []
    for dependency in config["dependencies"]["pinned_files"]:
        path = resolve_dependency(base, str(dependency["relative_path"]))
        if not path.is_file():
            raise ProtocolError(f"Dependencia congelada ausente: {path}")
        observed = sha256_file(path)
        if observed != dependency["sha256"]:
            raise ProtocolError(
                f"Dependencia alterada ({dependency['role']}): esperado {dependency['sha256']}, observado {observed}."
            )
        verified.append(
            {
                "role": dependency["role"],
                "path": str(path),
                "sha256": observed,
                "bytes": path.stat().st_size,
            }
        )
    return verified


def file_record(path: str | Path, role: str) -> dict[str, Any]:
    target = Path(path).resolve()
    if not target.is_file():
        raise ProtocolError(f"Arquivo esperado ausente ({role}): {target}")
    return {
        "role": role,
        "path": str(target),
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
    }


def assert_file_record(record: Mapping[str, Any]) -> Path:
    path = Path(str(record.get("path", ""))).resolve()
    if not path.is_file():
        raise ProtocolError(f"Artefato congelado ausente: {path}")
    observed = sha256_file(path)
    if observed != record.get("sha256"):
        raise ProtocolError(f"Artefato mudou depois do congelamento: {path}")
    return path


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def aeqd_forward(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    phi = math.radians(lat)
    lam = math.radians(lon)
    phi0 = math.radians(lat0)
    lam0 = math.radians(lon0)
    delta = (lam - lam0 + math.pi) % (2.0 * math.pi) - math.pi
    cos_c = max(
        -1.0,
        min(1.0, math.sin(phi0) * math.sin(phi) + math.cos(phi0) * math.cos(phi) * math.cos(delta)),
    )
    c = math.acos(cos_c)
    k = 1.0 if c <= 1e-15 else c / math.sin(c)
    x = EARTH_RADIUS_M * k * math.cos(phi) * math.sin(delta)
    y = EARTH_RADIUS_M * k * (
        math.cos(phi0) * math.sin(phi) - math.sin(phi0) * math.cos(phi) * math.cos(delta)
    )
    return x, y


def point_segment_distance_m(
    point: tuple[float, float], first: tuple[float, float], second: tuple[float, float]
) -> float:
    px, py = point
    ax, ay = first
    bx, by = second
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    if denominator <= 1e-24:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def point_in_polygon(point: tuple[float, float], ring: Sequence[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for first, second in zip(ring, ring[1:]):
        x1, y1 = first
        x2, y2 = second
        if (y1 > y) != (y2 > y):
            cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < cross:
                inside = not inside
    return inside


def closed_polygon_membership(
    *,
    point_lat: float,
    point_lon: float,
    polygon_lon_lat: Sequence[Sequence[float]],
    center_lat: float,
    center_lon: float,
    tolerance_m: float,
) -> tuple[bool, bool, float]:
    """Retorna (membro, na_fronteira, distancia_minima_da_borda_m)."""

    if len(polygon_lon_lat) < 4:
        raise ProtocolError("Poligono setorial com menos de quatro coordenadas.")
    ring = [
        aeqd_forward(float(lat), float(lon), center_lat, center_lon)
        for lon, lat in polygon_lon_lat
    ]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    point = aeqd_forward(point_lat, point_lon, center_lat, center_lon)
    minimum = min(point_segment_distance_m(point, a, b) for a, b in zip(ring, ring[1:]))
    boundary = minimum <= tolerance_m
    return point_in_polygon(point, ring) or boundary, boundary, minimum


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    p = successes / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denominator
    margin = z * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def proportion_record(successes: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(successes, total)
    return {
        "successes": int(successes),
        "total": int(total),
        "rate": None if total <= 0 else successes / total,
        "wilson_95_low": low,
        "wilson_95_high": high,
    }


def mean(values: Sequence[float]) -> float | None:
    return None if not values else sum(values) / len(values)


def median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0
