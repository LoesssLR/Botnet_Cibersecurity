"""Comandos locales del agente: ping, info, stop y echo."""
from __future__ import annotations

import getpass
import os
import platform
import socket


def handle_command(message: dict) -> dict:
    """Resuelve un comando del C2 y devuelve el frame `result`."""
    command_id = message.get("id")
    name = message.get("name")

    if name == "ping":
        return {
            "type": "result",
            "id": command_id,
            "status": "ok",
            "data": {"pong": True},
        }

    if name == "info":
        return {
            "type": "result",
            "id": command_id,
            "status": "ok",
            "data": {
                "hostname": socket.gethostname(),
                "os": platform.platform(),
                "user": getpass.getuser(),
                "python": platform.python_version(),
                "cpus": os.cpu_count(),
            },
        }

    if name == "stop":
        return {
            "type": "result",
            "id": command_id,
            "status": "ok",
            "data": {"stopping": True},
        }

    if name == "echo":
        args = message.get("args") or {}
        return {
            "type": "result",
            "id": command_id,
            "status": "ok",
            "data": {"text": str(args.get("text", ""))},
        }

    return {
        "type": "result",
        "id": command_id,
        "status": "error",
        "data": {"error": "Comando no soportado"},
    }
