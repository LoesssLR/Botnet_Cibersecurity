# AgenteUTN — Agente zombie del laboratorio (troyano)

Agente Windows del laboratorio de **Seguridad de TI II (UTN)**. Abre una
conexión inversa TCP hacia el servidor C2 (`server/` de este repositorio),
se registra con un `hello` JSON, responde comandos remotos y ejecuta la
inundación `load` contra el servidor víctima. Compatible con el protocolo
documentado en [`docs/protocolo.md`](../docs/protocolo.md).

> **Ámbito autorizado del curso.** Se ejecuta únicamente en el entorno del
> laboratorio (instancias propias con autorización del docente). La inundación
> `load` es acotada y configurable, y no debe utilizarse fuera del alcance
> autorizado del curso. Las instancias de AWS de la demo ya fueron eliminadas;
> este código queda como evidencia documentada del proyecto.

## Cómo funciona (resumen)

1. La dirección del C2 (`C2_HOST` / `C2_PORT`) está configurada en
   `src/config.py` (variables de entorno, defecto `127.0.0.1:8443`).
   En la demo se empaquetaba con la IP elástica del C2.
2. Al ejecutarse, el agente abre un **socket TCP hacia el C2** (conexión
   inversa: la víctima llama hacia afuera) y envía como primera línea el
   `hello`:
   ```json
   {"type":"hello","agent_id":"utn-...","hostname":"PC","os":"Windows 11","user":"...","version":"2.0","secret":""}
   ```
3. Mantiene la sesión con `heartbeat` cada 10 s y responde `ping`, `info`,
   `echo` y `stop`. El comando `load` corre en segundo plano (cancelable con
   `stop` o si se pierde la conexión).
4. Si la conexión se pierde o el servidor responde `busy`, reconecta según la
   política de `src/reconnect_policy.py`. No reconecta tras `stop`, `bye` o
   `error auth`.

## Estructura

```text
troyano/
├── README.md                 # Este documento
├── assets/
│   ├── make_icon.py          # Genera agente.ico (solo stdlib)
│   └── agente.ico            # Icono de la aplicación
├── src/
│   ├── main.py               # Menú de la aplicación (punto de entrada del .exe)
│   ├── config.py             # Configuración por variables de entorno
│   ├── c2_client.py          # Sesión TCP con el C2 (hello, comandos, load, reconexión)
│   ├── load_command.py       # Inundación HTTP controlada (solo stdlib)
│   ├── commands.py           # ping / info / stop / echo
│   ├── command_dispatcher.py # Whitelist de comandos permitidos
│   ├── protocol.py           # Codificación/decodificación JSON por línea (64 KB)
│   ├── identity.py           # hello y heartbeat
│   ├── response.py           # Construcción de frames result
│   ├── server_events.py      # Interpretación de bye/error del servidor
│   └── reconnect_policy.py   # Política de reconexión
├── pyinstaller/
│   ├── AgenteUTN.spec        # Spec de PyInstaller (icono + metadatos de versión)
│   └── version_info.txt      # Metadatos de versión de Windows del .exe
├── installer/
│   ├── AgenteUTN.iss         # Instalador Inno Setup (nombre, icono, 7-Zip opcional)
│   └── redist/LEEME.txt      # Dónde colocar 7z-installer-x64.exe (no se versiona)
└── tests/                    # Suite de pruebas (53 pruebas)
```

## Configuración

Todas las variables son opcionales (ver `src/config.py`):

| Variable | Defecto | Uso |
|---|---|---|
| `C2_HOST` | `127.0.0.1` | Dirección del servidor C2 |
| `C2_PORT` | `8443` | Puerto del servidor C2 |
| `C2_SHARED_SECRET` | vacío | Secreto enviado en el campo `secret` del hello |
| `VICTIMA_URL` | vacío | URL de diagnóstico del menú (opción 4) |
| `FLOOD_MAX_DURATION_S` | `120` | Tope de duración del load (`0` = sin tope) |
| `FLOOD_MAX_CONCURRENCY` | `200` | Tope de conexiones por agente (`0` = sin tope) |
| `AGENT_RECONNECT_ATTEMPTS` | `3` | Reintentos máximos de reconexión |
| `AGENT_RECONNECT_DELAY_S` | `5` | Espera entre reintentos |

## Ejecutar desde el código

```powershell
cd troyano
python -m src.main
```

Opción **5** del menú: conecta al C2 en modo zombie (se queda escuchando
comandos hasta `stop`/`bye`/Ctrl+C, con reconexión automática).

## Pruebas

```powershell
cd troyano
python -m unittest discover -s tests
```

Debe finalizar con `Ran 53 tests ... OK`.

## Compilar el .exe

```powershell
cd troyano
pip install pyinstaller
python -m PyInstaller pyinstaller/AgenteUTN.spec --noconfirm
```

Genera `troyano/dist/AgenteUTN.exe` con **nombre, icono y metadatos de versión
de Windows** (consola, sin dependencias externas).

## Generar el instalador

Con Inno Setup 6 instalado y `7z-installer-x64.exe` en `installer/redist/`
(ver `LEEME.txt`):

```powershell
cd troyano\installer
ISCC.exe AgenteUTN.iss
```

Genera `installer/output/AgenteUTN_Setup.exe`. El asistente muestra **nombre,
editor, versión e icono**, y el componente **7-Zip aparece desmarcado por
defecto** en la página de componentes: solo se instala si el usuario lo marca.

## Mejoras respecto a la versión original del entregable

- **Nombre**: el `.exe` lleva metadatos de versión de Windows
  (`FileDescription`, `ProductName`, `FileVersion` 2.0.0.0) y el instalador
  muestra nombre, editor y versión.
- **Icono**: `assets/agente.ico` (generado con `make_icon.py`, solo stdlib),
  aplicado al `.exe`, al instalador y a los accesos directos.
- **Confirmación del 7-Zip**: el componente es opcional y está **desmarcado
  por defecto** en el asistente; antes se instalaba en silencio con `/S`.
- **Configuración**: sin IPs fijas en el código; todo va por variables de
  entorno (`src/config.py`), incluidos los topes del `load`, alineados con
  el servidor C2.
- **Código**: paquete `src/` con imports relativos, sin archivos legado
  (`ping_client.py`, `aws_diagnostic.py`, `local_client.py` eliminados);
  `info` incluye usuario y CPUs; pruebas de integración robustas (sin
  excepciones huérfanas de tareas de servidor).

## Notas de integración con el C2

- `agent_id` se genera como `utn-<12 hex>` al arrancar; el servidor lo sanea.
- Si el C2 tiene `C2_SHARED_SECRET`, definir la misma variable aquí antes de
  empaquetar (viaja sin cifrar; solo laboratorio).
- Tras `bye` (kick) el agente NO reconecta; para expulsión permanente el C2
  usa `send stop`.
