"""Despachador de comandos con lista de permitidos (whitelist)."""
from __future__ import annotations

from commands import handle_command

ALLOWED_COMMANDS = {"ping", "info", "echo", "stop"}


def dispatch_command(message: dict) -> dict:
    """Valida un frame `command` y lo resuelve si el nombre está permitido."""
    if not isinstance(message, dict):
        raise ValueError("El mensaje debe ser un objeto")
    if message.get("type") != "command":
        raise ValueError("El mensaje no es un comando")
    if not isinstance(message.get("id"), str) or not message["id"]:
        raise ValueError("ID de comando inválido")

    name = message.get("name")
    if not isinstance(name, str) or name not in ALLOWED_COMMANDS:
        return {
            "type": "result",
            "id": message["id"],
            "status": "error",
            "data": {"error": "Comando no permitido"},
        }

    return handle_command(message)
