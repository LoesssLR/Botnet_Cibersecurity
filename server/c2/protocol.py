"""Protocolo del C2: un mensaje JSON por linea terminado en salto de linea."""
from __future__ import annotations

import json
from typing import Any

MAX_MESSAGE_BYTES = 64 * 1024


def encode(message: dict) -> bytes:
    return (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode(line: bytes) -> dict:
    message: Any = json.loads(line.decode("utf-8"))
    if not isinstance(message, dict) or "type" not in message:
        raise ValueError("mensaje JSON sin campo 'type'")
    return message


async def read_message(reader) -> dict | None:
    line = await reader.readline()
    if not line:
        return None
    if len(line) > MAX_MESSAGE_BYTES:
        raise ValueError("mensaje excede el tamano maximo permitido")
    return decode(line)
