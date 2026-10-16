# Despliegue en AWS

Guía para crear las dos instancias del laboratorio en Amazon Web Services.

## Requisitos previos

- Cuenta AWS con permisos de EC2.
- Un par de claves SSH (`.pem`).
- IP pública del equipo de trabajo (por ejemplo con `curl ifconfig.me`).
- Alerta de presupuesto configurada (las instancias se cobran por hora).

## 1. Grupos de seguridad

Crear dos grupos de seguridad en la VPC por defecto.

### sg-botnet

| Tipo | Puerto | Origen | Descripción |
|---|---|---|---|
| SSH | 22 | IP del equipo | Administración |
| TCP personalizado | 8443 | 0.0.0.0/0 | Conexiones inversas de los zombies |

### sg-victima

| Tipo | Puerto | Origen | Descripción |
|---|---|---|---|
| SSH | 22 | IP del equipo | Administración |
| HTTP | 80 | 0.0.0.0/0 | Tráfico de ataque controlado |
| TCP personalizado | 19999 | IP del equipo (o túnel SSH) | Netdata |

## 2. Instancia del servidor botnet

1. EC2 → Launch instance.
2. Nombre: `botnet-c2`. AMI: Ubuntu Server 24.04 LTS (64-bit x86).
3. Tipo: `t3.medium` (2 vCPU / 4 GB, según el enunciado).
4. Key pair: el creado. Almacenamiento: 20 GB gp3.
5. Security group: `sg-botnet` (solo los puertos de la sección 1; en el asistente
   **no marque** "Allow HTTP" ni "Allow HTTPS": este servidor no los usa).
6. Lanzar y esperar el estado `running`.

## 3. IP elástica del botnet

1. EC2 → Elastic IPs → Allocate Elastic IP address.
2. Asociarla a `botnet-c2`.
3. Anotar la IP: es la dirección de conexión inversa que usarán los agentes
   (y el `.exe` del compañero); el servidor C2 no necesita configurarla.

## 4. Instancia del servidor víctima

1. EC2 → Launch instance.
2. Nombre: `victima`. AMI: Ubuntu Server 24.04 LTS.
3. Tipo: `t3.micro`.
4. Security group: `sg-victima`.
5. Lanzar, asignar una segunda IP elástica y anotarla (`TARGET_HOST`).

## 5. Configuración base (ambas instancias)

### Acceso por SSH con PuTTY (Windows)

1. Abrir **PuTTYgen** → `Load` → seleccionar el `.pem` (cambiar el filtro a
   "All Files (*.*)") → `Save private key` → guardar como `botnet-c2-key.ppk`.
2. Abrir **PuTTY** → Host Name: `ubuntu@<IP_PUBLICA>` (usuario `ubuntu`),
   puerto `22`.
3. Connection → SSH → Auth → Credentials → cargar el archivo `.ppk`.
4. `Open`, aceptar la huella del servidor la primera vez y guardar la sesión con
   un nombre (por ejemplo `botnet-c2`) para reutilizarla.

```bash
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone America/Costa_Rica
```

Reglas UFW equivalentes a los grupos de seguridad (opcional, recomendado):

```bash
# En el botnet
sudo ufw allow from <IP_DEL_EQUIPO> to any port 22 proto tcp
sudo ufw allow 8443/tcp
sudo ufw enable
```

```bash
# En la víctima
sudo ufw allow from <IP_DEL_EQUIPO> to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw enable
```

## 6. Netdata en la víctima

Instalación oficial:

```bash
wget -O /tmp/netdata-kickstart.sh https://get.netdata.cloud/kickstart.sh
sudo sh /tmp/netdata-kickstart.sh
```

Verificación con túnel SSH desde el equipo de trabajo (recomendado, sin exponer el puerto):

```bash
ssh -L 19999:localhost:19999 ubuntu@<IP_VICTIMA>
# Luego abrir http://localhost:19999 en el navegador
```

Para que el C2 consuma métricas vía API, exponer el 19999 solo a la IP del botnet,
o consumir la API localmente desde la víctima.

## 7. Desplegar el servidor C2 en la instancia

1. Conectarse por SSH y verificar Python: `python3 --version` (Ubuntu 24.04 incluye 3.12).
2. Subir el repositorio (`git clone` o `scp -r botnet ubuntu@<IP_BOTNET>:~`).
3. `cp .env.example .env` y completar:
   - `NETDATA_URL=http://<IP_ELASTICA_VICTIMA>:19999`
   - `C2_SHARED_SECRET` (opcional; si se define, el agente/`.exe` debe enviar el mismo valor).
4. Ejecutar para una prueba rápida: `python3 server/main.py` (el puerto 8443 ya está
   habilitado en `sg-botnet`). Para dejarlo persistente, instalar el servicio de la
   sección 8.
5. Verificar desde otra máquina:
   `python agent/test_agent.py --host <IP_BOTNET> --port 8443 --id zombie-01`
6. Pruebas antes de la exposición:
   `python3 server/tests/run_all.py` y `python3 server/tests/smoke_test.py`

## 8. Servicio persistente del C2 (systemd + tmux)

El repositorio incluye `server/deploy/botnet-c2.service`: arranca el servidor
dentro de una sesión `tmux`, lo reinicia si falla y lo levanta al encender la
instancia (sin ventanas visibles).

```bash
sudo apt install -y tmux
sudo cp server/deploy/botnet-c2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now botnet-c2
sudo systemctl status botnet-c2
```

Ajustar `User` y `WorkingDirectory` en la unidad si el usuario o la ruta del
repositorio difieren de `ubuntu` y `/home/ubuntu/botnet`.

### Operar la consola del C2

```bash
tmux attach -t botnet-c2      # entrar a la consola del C2
```

- **Salir sin detener el C2:** `Ctrl+B`, soltar, luego `D` (detach). Puedes
  cerrar PuTTY: el C2 sigue corriendo.
- **`exit` dentro de la consola:** no apaga el C2; el bucle de persistencia del
  servicio lo reinicia a los 3 s.
- **Apagado real:** `sudo systemctl stop botnet-c2`.
- **Reiniciar (por ejemplo, tras editar `.env`):** `sudo systemctl restart botnet-c2`.
- **Estado:** `sudo systemctl status botnet-c2`.

## Notas de costo

- `t3.micro` es elegible para la capa gratuita (750 h/mes durante 12 meses); `t3.medium` no.
- Las IP elásticas no asociadas tienen costo: mantenerlas asociadas o liberarlas.
- Detener las instancias cuando no se usen y revisar las tarifas vigentes de IP elástica.
