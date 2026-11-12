# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller del AgenteUTN: .exe con nombre, icono y metadatos
# de versión de Windows. Compilar desde troyano/:
#   python -m PyInstaller pyinstaller/AgenteUTN.spec --noconfirm

from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ICON = ROOT / "assets" / "agente.ico"
VERSION_INFO = ROOT / "pyinstaller" / "version_info.txt"

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AgenteUTN",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=str(VERSION_INFO),
)
