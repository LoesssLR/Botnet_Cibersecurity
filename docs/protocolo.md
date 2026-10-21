# Protocolo C2 (servidor <-> agente)

Transporte: TCP. Cada mensaje es una linea de texto UTF-8 con un objeto JSON,
terminada en `\n`. Tamano maximo por mensaje: 64 KB.

## Agente -> Servidor

### hello (obligatorio al conectar)

```json
{"type":"hello","agent_id":"zombie-01","hostname":"PC-LAB","os":"Windows 11","user":"maria","version":"0.1","secret":"<C2_SHARED_SECRET>"}
```

Si el servidor tiene configurado `C2_SHARED_SECRET`, el campo `secret` debe coincidir
o la conexion se rechaza.

### heartbeat (cada 10 s, opcional)

```json
{"type":"heartbeat","ts":1730000000.0}
```

### result (respuesta a un comando)

```json
{"type":"result","id":"a1b2c3d4","status":"ok","data":{"pong":true}}
```

`id` debe copiar el identificador recibido en el comando. `status` es `ok` o `error`.

## Servidor -> Agente

### command

```json
{"type":"command","id":"a1b2c3d4","name":"ping","args":{}}
```

### command load (inundacion controlada)

```json
{"type":"command","id":"a1b2c3d4","name":"load","args":{"target":"http://IP_VICTIMA","duration":30,"concurrency":20}}
```

`duration` y `concurrency` son numeros enteros, no strings. El servidor valida y
normaliza el target (`http://` explicito, hostname valido, allowlist opcional con
`TARGET_HOST`/`TARGET_HTTP_PORT`) y recorta `duration` <= 120 s y `concurrency`
<= 200 por agente; los valores `<= 0` o no numericos se rechazan. Debe usarse
unicamente contra el servidor victima del laboratorio.

### error (rechazo del servidor)

```json
{"type":"error","code":"auth","status":"error","error":"secreto invalido"}
```

`code: "auth"` indica que el `hello` fue rechazado y el agente no debe reconectar.
`code: "busy"` indica que el servidor alcanzo su limite de conexiones; conviene
reintentar con espera.

### bye (expulsion)

```json
{"type":"bye","reason":"kicked"}
```

El servidor lo envia antes de cerrar por `kick`. El agente de prueba termina con
codigo 0 y no reconecta; un agente externo puede ignorarlo, pero el socket se
cierra de todos modos.

## Comandos del agente de prueba

| Comando | Args | Respuesta | Estado |
|---|---|---|---|
| ping | - | `{"pong": true}` | implementado |
| info | - | datos del sistema (hostname, SO, usuario, version de Python, CPUs) | implementado |
| echo | text | el mismo texto | implementado |
| stop | - | el agente termina su ejecucion y no reconecta | implementado |
| load | target, duration, concurrency | `{"sent": n, "errors": m, "rps": r, "duration_s": d}` | implementado |

## Notas de integracion

- El agente final (otro integrante) debe implementar `hello`, `heartbeat` y `result`
  con este formato para integrarse con el servidor.
- `agent_id` se sanea en el servidor: caracteres de control/ANSI se eliminan, los
  caracteres no seguros se reemplazan por `_` y la longitud maxima es 64. Conviene
  usar IDs simples como `zombie-01`.
- Recomendado: reconexion automatica con espera (por ejemplo cada 5 s) y
  `heartbeat` cada 10 s, para que los zombies sigan conectados si el C2 se
  reinicia (el servidor reemplaza la conexion anterior del mismo `agent_id`).
  No reconectar tras `error code=auth`, `bye` o `stop`.
- El agente de prueba ejecuta `load` en segundo plano: sigue procesando `ping` y
  `stop` durante la inundacion, y cancela los workers si llega `stop` o se cae la
  conexion con el C2.
- Cualquier mensaje cuyo `type` no se reconozca se ignora. Un agente externo debe
  tolerar `error` y `bye` sin romperse.
