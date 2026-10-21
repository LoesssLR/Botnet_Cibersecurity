"""Punto de entrada del servidor C2 (uso: python server/main.py)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from c2.config import Config
from c2.console import Console
from c2.manager import AgentManager


def setup_logging(log_dir) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "c2.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


async def run(args: argparse.Namespace) -> None:
    config = Config.load()
    if args.host:
        config.bind_host = args.host
    if args.port is not None:
        config.port = args.port
    if args.secret is not None:
        config.shared_secret = args.secret
    setup_logging(config.log_dir)
    config.data_dir.mkdir(parents=True, exist_ok=True)

    manager = AgentManager(config.bind_host, config.port, config.shared_secret)
    console = Console(manager, config)
    manager.on_event = console.event
    await manager.start()
    try:
        await console.run()
    finally:
        await manager.stop()
        print("Servidor detenido.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Servidor C2 - laboratorio Seguridad de TI II (UTN)")
    parser.add_argument("--host", help="interfaz de escucha (default: C2_BIND_HOST o 0.0.0.0)")
    parser.add_argument("--port", type=int, help="puerto de escucha (default: C2_PORT o 8443)")
    parser.add_argument("--secret", help="secreto compartido (default: C2_SHARED_SECRET)")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\ninterrumpido por el usuario")
    return 0


if __name__ == "__main__":
    sys.exit(main())
