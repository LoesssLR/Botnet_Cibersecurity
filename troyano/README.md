# Troyano — Agente zombie del laboratorio (disfraz de 7-Zip)

Agente Windows del laboratorio de **Seguridad de TI II (UTN)**. Abre una
conexión inversa TCP hacia el servidor C2 (`server/` de este repositorio),
se registra con un `hello` JSON, responde comandos remotos y ejecuta la
inundación `load` contra el servidor víctima. Compatible con el protocolo
documentado en [`docs/protocolo.md`](../docs/protocolo.md).

> **Ámbito autorizado del curso.** Se ejecuta únicamente en el entorno del
> laboratorio (instancias y equipos propios con autorización del docente).
> La inundación `load` es acotada y configurable, y no debe utilizarse fuera
> del alcance autorizado del curso. Las instancias de AWS de la demo ya fueron
> eliminadas; este código queda como evidencia documentada del proyecto.

## El disfraz (ingeniería social del entregable)

El instalador se hace pasar por el **instalador oficial de 7-Zip**, capa por
capa:

1. **Asistente**: nombre "7-Zip", editor "Igor Pavlov", versión 24.09, icono
   tipo 7-Zip (`assets/7z.ico`) y archivo generado `7z2409-x64.exe`
   (`installer/7-Zip.iss`). En el asistente no aparece "AgenteUTN" ni nada
   raro.
2. **Carga real**: instala el 7-Zip verdadero (`redist/7z-installer-x64.exe`)
   en silencio (`/S`), para que la instalación parezca legítima.
3. **Payload oculto**: el `.exe` se empaqueta como `7zHelper.exe` con
   metadatos de un componente de 7-Zip (`pyinstaller/version_info.txt`) y se
   copia dentro de `C:\Program Files\7-Zip`.
4. **Persistencia**: se registra en la clave `Run` de HKCU como
   "7-Zip Helper" para arrancar con Windows (el registro se elimina al
   desinstalar).

> El nombre "AgenteUTN" solo existe en este repositorio (código fuente,
> pruebas y documentación). Nada de lo instalado lo muestra. El disfraz usa
> el nombre y la apariencia de 7-Zip únicamente dentro del laboratorio
> autorizado del curso; 7-Zip es marca de Igor Pavlov y este uso académico
> no está afiliado al proyecto 7-Zip.

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
4. Modo zombie: si la conexión se pierde o el C2 está caído, **reconecta
   indefinidamente** con la espera configurada. No reconecta tras `stop`,
   `bye` o `error auth`.

## Estructura

```text
troyano/
├── README.md                 # Este documento
├── assets/
│   ├── make_icon.py          # Genera 7z.ico (solo stdlib)
│   └── 7z.ico                # Icono tipo 7-Zip (capa de disfraz)
├── src/
│   ├── main.py               # Punto de entrada: modo zombie o --menu
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
│   ├── AgenteUTN.spec        # Spec de PyInstaller (icono + metadatos, exe 7zHelper)
│   └── version_info.txt      # Metadatos de versión del .exe (disfraz 7-Zip)
├── installer/
│   ├── 7-Zip.iss             # Instalador Inno Setup disfrazado de 7-Zip
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
| `AGENT_RECONNECT_ATTEMPTS` | `3` | Reintentos rápidos de reconexión |
| `AGENT_RECONNECT_DELAY_S` | `5` | Espera entre reintentos |

## Ejecutar desde el código

```powershell
cd troyano
python -m src.main          # modo zombie (conecta al C2 y reconecta solo)
python -m src.main --menu   # menú de diagnóstico local
```

## Pruebas

```powershell
cd troyano
python -m unittest discover -s tests
```

Debe finalizar con `Ran 53 tests ... OK`.

## Compilar el payload (.exe)

```powershell
cd troyano
pip install pyinstaller
python -m PyInstaller pyinstaller/AgenteUTN.spec --noconfirm
```

Genera `troyano/dist/7zHelper.exe` con **icono tipo 7-Zip y metadatos de un
componente de 7-Zip**. El spec deja `console=True` para ver la salida del
zombie en el laboratorio; con `console=False` la ventana desaparece por
completo (disfraz total, la salida se pierde).

## Generar el instalador disfrazado

Con Inno Setup 6 instalado y `7z-installer-x64.exe` en `installer/redist/`
(ver `LEEME.txt`):

```powershell
cd troyano\installer
ISCC.exe 7-Zip.iss
```

Genera `installer/output/7z2409-x64.exe`: un asistente **idéntico al setup de
7-Zip** que instala el 7-Zip real en silencio, copia `7zHelper.exe` a
`Program Files\7-Zip` y lo registra para arrancar con Windows.

## Mejoras respecto a la versión original del entregable

- **Nombre e icono**: `.exe` con metadatos de versión de Windows e icono;
  el instalador muestra nombre, editor y versión.
- **Disfraz completo de 7-Zip**: el asistente, el archivo generado
  (`7z2409-x64.exe`), el payload (`7zHelper.exe`) y la persistencia imitan
  componentes de 7-Zip; antes el instalador se llamaba "AgenteUTN" y el
  7-Zip se instalaba en silencio sin disfraz.
- **Configuración**: sin IPs fijas en el código; todo va por variables de
  entorno (`src/config.py`), incluidos los topes del `load`, alineados con
  el servidor C2.
- **Código**: paquete `src/` con imports relativos, sin archivos legado;
  `info` incluye usuario y CPUs; modo zombie por defecto con reconexión
  indefinida (`--menu` para diagnóstico); pruebas de integración robustas.

## Notas de integración con el C2

- `agent_id` se genera como `utn-<12 hex>` al arrancar; el servidor lo sanea.
- Si el C2 tiene `C2_SHARED_SECRET`, definir la misma variable aquí antes de
  empaquetar (viaja sin cifrar; solo laboratorio).
- Tras `bye` (kick) el agente NO reconecta; para expulsión permanente el C2
  usa `send stop`.
