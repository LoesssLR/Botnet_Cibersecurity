"""Configuración del agente por variables de entorno.

Sin variables definidas, el agente apunta a un C2 local (127.0.0.1:8443)
para pruebas de laboratorio. En la demo, el equipo definía estas variables
en la máquina donde se empaquetaba o ejecutaba el agente.

Variables:
    C2_HOST / C2_PORT         dirección del servidor C2
    C2_SHARED_SECRET          secreto compartido (campo `secret` del hello)
    VICTIMA_URL               URL de diagnóstico (opcional)
    FLOOD_MAX_DURATION_S      tope de duración del load (0 = sin tope)
    FLOOD_MAX_CONCURRENCY     tope de concurrencia del load (0 = sin tope)
    AGENT_RECONNECT_ATTEMPTS  reintentos máximos de reconexión (0 = sin límite)
    AGENT_RECONNECT_DELAY_S   espera entre reintentos
"""
from __future__ import annotations

import os

APP_NAME = "AgenteUTN"
VERSION = "2.0"

C2_HOST = os.environ.get("C2_HOST", "127.0.0.1")
C2_SHARED_SECRET = os.environ.get("C2_SHARED_SECRET", "")
VICTIMA_URL = os.environ.get("VICTIMA_URL", "").strip()

DEFAULT_MAX_DURATION_S = 120
DEFAULT_MAX_CONCURRENCY = 200
DEFAULT_RECONNECT_ATTEMPTS = 3
DEFAULT_RECONNECT_DELAY_S = 5


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


C2_PORT = _env_int("C2_PORT", 8443)
MAX_DURATION_S = _env_int("FLOOD_MAX_DURATION_S", DEFAULT_MAX_DURATION_S)
MAX_CONCURRENCY = _env_int("FLOOD_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)
RECONNECT_MAX_ATTEMPTS = _env_int("AGENT_RECONNECT_ATTEMPTS", DEFAULT_RECONNECT_ATTEMPTS)
RECONNECT_DELAY_S = _env_int("AGENT_RECONNECT_DELAY_S", DEFAULT_RECONNECT_DELAY_S)
