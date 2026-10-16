# Arquitectura del laboratorio

Botnet de laboratorio en entorno controlado: instancias propias en AWS y equipos de
prueba de la Universidad, con autorización del docente.

## Componentes

| Componente | Ubicación | Rol |
|---|---|---|
| Atacante (admin) | Nodo externo | Consola de comando y control del C2 |
| Servidor botnet (C2) | AWS EC2 (Ubuntu Server) | Recibe conexiones inversas, administra zombies, envía instrucciones y registra métricas |
| Servidor víctima | AWS EC2 (Ubuntu Server) | Objetivo de las pruebas; expone un servicio web y Netdata para monitoreo |
| Hosts zombie | Equipos de prueba (red UTN) | Se conectan de forma inversa al C2 y ejecutan las instrucciones recibidas |

## Flujos

1. **Comando y control:** el atacante administra el servidor botnet (SSH y consola del C2).
2. **Conexión inversa:** cada host zombie inicia y mantiene una conexión hacia el servidor botnet.
3. **Tráfico de ataque controlado:** ante una orden del atacante, los zombies generan
   solicitudes contra el servidor víctima.
4. **Métricas:** el servidor víctima registra su comportamiento con Netdata; el C2
   consulta esa información y la registra.

## Diagrama

```
        Atacante (admin)
              │  consola C2
              ▼
   ┌────────────────────┐        conexión inversa       ┌─────────────────────┐
   │  Servidor botnet   │◄──────────────────────────────│  Host zombie 1..N   │
   │  Ubuntu · AWS EC2  │                               │  (equipos de prueba)│
   │  IP elástica       │                               └──────────┬──────────┘
   └──────────┬─────────┘                                          │
              │ métricas (API Netdata)             ataque HTTP controlado
              ▼                                                   │
   ┌────────────────────┐                                         │
   │  Servidor víctima  │◄────────────────────────────────────────┘
   │  Ubuntu · Netdata  │
   │  AWS EC2           │
   └────────────────────┘
```

## Infraestructura AWS

| Instancia | Rol | Tipo sugerido | Recursos | Detalle |
|---|---|---|---|---|
| Botnet | C2 | t3.medium | 2 vCPU / 4 GB | IP elástica; puerto del C2 accesible desde Internet |
| Víctima | Objetivo | t3.micro | 2 vCPU / 1 GB | IP elástica; Netdata; servicio web de prueba |

## Puertos (propuesta)

| Servicio | Puerto | Protocolo | Origen |
|---|---|---|---|
| SSH | 22 | TCP | Solo IP del equipo de trabajo |
| Consola/C2 | 8443 | TCP | Internet (los zombies se conectan desde la red UTN) |
| HTTP víctima | 80 | TCP | Internet (tráfico de prueba) |
| Netdata | 19999 | TCP | Solo IP del equipo de trabajo (o túnel SSH) |

> Durante las pruebas, Netdata queda accesible solo mediante túnel SSH; en la
> demostración se puede habilitar temporalmente al rango de la red de la Universidad.
