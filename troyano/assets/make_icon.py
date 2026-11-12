"""Genera assets/7z.ico (icono tipo 7-Zip) usando solo la biblioteca estándar.

El icono imita el logo de 7-Zip (cuadrado azul redondeado con "7z" blanco)
para la capa de disfraz del instalador del laboratorio. Se renderiza en
256x256 y 32x32 como PNG dentro del contenedor ICO (compatible con
PyInstaller e Inno Setup).

Uso:  python assets/make_icon.py
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent
OUTPUT = ASSETS_DIR / "7z.ico"

GRID = 16  # retícula del dibujo (células)

BACKGROUND = (31, 95, 196, 255)     # azul 7-Zip #1F5FC4
BORDER = (24, 70, 145, 255)         # azul oscuro para el borde
TEXT = (255, 255, 255, 255)         # blanco
TRANSPARENT = (0, 0, 0, 0)

# "7" (barra superior + diagonal hacia abajo-izquierda) y "z" (abajo a la derecha)
GLYPH_CELLS = {
    # "7" grande (arriba)
    (2, 1), (3, 1), (4, 1), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1),
    (9, 2), (8, 3), (7, 4), (6, 5), (5, 6), (4, 7), (3, 8), (2, 9),
    # "z" pequeña (abajo a la derecha)
    (9, 10), (10, 10), (11, 10), (12, 10), (13, 10), (14, 10),
    (13, 11), (12, 12), (11, 13),
    (9, 14), (10, 14), (11, 14), (12, 14), (13, 14), (14, 14),
}

CORNER_CELLS = {(0, 0), (0, GRID - 1), (GRID - 1, 0), (GRID - 1, GRID - 1)}


def _cell_color(column: int, row: int) -> tuple[int, int, int, int]:
    if (column, row) in CORNER_CELLS:
        return TRANSPARENT
    if (column, row) in GLYPH_CELLS:
        return TEXT
    if column in (0, GRID - 1) or row in (0, GRID - 1):
        return BORDER
    return BACKGROUND


def _png(width: int, height: int, rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    raw = b"".join(
        b"\x00" + b"".join(bytes(pixel) for pixel in row)
        for row in rows
    )
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _render(size: int) -> bytes:
    """Renderiza el dibujo en un cuadrado de `size` x `size` (múltiplo de GRID)."""
    factor = size // GRID
    rows = [
        [_cell_color(x // factor, y // factor) for x in range(size)]
        for y in range(size)
    ]
    return _png(size, size, rows)


def _ico(pngs: list[tuple[int, bytes]]) -> bytes:
    """Envuelve PNGs en un contenedor ICO (Vista+, con PNG embebido)."""
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries = b""
    blobs = b""
    for size, data in pngs:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII",
            dimension,      # ancho (0 = 256)
            dimension,      # alto (0 = 256)
            0,              # paleta
            0,              # reservado
            1,              # planos
            32,             # bits por píxel
            len(data),      # tamaño del PNG
            offset,         # offset del PNG
        )
        blobs += data
        offset += len(data)
    return header + entries + blobs


def main() -> None:
    OUTPUT.write_bytes(_ico([(32, _render(32)), (256, _render(256))]))
    print(f"icono generado: {OUTPUT}")


if __name__ == "__main__":
    main()
