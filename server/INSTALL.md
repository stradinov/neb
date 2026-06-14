# Backend central de la bitácora de relevo — instalación

Guía para montar el **servidor de referencia** del backend central de la bitácora de relevo (Neb).
El central es **opcional**: habilita el relevo cross-dev real (lock atómico cross-máquina + transcript
buscable). Sin central, la bitácora funciona local-only (ver [`../tooling/logbook.md`](../tooling/logbook.md)).

El servidor es **agnóstico al despliegue**: escucha HTTP en `host:puerto` y asume un reverse proxy
que termina TLS. Estos pasos son el contrato mínimo; el despliegue concreto (vhost, systemd de tu
infra) lo ajusta cada adoptante.

> **Privacidad — leer antes de montar.** El central es **opt-in por proyecto**: con `NEB_LOGBOOK_ENDPOINT`
> configurado, un proyecto publica su trabajo al catálogo compartido del equipo **solo si** su `CLAUDE.md`
> trae el marcador `<!-- neb-logbook: central -->` (works con-REQ **y sesiones exploratorias**: su
> transcript, sin `tool_result`, queda buscable por el equipo). Sin el marcador la bitácora queda
> **local-only** (el default; la bitácora local ya cubre el relevo del propio dev). (El opt-in por perfil
> es un follow-up.) Un dev que trabaja solo **no necesita montar el central**.

## Requisitos

- **MariaDB ≥ 10.5** (verificado en 10.5.29). Se usan: `FULLTEXT` InnoDB, `JSON`/`LONGTEXT`,
  `ROW_FORMAT=COMPRESSED` y una **columna generada `STORED` + `UNIQUE`** (`identity_key`).
- **Python 3** + **PyMySQL** (única dependencia: `pip install -r requirements.txt`).

## 1. Base de datos y usuario

```sql
CREATE DATABASE neb_logbook CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'neb_logbook'@'localhost' IDENTIFIED BY '<password-fuerte>';
GRANT SELECT, INSERT, UPDATE, DELETE ON neb_logbook.* TO 'neb_logbook'@'localhost';
FLUSH PRIVILEGES;
```

Aplicar el esquema:

```bash
mysql neb_logbook < schema.sql
```

## 2. Configuración (env)

Copiá `.env.example` a un archivo **no versionado** y poblá. El token y la contraseña **nunca**
se commitean ni viven en `.md`/`personal/`.

```bash
NEB_LOGBOOK_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
```

Variables: `NEB_LOGBOOK_TOKEN`, `NEB_LOGBOOK_DB_{HOST,PORT,USER,PASSWORD,NAME}` (ver `.env.example`).

## 3. Correr el servidor

```bash
pip install -r requirements.txt
python logbook_server.py --host 127.0.0.1 --port 8787
```

Ejemplo de unit systemd (ajustá rutas/usuario):

```ini
[Unit]
Description=Neb logbook central
After=network.target mariadb.service

[Service]
EnvironmentFile=/etc/neb-logbook.env
ExecStart=/usr/bin/python3 /opt/neb/server/logbook_server.py --host 127.0.0.1 --port 8787
Restart=on-failure
User=neb

[Install]
WantedBy=multi-user.target
```

## 4. Exposición

El servidor escucha HTTP en `127.0.0.1:8787`. Elegí una:

- **Tras reverse proxy (recomendado)** — un Apache/nginx ya existente termina TLS y proxea a
  `127.0.0.1:8787`. Ejemplo Apache (vhost/location):

  ```apache
  <Location /neb-logbook>
      ProxyPass        http://127.0.0.1:8787
      ProxyPassReverse http://127.0.0.1:8787
  </Location>
  ```
  El cliente apunta `NEB_LOGBOOK_ENDPOINT=https://tu-host/neb-logbook`.

- **Puerto propio** — exponé `:8787` directamente (idealmente solo dentro de la red del equipo /
  VPN). El servidor no termina TLS por sí mismo.

## 5. Configurar el cliente (cada dev)

En la máquina de cada dev, exportá (como `NEB_HOME`: shell rc o `~/.claude/settings.json` campo `env`):

```bash
export NEB_LOGBOOK_ENDPOINT="https://tu-host/neb-logbook"
export NEB_LOGBOOK_TOKEN="<el mismo token del servidor>"
```

Con eso, el hook `logbook-sync` (ver [`../hooks/README.md`](../hooks/README.md)) publica al central de
forma automática (detached, best-effort), y `/logbook` (search/claim/...) opera contra el central.

## 6. Smoke test

```bash
curl -s http://127.0.0.1:8787/healthz
# {"ok": true}

curl -s -H "Authorization: Bearer $NEB_LOGBOOK_TOKEN" http://127.0.0.1:8787/work
# {"works": []}
```

## Búsqueda (FULLTEXT)

`/search` usa `FULLTEXT` InnoDB sobre `text_plain` con `utf8mb4`. Por default `ft_min_word_len=4`
(palabras de <4 caracteres no se indexan) y aplica la lista de stopwords. Si necesitás indexar
términos cortos, ajustá `ft_min_word_len` en `my.cnf` y reconstruí el índice
(`OPTIMIZE TABLE transcript;`).

## Retención

Un `work` cerrado se **archiva** (`archived_at`), no se borra — el corpus es de auditoría. La purga
es manual e intencional:

```bash
python purge.py --before 2025-01-01           # dry-run (cuenta)
python purge.py --before 2025-01-01 --apply    # ejecuta el DELETE (cascada a event/transcript)
```
