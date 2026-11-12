"""Interpretación de eventos del servidor C2 (error y bye)."""
from __future__ import annotations


def handle_server_event(message: dict) -> dict:
    """Traduce un frame del servidor a una acción local.

    Devuelve `{"action": ..., "reconnect": ..., "reason": ...}`:
      - error auth      -> desconectar sin reconectar
      - error busy      -> desconectar y reconectar
      - bye             -> desconectar sin reconectar (expulsión)
      - cualquier otro  -> ignorar
    """
    if not isinstance(message, dict):
        raise ValueError("El mensaje debe ser un objeto")

    message_type = message.get("type")

    if message_type == "error":
        code = message.get("code")
        if code == "auth":
            return {"action": "disconnect", "reconnect": False, "reason": "Autenticación rechazada"}
        if code == "busy":
            return {"action": "disconnect", "reconnect": True, "reason": "Servidor ocupado"}
        return {"action": "disconnect", "reconnect": False, "reason": "Error desconocido"}

    if message_type == "bye":
        return {
            "action": "disconnect",
            "reconnect": False,
            "reason": message.get("reason", "Expulsado"),
        }

    return {"action": "ignore", "reconnect": False, "reason": "Mensaje no aplicable"}
