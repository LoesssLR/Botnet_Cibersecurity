"""Política de reconexión del agente.

Reglas:
  - `bye`, `error auth` u otros errores  -> no reconectar.
  - `error busy` o conexión perdida      -> reconectar, con un máximo de
    intentos y espera configurables por variables de entorno.
"""
from __future__ import annotations

from .config import RECONNECT_DELAY_S, RECONNECT_MAX_ATTEMPTS


def reconnect_decision(event: dict, attempts: int = 0) -> dict:
    """Determina si corresponde reintentar la conexión."""
    if not isinstance(event, dict):
        raise ValueError("El evento debe ser un diccionario")
    if not isinstance(attempts, int) or attempts < 0:
        raise ValueError("Número de intentos inválido")

    event_type = event.get("type")

    if event_type == "bye":
        return {"retry": False, "delay": 0}

    if event_type == "error":
        if event.get("code") == "busy":
            return {"retry": True, "delay": RECONNECT_DELAY_S}
        return {"retry": False, "delay": 0}

    if event_type != "connection_lost":
        return {"retry": False, "delay": 0}

    if RECONNECT_MAX_ATTEMPTS > 0 and attempts >= RECONNECT_MAX_ATTEMPTS:
        return {"retry": False, "delay": 0}

    return {"retry": True, "delay": RECONNECT_DELAY_S}
