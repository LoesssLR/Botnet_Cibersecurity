"""Configuracion del servidor C2 (variables de entorno y archivo .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8443


def _parse_value(raw_value: str) -> str:
    """Limpia un valor de .env: comentario inline y comillas envolventes.

    Un '#' inicia un comentario solo si esta fuera de comillas y al comienzo del
    valor o precedido por un espacio. Asi no se truncan secretos que lo
    contengan sin espacios (por ejemplo, 'abc#123').
    """
    quote = ""
    for index, character in enumerate(raw_value):
        if quote:
            if character == quote:
                quote = ""
        elif character in ("'", '"'):
            quote = character
        elif character == "#" and (index == 0 or raw_value[index - 1].isspace()):
            raw_value = raw_value[:index]
            break
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, _parse_value(value))


@dataclass
class Config:
    bind_host: str
    port: int
    shared_secret: str
    netdata_url: str
    log_dir: Path
    data_dir: Path
    target_host: str = ""
    target_http_port: int | None = None

    @classmethod
    def load(cls) -> "Config":
        load_env_file(PROJECT_ROOT / ".env")
        log_dir = Path(os.environ.get("LOG_DIR", "logs"))
        data_dir = Path(os.environ.get("DATA_DIR", "data"))
        if not log_dir.is_absolute():
            log_dir = PROJECT_ROOT / log_dir
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir
        raw_target_port = os.environ.get("TARGET_HTTP_PORT", "").strip()
        target_http_port: int | None = None
        if raw_target_port:
            try:
                target_http_port = int(raw_target_port)
            except ValueError as exc:
                raise ValueError("TARGET_HTTP_PORT debe ser un entero") from exc
            if not 1 <= target_http_port <= 65535:
                raise ValueError("TARGET_HTTP_PORT fuera de rango (1-65535)")
        return cls(
            bind_host=os.environ.get("C2_BIND_HOST", DEFAULT_HOST),
            port=int(os.environ.get("C2_PORT", DEFAULT_PORT)),
            shared_secret=os.environ.get("C2_SHARED_SECRET", ""),
            netdata_url=os.environ.get("NETDATA_URL", ""),
            log_dir=log_dir,
            data_dir=data_dir,
            target_host=os.environ.get("TARGET_HOST", "").strip(),
            target_http_port=target_http_port,
        )
