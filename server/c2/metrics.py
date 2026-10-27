"""Consulta de metricas del servidor objetivo via la API de Netdata."""
from __future__ import annotations

import json
import socket
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HTTP_TIMEOUT = 4.0
SOCKET_TIMEOUT = 2.0
DEFAULT_WINDOW_S = 10
CHARTS = ("system.cpu", "system.ram", "system.net")


def _split_base_url(base_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlsplit(base_url)
    return parsed.hostname or "", parsed.port or 19999


def is_netdata_reachable(base_url: str) -> bool:
    host, port = _split_base_url(base_url)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT):
            return True
    except OSError:
        return False


def fetch_chart_payload(base_url: str, chart: str, window_seconds: int = DEFAULT_WINDOW_S) -> dict:
    window = max(1, int(window_seconds))
    query = urllib.parse.urlencode(
        {"chart": chart, "after": -window, "points": 1, "group": "average", "format": "json"}
    )
    url = f"{base_url.rstrip('/')}/api/v1/data?{query}"
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_chart(payload: dict) -> dict | None:
    """Devuelve la ultima fila de un grafico de Netdata como {dimension: valor}."""
    labels = payload.get("labels") or []
    rows = payload.get("data") or []
    if not labels or not rows:
        return None
    return dict(zip(labels, rows[-1]))


def _numeric_values(row: dict | None) -> dict:
    if not row:
        return {}
    return {key: value for key, value in row.items() if key != "time" and isinstance(value, (int, float))}


def compute_metrics(cpu: dict | None, ram: dict | None, net: dict | None) -> dict:
    """Calcula cpu_pct, ram_pct y net_kbit_s a partir de las filas de Netdata."""
    result = {"cpu_pct": None, "ram_pct": None, "net_kbit_s": None}

    cpu_values = _numeric_values(cpu)
    if cpu_values:
        if "idle" in cpu_values:
            # Netdata v1: la dimension idle es el tiempo inactivo
            result["cpu_pct"] = round(100 - cpu_values["idle"], 1)
        else:
            # Netdata v2: system.cpu no trae idle; las dimensiones de uso
            # (user, system, nice, iowait, ...) suman la utilizacion total
            result["cpu_pct"] = round(sum(cpu_values.values()), 1)

    ram_values = _numeric_values(ram)
    total = sum(ram_values.values())
    if total > 0 and "used" in ram_values:
        result["ram_pct"] = round(ram_values["used"] / total * 100, 1)

    net_values = _numeric_values(net)
    if net_values:
        result["net_kbit_s"] = round(sum(net_values.values()), 1)

    return result


def fetch_target_metrics(base_url: str, window_seconds: int = DEFAULT_WINDOW_S) -> dict:
    """Consulta system.cpu, system.ram y system.net del objetivo (None si no hay dato)."""

    def safe(chart: str) -> dict | None:
        try:
            return parse_chart(fetch_chart_payload(base_url, chart, window_seconds))
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=len(CHARTS)) as executor:
        rows = list(executor.map(safe, CHARTS))
    return compute_metrics(*rows)
