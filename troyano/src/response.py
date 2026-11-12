"""Construcción de frames `result` del protocolo C2."""
from __future__ import annotations


def build_result(command: dict, status: str, data: dict) -> dict:
    """Construye la respuesta a un comando con su id de correlación."""
    if command.get("type") != "command":
        raise ValueError("El mensaje no es un comando")
    command_id = command.get("id")
    if not isinstance(command_id, str) or not command_id:
        raise ValueError("Identificador de comando inválido")
    if status not in ("ok", "error"):
        raise ValueError("Estado inválido")
    if not isinstance(data, dict):
        raise ValueError("Los datos deben ser un objeto")
    return {
        "type": "result",
        "id": command_id,
        "status": status,
        "data": data,
    }
