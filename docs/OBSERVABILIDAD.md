# Observabilidad de Contecflow PSA (22-11-2026)

Todo en Docker con un comando, métricas de plataforma y de negocio **por empresa**,
alertas y paneles de Grafana provisionados desde el repositorio. Es la referencia
única de observabilidad, incluida la activación de `/metrics`.

## 1. Arrancar

```bash
./setup.sh docker            # Linux / macOS / Git Bash
setup.bat docker             # Windows
./setup.sh docker demo       # además siembra datos demo (o `clean`: solo admin)
./setup.sh docker-status     # estado de los contenedores y URLs
./setup.sh docker-stop       # para TODO (docker compose down de todos los perfiles, sin -v)
```

Los dos lanzadores llaman a `scripts/docker_stack.py` (solo biblioteca estándar;
usa `.venv` si existe y si no el Python del sistema), así que hacen lo mismo:

1. Comprueba Docker; si el daemon está parado intenta arrancarlo (Docker Desktop,
   `open -ga Docker`, `systemctl start docker`) y espera hasta 3 min.
2. Completa el `.env` **solo con lo que falta**: `POSTGRES_*`, `MINIO_*` (con la
   misma regla que `setup.sh`: si el volumen ya existe se usa el valor histórico
   `contecflow_dev`), `METRICS_AUTH_TOKEN`, `GRAFANA_ADMIN_USER`,
   `GRAFANA_ADMIN_PASSWORD` (generada) y el origen de la web
   (`http://localhost:8080`) en `ALLOWED_ORIGINS`, sin el cual el middleware CSRF
   rechazaría el login con 403. Los secretos se generan una vez y quedan en `.env`;
   no se escriben en ningún fichero del repositorio. Respeta los finales de línea
   del `.env`.
3. Crea los volúmenes persistentes (`contecflow_postgres_data`,
   `contecflow_s3_data`) si faltan. **Nunca los borra ni los recrea**: son
   `external: true` y `docker-stop` no usa `-v`.
4. `docker compose --profile app --profile observability up -d --build`. El
   servicio `migrate` (`alembic upgrade head` + políticas RLS) corre antes que
   la API; si falla, la API no arranca y se enseña su log.
5. Intenta `--profile host-metrics` (node-exporter, cAdvisor) **aparte**: si no
   arrancan (Docker Desktop), avisa y sigue.
6. Espera a que la API esté `healthy` (5 min), comprueba worker, beat, web,
   Prometheus y Alertmanager, y alinea la contraseña del admin de Grafana con el
   `.env` (`grafana cli admin reset-admin-password`), porque Grafana solo aplica
   la variable al crear su base.
7. Si la base no tiene usuarios, avisa de `setup docker demo|clean`.

El modo local de siempre (`demo`, `clean`, `start`, `stop`, `update`,
`docker-clean`) no cambia.

## 2. URLs (todas publicadas solo en 127.0.0.1)

| Servicio | URL por defecto | Variable |
|---|---|---|
| Aplicación (nginx + SPA) | http://localhost:8080 | `WEB_PORT` |
| API (docs) | http://localhost:8080/api/v1/docs | — (la API no publica puerto; entra por nginx) |
| Grafana | http://localhost:3001 | `GRAFANA_PORT`, `GRAFANA_ROOT_URL` |
| Prometheus | http://localhost:9090 | `PROMETHEUS_PORT` |
| Alertmanager | http://localhost:9093 | `ALERTMANAGER_PORT` |

Grafana usa el 3001 porque el 3000 es el de Vite en el modo local.

## 3. Piezas

| Servicio | Perfil | Qué hace |
|---|---|---|
| `api` | app | `/metrics` (Bearer `METRICS_AUTH_TOKEN`); `METRICS_ENABLED=1` forzado en el contenedor |
| `worker` | app | `/metrics` propio en `worker:9808` (red interna), multiproceso para el pool prefork |
| `beat` | app | `/metrics` propio en `beat:9809` (red interna); su `up` es la alarma de beat caído |
| `prometheus` | observability | Recoge todo, evalúa `ops/prometheus/rules/*.yml`, retención configurable |
| `alertmanager` | observability | Reparte alertas por correo y/o webhook (config generada del `.env`) |
| `grafana` | observability | Datasources y 6 dashboards provisionados desde `ops/grafana/` |
| `postgres-exporter`, `redis-exporter` | observability | Salud y saturación de la base y de Redis |
| `node-exporter`, `cadvisor` | host-metrics | Máquina (CPU, memoria, disco) y contenedores |

Ficheros:

```
ops/prometheus/prometheus.yml           objetivos y alerting
ops/prometheus/rules/plataforma.yml     API, Celery, datos, máquina
ops/prometheus/rules/negocio_y_seguridad.yml   SLA, riesgo, IA, logins
ops/alertmanager/generar-config.sh      entrypoint: escribe la config en un tmpfs y arranca
ops/grafana/provisioning/datasources/   Prometheus + Alertmanager (uid fijos)
ops/grafana/provisioning/dashboards/    carpeta «Contecflow», sin edición en la interfaz
ops/grafana/dashboards/*.json           los paneles
ops/grafana/generar_dashboards.py       cómo se escriben los JSON (regenerar tras cambiarlo)
```

### Docker Desktop (Windows / macOS)

- **node-exporter** no monta `/` del anfitrión (en Docker Desktop no es un montaje
  compartido y el contenedor no arrancaría); con `/proc` y `/sys` mide la
  **máquina virtual Linux de Docker**, no Windows. Es la que tiene los límites de
  CPU, memoria y disco que importan a los contenedores.
- **cAdvisor** necesita `privileged`, `/dev/kmsg` y `/var/lib/docker`; en Docker
  Desktop con WSL2 suele funcionar pero algunas versiones no exponen el disco
  por contenedor o no arrancan. Si falla, `setup docker` avisa y el resto sigue;
  los paneles de contenedores quedan vacíos y la alerta informativa
  `ObjetivoDeMetricasCaido` lo señala.
- **No verificado en esta máquina**: la pila de observabilidad se validó con
  `docker compose config` (sintaxis y perfiles); no se ha levantado aquí porque
  Docker Desktop estaba parado.

## 4. Métricas

Convenciones: la etiqueta `empresa` es **siempre** el valor de
`etiqueta_de_empresa()` (`app/core/metricas_empresa.py`); el resto de etiquetas
son de catálogo (estados, prioridades, severidades, módulos, fases, nombres de
tarea, rutas-plantilla, códigos del catálogo de errores).

### 4.1 HTTP (API, en caliente)

| Métrica | Tipo | Etiquetas |
|---|---|---|
| `http_requests_total` | counter | `handler` (plantilla), `method`, `status` (2xx…) |
| `http_request_duration_seconds` | histogram | `handler`, `method` |
| `contecflow_http_requests_inprogress` | gauge | `handler`, `method` |
| `contecflow_http_peticiones_empresa_total` | counter | `empresa`, `estado` (2xx/3xx/4xx/5xx; 401, 403, 404 y 429 aparte) |
| `contecflow_http_duracion_empresa_seconds` | histogram | `empresa` |
| `contecflow_http_errores_total` | counter | `empresa`, `ruta` (plantilla), `estado`, `codigo` (catálogo `app/core/codigos_de_error.py`) |
| `contecflow_abac_denials_total`, `contecflow_external_api_*`, `contecflow_scheduled_job_duration_seconds` | | como antes |

La empresa de la petición la anota la dependencia de autenticación
(`app/core/deps.py`) en `request.state`; las peticiones sin usuario van como
`sin_empresa`. El código de error lo anotan los manejadores de `app/main.py`; si
no hay, se deduce del estado (`no_autenticado`, `prohibido`, `validacion`…). Un
«código» que no sea `[a-z0-9_]` se descarta (nunca texto libre).

### 4.2 Seguridad, IA y negocio en caliente

| Métrica | Etiquetas |
|---|---|
| `contecflow_logins_total` | `empresa` (`desconocida` si el usuario no existe), `resultado` = correcto / fallido / bloqueado |
| `contecflow_ia_peticiones_total` | `empresa`, `modulo`, `resultado` |
| `contecflow_ia_tokens_total` | `empresa`, `modulo`, `sentido` |
| `contecflow_ia_coste_usd_total` | `empresa`, `modulo` |
| `contecflow_ia_presupuesto_agotado_total` | `empresa` |
| `contecflow_tickets_created_total` | `tenant_id` (**ahora la etiqueta acotada**, antes el id crudo), `ticket_type`, `priority`, `source` |
| `contecflow_invoices_created_total` | `tenant_id` (ídem), `status` |

### 4.3 Celery (worker y beat)

| Métrica | Etiquetas |
|---|---|
| `contecflow_celery_tareas_total` | `tarea`, `resultado` (ok / error / reintento / rechazada) |
| `contecflow_celery_tarea_duracion_seconds` | `tarea` |
| `contecflow_celery_tareas_publicadas_total` | `tarea` |
| `contecflow_celery_cola_longitud` | `cola` (la calcula la API con `LLEN` en Redis) |

### 4.4 Negocio por empresa (de la base, con caché)

`app/core/metricas_negocio.py`: un colector que, como mucho una vez cada
`METRICS_BUSINESS_CACHE_SECONDS` (60) por proceso, lanza ~20 consultas agregadas
(`COUNT/SUM … GROUP BY organization_id`) sobre columnas indexadas, con una sesión
de fondo de solo lectura. Cada bloque falla por separado
(`contecflow_negocio_colector_errores_total{bloque}`). En modo multiproceso lo
calcula el worker de uvicorn que atiende el scrape.

| Métrica | Etiquetas | Qué cuenta |
|---|---|---|
| `contecflow_negocio_tickets_abiertos` | empresa, prioridad | no resueltos/cerrados/cancelados |
| `contecflow_negocio_tickets_creados_24h` | empresa, tipo | |
| `contecflow_negocio_tickets_resueltos_24h` | empresa | |
| `contecflow_negocio_sla` | empresa, ambito (tickets/demanda/vulnerabilidades), estado (en_riesgo/incumplido) | elementos abiertos |
| `contecflow_negocio_proyectos` | empresa, estado | vigentes (`is_active`) |
| `contecflow_negocio_horas_imputadas_7d` | empresa | suma de horas |
| `contecflow_negocio_horas_extra_30d` | empresa, estado | suma de horas |
| `contecflow_negocio_ausencias` | empresa, estado (hoy/pendientes) | |
| `contecflow_negocio_demanda_abiertas` | empresa, fase (25 más pobladas; resto `otras`) | |
| `contecflow_negocio_vulnerabilidades_abiertas` | empresa, severidad | hallazgos open/triaged/in_progress |
| `contecflow_negocio_indice_riesgo` | empresa, tipo (bruto/aceptado) | última foto diaria de ámbito `org` |
| `contecflow_negocio_licencias` | empresa, estado | |
| `contecflow_negocio_licencias_puestos` | empresa, tipo (totales/asignados) | |
| `contecflow_negocio_equipos` | empresa, estado | |
| `contecflow_negocio_ia_peticiones_24h` | empresa, modulo, resultado | |
| `contecflow_negocio_ia_tokens_24h` | empresa, modulo, sentido | |
| `contecflow_negocio_ia_coste_usd_24h` | empresa, modulo | |
| `contecflow_negocio_logins_24h` | empresa, resultado | eventos del SOC |
| `contecflow_negocio_usuarios_activos` | empresa, ventana (15m/24h/30d) | usuarios distintos |
| `contecflow_negocio_colector_duracion_seconds`, `…_ultimo_calculo_timestamp_seconds` | — | salud del colector |

Base de pruebas: los recuentos se validan en `tests/test_metricas_observabilidad.py`.
Se comprobó además que todas las consultas corren sin error contra la SQLite de
desarrollo (vacía); contra Postgres no se ha ejecutado aquí.

## 5. Cardinalidad

- `METRICS_TENANT_MAX` (50): solo las 50 primeras empresas por fecha de alta
  tienen etiqueta propia; el resto suma en `otras`. Orden estable entre procesos.
- `METRICS_TENANT_LABEL`: `slug` (defecto) o `id`.
- Fases de demanda y módulos de IA: 25 valores como mucho; el resto `otras`/`otros`.
- Rutas: siempre la plantilla (`/api/v1/tickets/{ticket_id}`), nunca la URL.
- Estimación: HTTP por empresa ≈ 50 × 8 estados + 50 histogramas; errores solo
  para lo que ocurre (dispersos); negocio ≈ 50 × (5–10) por familia.
- El mapa empresa → etiqueta se cachea 5 min por proceso; una empresa nueva
  fuerza un refresco como mucho cada 30 s.

## 6. Dashboards (carpeta «Contecflow» en Grafana)

| Dashboard | Contenido |
|---|---|
| Plataforma | API (tasa, 5xx, p50/p95/p99, rutas lentas), APIs externas, Celery (cola, tareas, duración), PostgreSQL, Redis, contenedores, máquina, objetivos |
| Negocio por empresa | variable **Empresa**; tickets, proyectos, horas, horas extra, ausencias, demanda por fase, licencias, equipos, usuarios activos |
| Seguridad | logins por resultado y empresa, 401/403/429, denegaciones ABAC, códigos de error y rutas con más errores |
| IA | llamadas, tokens, coste por empresa y módulo, errores, tope diario agotado |
| Service desk y SLA | SLA en riesgo/incumplido por ámbito y empresa, tickets abiertos/creados/resueltos |
| Riesgo y vulnerabilidades | críticas/altas abiertas, SLA de remediación, índice de riesgo |

Se provisionan con `allowUiUpdates: false`: para cambiarlos se edita
`ops/grafana/generar_dashboards.py`, se ejecuta
`python ops/grafana/generar_dashboards.py ops/grafana/dashboards` y se commitea.

## 7. Alertas

Reglas en `ops/prometheus/rules/`. Severidades: `critical`, `warning`, `info`.

| Alerta | Condición |
|---|---|
| ApiCaida | `up{job="contecflow-api"} == 0` 2 min (también si responde 401: token) |
| TasaDeErrores5xxAlta | > 5 % de 5xx durante 5 min (con tráfico mínimo) |
| LatenciaP95Alta | p95 > 2 s durante 10 min |
| CeleryWorkerCaido / CeleryBeatCaido | su `/metrics` no responde 3 / 5 min |
| ColaDeCeleryAtascada | cola > 0 y ninguna tarea termina en 10 min |
| ColaDeCeleryLarga / TareasDeCeleryFallando | cola > 500 15 min / > 3 fallos de una tarea en 30 min |
| PostgresCaido / RedisCaido | exporter sin conexión 1 min |
| PostgresConexionesAlLimite / RedisMemoriaAlLimite | > 80 % de conexiones / > 90 % de maxmemory |
| DiscoCasiLleno / MemoriaCasiAgotada / ContenedorCercaDeSuLimiteDeMemoria | < 10 % libre / > 90 % del límite |
| IaPresupuestoAgotado / IaErroresAltos | tope diario alcanzado / > 20 % de errores 15 min |
| SlaIncumplidoNuevo / SlaEnRiesgo | más incumplidos en 30 min / en riesgo 30 min |
| VulnerabilidadesCriticasAbiertas / IndiceDeRiesgoAlto | críticas abiertas 1 h / índice ≥ 70 |
| LoginsFallidosEnRafaga / Respuestas401o403Altas | > 20 fallidos en 10 min / > 1 por segundo |
| ColectorDeNegocioConErrores / ObjetivoDeMetricasCaido | informativas |

**Receptores** (`.env`, todos opcionales): `ALERT_WEBHOOK_URL`, y para correo
`ALERT_EMAIL_TO`, `ALERT_EMAIL_FROM`, `ALERT_SMTP_HOST` (host:puerto),
`ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD`, `ALERT_SMTP_REQUIRE_TLS`. Sin ninguno,
las alertas solo se ven en Alertmanager y Grafana. La config se genera al
arrancar en un tmpfs (no queda en disco ni en el volumen) con los valores
escapados. Agrupación por `alertname` + `empresa`; repetición cada 4 h (24 h las
`info`); con la API o la base caídas se inhiben sus síntomas.

## 8. GRC

- **`/metrics` protegido**: Bearer `METRICS_AUTH_TOKEN` (comparación en tiempo
  constante; se puede rotar desde Admin → Configuración sin redesplegar — si el
  de la base y el del `.env` difieren, Prometheus recibe 401 y salta `ApiCaida`).
  Fuera de development/test sin token responde 401. nginx no publica `/metrics`
  y la API no publica puerto. El token llega a Prometheus por un tmpfs, no por
  fichero del repositorio. Los `/metrics` del worker y del beat no llevan token:
  solo existen dentro de la red de compose (sin puerto publicado).
- **Sin datos personales en etiquetas**: solo empresa (slug o id de la
  organización, persona jurídica), catálogos y rutas-plantilla. Nunca ids,
  nombres o correos de usuarios, IPs, URLs reales ni texto libre. Lo vigila
  `tests/test_metricas_observabilidad.py::test_metrics_no_expone_datos_personales`.
  Si el slug de una empresa identificara a una persona física (autónomo), usar
  `METRICS_TENANT_LABEL=id`.
- **Retención**: Prometheus `PROMETHEUS_RETENTION` (15d) y
  `PROMETHEUS_RETENTION_SIZE` (5GB); Alertmanager `ALERTMANAGER_RETENTION`
  (120h). Los volúmenes de Prometheus, Alertmanager y Grafana son regenerables.
- **Grafana**: sin acceso anónimo, sin registro, sin creación de organizaciones,
  sin snapshots externos, sin Gravatar ni telemetría, cookie `SameSite=strict`,
  basic auth de API apagada, `/metrics` de Grafana apagado (no tiene
  autenticación). El contenedor no arranca sin contraseña o con «admin».
- **Auditoría**: los inicios de sesión y cambios en Grafana quedan en su log
  (`docker compose logs grafana`); los paneles y datasources son ficheros del
  repositorio (el historial de git es su auditoría) y no se pueden guardar desde
  la interfaz. Las lecturas del colector de negocio son agregados de solo
  lectura entre empresas, con una sesión de fondo (sin contexto de empresa, igual
  que los trabajos programados); no se registran en `audit_logs` porque no
  acceden a registros individuales.
- **Privilegios**: Prometheus, Alertmanager y Grafana corren con el usuario sin
  privilegios de sus imágenes; cAdvisor es `privileged` (necesario para leer
  cgroups) y por eso va en un perfil aparte y sin puerto publicado.
  `postgres-exporter` usa el usuario dueño de la base (como antes); para
  producción conviene un rol de solo lectura con `pg_monitor`.

## 9. Variables

`METRICS_TENANT_LABEL`, `METRICS_TENANT_MAX`, `METRICS_BUSINESS_ENABLED`,
`METRICS_BUSINESS_CACHE_SECONDS`, `CELERY_METRICS_PORT` (Settings) y
`GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_PORT`,
`GRAFANA_ROOT_URL`, `ALERTMANAGER_PORT`, `PROMETHEUS_PORT`,
`PROMETHEUS_RETENTION`, `PROMETHEUS_RETENTION_SIZE`, `ALERTMANAGER_RETENTION`,
`ALERT_*` (compose). Todas documentadas en `.env.example`.
