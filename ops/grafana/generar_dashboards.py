"""Genera los dashboards de Grafana de Contecflow (ops/grafana/dashboards/*.json).

Los JSON son la fuente que Grafana provisiona; este script es como se escriben,
para que los seis tableros compartan estilo, datasource y variable `empresa`.
Uso (desde la raíz del repositorio):

    python ops/grafana/generar_dashboards.py ops/grafana/dashboards

Métricas y significado: docs/OBSERVABILIDAD.md.
"""
import json
import pathlib
import sys

DEST = pathlib.Path(sys.argv[1])
DS = {"type": "prometheus", "uid": "contecflow-prometheus"}
E = 'empresa=~"$empresa"'


class Tablero:
    def __init__(self, uid, titulo, descripcion, tags, con_empresa=False):
        self.uid, self.titulo, self.descripcion, self.tags = uid, titulo, descripcion, tags
        self.con_empresa = con_empresa
        self.paneles = []
        self.y = 0
        self.x = 0
        self.alto_fila = 0
        self.id = 1

    def fila(self, titulo):
        self._salto()
        self.paneles.append({"type": "row", "title": titulo, "id": self.id, "collapsed": False,
                             "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []})
        self.id += 1
        self.y += 1

    def _salto(self):
        if self.x:
            self.y += self.alto_fila
            self.x = 0
            self.alto_fila = 0

    def panel(self, tipo, titulo, objetivos, w=12, h=8, unidad="short", descripcion="", extra=None,
              apilado=False, umbrales=None):
        if self.x + w > 24:
            self._salto()
        p = {
            "type": tipo, "title": titulo, "id": self.id, "datasource": DS, "description": descripcion,
            "gridPos": {"h": h, "w": w, "x": self.x, "y": self.y},
            "targets": [
                {"datasource": DS, "refId": chr(65 + i), "expr": expr, "legendFormat": leyenda,
                 **({"instant": True, "format": "table"} if tipo in ("table",) else {})}
                for i, (expr, leyenda) in enumerate(objetivos)
            ],
            "fieldConfig": {"defaults": {"unit": unidad}, "overrides": []},
            "options": {},
        }
        if umbrales:
            p["fieldConfig"]["defaults"]["thresholds"] = {
                "mode": "absolute",
                "steps": [{"color": "green", "value": None}] + [{"color": c, "value": v} for v, c in umbrales]}
            p["fieldConfig"]["defaults"]["color"] = {"mode": "thresholds"}
        if tipo == "timeseries":
            p["fieldConfig"]["defaults"]["custom"] = {
                "drawStyle": "line", "lineWidth": 1, "fillOpacity": 15 if apilado else 5,
                "stacking": {"mode": "normal" if apilado else "none", "group": "A"}, "showPoints": "never"}
            p["options"] = {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                            "tooltip": {"mode": "multi", "sort": "desc"}}
        elif tipo == "stat":
            p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                            "colorMode": "value", "graphMode": "area", "textMode": "auto"}
        elif tipo == "bargauge":
            p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                            "orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True}
        elif tipo == "table":
            p["options"] = {"showHeader": True, "cellHeight": "sm"}
            p["transformations"] = [{"id": "organize", "options": {"excludeByName": {"Time": True}}}]
        if extra:
            p.update(extra)
        self.paneles.append(p)
        self.id += 1
        self.x += w
        self.alto_fila = max(self.alto_fila, h)

    def json(self):
        variables = []
        if self.con_empresa:
            variables.append({
                "type": "query", "name": "empresa", "label": "Empresa", "datasource": DS,
                "query": {"query": "label_values(empresa)", "refId": "empresa"},
                "definition": "label_values(empresa)", "refresh": 2, "includeAll": True, "multi": True,
                "allValue": ".*", "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
                "sort": 1, "regex": "", "hide": 0,
                "description": "Slug acotado de la organización (las que pasan de METRICS_TENANT_MAX van en «otras»).",
            })
        return {
            "uid": self.uid, "title": self.titulo, "description": self.descripcion, "tags": self.tags,
            "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": False,
            "graphTooltip": 1, "refresh": "1m", "time": {"from": "now-6h", "to": "now"},
            "templating": {"list": variables}, "annotations": {"list": []},
            "links": [{"title": "Contecflow", "type": "dashboards", "tags": ["contecflow"], "asDropdown": True}],
            "panels": self.paneles,
        }


def plataforma():
    t = Tablero("contecflow-plataforma", "Contecflow · Plataforma",
                "API, worker y beat de Celery, PostgreSQL, Redis, contenedores y máquina.",
                ["contecflow", "plataforma"])
    t.fila("API")
    t.panel("stat", "API arriba", [('max(up{job="contecflow-api"})', "")], w=4, h=4,
            umbrales=[(0, "red"), (1, "green")], extra={"fieldConfig": {"defaults": {"unit": "short", "mappings": [
                {"type": "value", "options": {"0": {"text": "CAÍDA", "color": "red"},
                                              "1": {"text": "OK", "color": "green"}}}]}, "overrides": []}})
    t.panel("stat", "Peticiones/s", [('sum(rate(http_requests_total{job="contecflow-api"}[5m]))', "")],
            w=5, h=4, unidad="reqps")
    t.panel("stat", "% 5xx (5 min)", [(
        'sum(rate(http_requests_total{job="contecflow-api",status="5xx"}[5m])) / '
        'clamp_min(sum(rate(http_requests_total{job="contecflow-api"}[5m])), 1e-9)', "")],
        w=5, h=4, unidad="percentunit", umbrales=[(0.01, "orange"), (0.05, "red")])
    t.panel("stat", "Latencia p95", [(
        'histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="contecflow-api"}[5m])))',
        "")], w=5, h=4, unidad="s", umbrales=[(1, "orange"), (2, "red")])
    t.panel("stat", "En curso", [('sum(contecflow_http_requests_inprogress)', "")], w=5, h=4)
    t.panel("timeseries", "Peticiones por estado", [
        ('sum by (status) (rate(http_requests_total{job="contecflow-api"}[5m]))', "{{status}}")],
        unidad="reqps", apilado=True)
    t.panel("timeseries", "Latencia p50 / p95 / p99", [
        ('histogram_quantile(0.5, sum by (le) (rate(http_request_duration_seconds_bucket{job="contecflow-api"}[5m])))', "p50"),
        ('histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="contecflow-api"}[5m])))', "p95"),
        ('histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket{job="contecflow-api"}[5m])))', "p99")],
        unidad="s")
    t.panel("table", "Rutas más lentas (p95, 15 min)", [(
        'topk(15, histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket{job="contecflow-api"}[15m]))))',
        "")], w=12, h=9, unidad="s")
    t.panel("table", "Rutas con más 5xx (1 h)", [(
        'topk(15, sum by (handler) (increase(http_requests_total{job="contecflow-api",status="5xx"}[1h])) > 0)', "")],
        w=12, h=9)
    t.panel("timeseries", "Llamadas a APIs externas por proveedor y resultado", [
        ('sum by (provider, outcome) (rate(contecflow_external_api_calls_total[5m]))', "{{provider}} {{outcome}}")],
        unidad="reqps")
    t.panel("timeseries", "Latencia p95 de APIs externas", [(
        'histogram_quantile(0.95, sum by (le, provider) (rate(contecflow_external_api_latency_seconds_bucket[5m])))',
        "{{provider}}")], unidad="s")

    t.fila("Worker y beat (Celery)")
    t.panel("stat", "Worker", [('max(up{job="celery-worker"})', "")], w=4, h=4, umbrales=[(0, "red"), (1, "green")])
    t.panel("stat", "Beat", [('max(up{job="celery-beat"})', "")], w=4, h=4, umbrales=[(0, "red"), (1, "green")])
    t.panel("stat", "Cola de Celery", [('max(contecflow_celery_cola_longitud)', "")], w=4, h=4,
            umbrales=[(100, "orange"), (500, "red")])
    t.panel("stat", "Tareas OK (1 h)", [('sum(increase(contecflow_celery_tareas_total{resultado="ok"}[1h]))', "")], w=6, h=4)
    t.panel("stat", "Tareas con error (1 h)", [('sum(increase(contecflow_celery_tareas_total{resultado="error"}[1h]))', "")],
            w=6, h=4, umbrales=[(1, "orange"), (10, "red")])
    t.panel("timeseries", "Tareas terminadas por resultado", [
        ('sum by (resultado) (rate(contecflow_celery_tareas_total[5m]))', "{{resultado}}")], unidad="ops", apilado=True)
    t.panel("timeseries", "Duración p95 por tarea", [(
        'histogram_quantile(0.95, sum by (le, tarea) (rate(contecflow_celery_tarea_duracion_seconds_bucket[15m])))',
        "{{tarea}}")], unidad="s")
    t.panel("timeseries", "Longitud de la cola", [('contecflow_celery_cola_longitud', "{{cola}}")])
    t.panel("timeseries", "Tareas publicadas (beat y API)", [
        ('sum by (tarea) (rate(contecflow_celery_tareas_publicadas_total[15m]))', "{{tarea}}")], unidad="ops")

    t.fila("PostgreSQL y Redis")
    t.panel("stat", "PostgreSQL", [('max(pg_up)', "")], w=4, h=4, umbrales=[(0, "red"), (1, "green")])
    t.panel("stat", "Conexiones / máximo", [(
        'sum(pg_stat_activity_count) / clamp_min(max(pg_settings_max_connections), 1)', "")], w=5, h=4,
        unidad="percentunit", umbrales=[(0.6, "orange"), (0.8, "red")])
    t.panel("stat", "Tamaño de la base", [('sum(pg_database_size_bytes)', "")], w=5, h=4, unidad="bytes")
    t.panel("stat", "Redis", [('max(redis_up)', "")], w=4, h=4, umbrales=[(0, "red"), (1, "green")])
    t.panel("stat", "Memoria Redis / maxmemory", [(
        'max(redis_memory_used_bytes) / clamp_min(max(redis_memory_max_bytes), 1)', "")], w=6, h=4,
        unidad="percentunit", umbrales=[(0.75, "orange"), (0.9, "red")])
    t.panel("timeseries", "Conexiones PostgreSQL por estado", [
        ('sum by (state) (pg_stat_activity_count)', "{{state}}")], apilado=True)
    t.panel("timeseries", "Transacciones/s (commit y rollback)", [
        ('sum(rate(pg_stat_database_xact_commit[5m]))', "commit"),
        ('sum(rate(pg_stat_database_xact_rollback[5m]))', "rollback")], unidad="ops")
    t.panel("timeseries", "Redis: memoria y clientes", [
        ('redis_memory_used_bytes', "memoria"), ], unidad="bytes")
    t.panel("timeseries", "Redis: comandos/s y clientes", [
        ('rate(redis_commands_processed_total[5m])', "comandos/s"), ('redis_connected_clients', "clientes")])

    t.fila("Contenedores (cAdvisor) y máquina (node-exporter)")
    t.panel("timeseries", "CPU por contenedor", [(
        'sum by (name) (rate(container_cpu_usage_seconds_total{name=~"contecflow-.*"}[5m]))', "{{name}}")],
        unidad="percentunit", descripcion="Fracción de un núcleo. Sin cAdvisor (Docker Desktop) sale vacío.")
    t.panel("timeseries", "Memoria por contenedor", [(
        'sum by (name) (container_memory_working_set_bytes{name=~"contecflow-.*"})', "{{name}}")], unidad="bytes")
    t.panel("stat", "CPU de la máquina", [(
        '1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))', "")], w=8, h=4, unidad="percentunit",
        umbrales=[(0.7, "orange"), (0.9, "red")],
        descripcion="En Docker Desktop: la máquina virtual de Docker, no el Windows anfitrión.")
    t.panel("stat", "Memoria usada", [(
        '1 - avg(node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)', "")], w=8, h=4,
        unidad="percentunit", umbrales=[(0.8, "orange"), (0.9, "red")])
    t.panel("stat", "Disco usado (máx.)", [(
        'max(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs|ramfs"} / '
        'node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs|ramfs"})', "")], w=8, h=4,
        unidad="percentunit", umbrales=[(0.8, "orange"), (0.9, "red")])
    t.panel("table", "Objetivos de Prometheus", [('up', "")], w=24, h=8)
    return t


def negocio():
    t = Tablero("contecflow-negocio", "Contecflow · Negocio por empresa",
                "Tickets, proyectos, horas, ausencias, demanda, licencias y equipos, usuarios activos. "
                "Datos de la base, recalculados cada METRICS_BUSINESS_CACHE_SECONDS.",
                ["contecflow", "negocio"], con_empresa=True)
    t.fila("Resumen")
    t.panel("stat", "Tickets abiertos", [(f'sum(contecflow_negocio_tickets_abiertos{{{E}}})', "")], w=4, h=4)
    t.panel("stat", "Tickets creados 24 h", [(f'sum(contecflow_negocio_tickets_creados_24h{{{E}}})', "")], w=4, h=4)
    t.panel("stat", "Tickets resueltos 24 h", [(f'sum(contecflow_negocio_tickets_resueltos_24h{{{E}}})', "")], w=4, h=4)
    t.panel("stat", "Proyectos activos", [(f'sum(contecflow_negocio_proyectos{{{E},estado="active"}})', "")], w=4, h=4)
    t.panel("stat", "Horas imputadas 7 d", [(f'sum(contecflow_negocio_horas_imputadas_7d{{{E}}})', "")], w=4, h=4, unidad="h")
    t.panel("stat", "Usuarios activos (15 min)", [(f'sum(contecflow_negocio_usuarios_activos{{{E},ventana="15m"}})', "")], w=4, h=4)

    t.fila("Service desk")
    t.panel("bargauge", "Tickets abiertos por empresa", [(
        f'sum by (empresa) (contecflow_negocio_tickets_abiertos{{{E}}})', "{{empresa}}")])
    t.panel("timeseries", "Tickets abiertos por prioridad", [(
        f'sum by (prioridad) (contecflow_negocio_tickets_abiertos{{{E}}})', "{{prioridad}}")], apilado=True)
    t.panel("timeseries", "Creados vs resueltos (ventana de 24 h)", [
        (f'sum(contecflow_negocio_tickets_creados_24h{{{E}}})', "creados"),
        (f'sum(contecflow_negocio_tickets_resueltos_24h{{{E}}})', "resueltos")])
    t.panel("timeseries", "Tickets creados (en caliente) por tipo", [(
        'sum by (ticket_type) (rate(contecflow_tickets_created_total{tenant_id=~"$empresa"}[15m]))', "{{ticket_type}}")],
        unidad="ops")

    t.fila("Proyectos y horas")
    t.panel("bargauge", "Proyectos por estado", [(
        f'sum by (estado) (contecflow_negocio_proyectos{{{E}}})', "{{estado}}")])
    t.panel("bargauge", "Horas imputadas 7 d por empresa", [(
        f'sum by (empresa) (contecflow_negocio_horas_imputadas_7d{{{E}}})', "{{empresa}}")], unidad="h")
    t.panel("timeseries", "Horas extra 30 d por estado", [(
        f'sum by (estado) (contecflow_negocio_horas_extra_30d{{{E}}})', "{{estado}}")], unidad="h", apilado=True)
    t.panel("timeseries", "Ausencias: hoy y pendientes de aprobar", [(
        f'sum by (estado) (contecflow_negocio_ausencias{{{E}}})', "{{estado}}")])

    t.fila("Demanda")
    t.panel("bargauge", "Solicitudes abiertas por fase", [(
        f'sum by (fase) (contecflow_negocio_demanda_abiertas{{{E}}})', "{{fase}}")], w=24)

    t.fila("Licencias y equipos")
    t.panel("bargauge", "Licencias por estado", [(f'sum by (estado) (contecflow_negocio_licencias{{{E}}})', "{{estado}}")], w=8)
    t.panel("stat", "Puestos asignados / contratados", [(
        f'sum(contecflow_negocio_licencias_puestos{{{E},tipo="asignados"}}) / '
        f'clamp_min(sum(contecflow_negocio_licencias_puestos{{{E},tipo="totales"}}), 1)', "")], w=8,
        unidad="percentunit", umbrales=[(0.9, "orange"), (1.0, "red")])
    t.panel("bargauge", "Equipos por estado", [(f'sum by (estado) (contecflow_negocio_equipos{{{E}}})', "{{estado}}")], w=8)

    t.fila("Usuarios")
    t.panel("timeseries", "Usuarios activos por ventana", [(
        f'sum by (ventana) (contecflow_negocio_usuarios_activos{{{E}}})', "{{ventana}}")])
    t.panel("table", "Usuarios activos por empresa (30 d)", [(
        f'sum by (empresa) (contecflow_negocio_usuarios_activos{{{E},ventana="30d"}})', "")])
    return t


def seguridad():
    t = Tablero("contecflow-seguridad", "Contecflow · Seguridad",
                "Logins, 401/403, errores por código del catálogo y denegaciones ABAC. Sin datos personales: "
                "todo agregado por empresa.", ["contecflow", "seguridad"], con_empresa=True)
    t.fila("Accesos")
    t.panel("stat", "Logins correctos (1 h)", [(f'sum(increase(contecflow_logins_total{{{E},resultado="correcto"}}[1h]))', "")], w=6, h=4)
    t.panel("stat", "Logins fallidos (1 h)", [(f'sum(increase(contecflow_logins_total{{resultado="fallido"}}[1h]))', "")],
            w=6, h=4, umbrales=[(10, "orange"), (50, "red")],
            descripcion="Incluye intentos contra usuarios inexistentes (empresa «desconocida»).")
    t.panel("stat", "Logins bloqueados (1 h)", [(f'sum(increase(contecflow_logins_total{{resultado="bloqueado"}}[1h]))', "")],
            w=6, h=4, umbrales=[(1, "orange"), (10, "red")])
    t.panel("stat", "Fallidos según el SOC (24 h)", [(f'sum(contecflow_negocio_logins_24h{{{E},resultado="fallido"}})', "")], w=6, h=4)
    t.panel("timeseries", "Logins por resultado", [(
        'sum by (resultado) (rate(contecflow_logins_total[5m]))', "{{resultado}}")], unidad="ops")
    t.panel("timeseries", "Logins fallidos por empresa", [(
        'sum by (empresa) (rate(contecflow_logins_total{resultado=~"fallido|bloqueado"}[5m]))', "{{empresa}}")], unidad="ops")

    t.fila("Respuestas 401 / 403 / 429")
    t.panel("timeseries", "401, 403 y 429 por empresa", [(
        f'sum by (empresa, estado) (rate(contecflow_http_peticiones_empresa_total{{{E},estado=~"401|403|429"}}[5m]))',
        "{{empresa}} {{estado}}")], unidad="reqps")
    t.panel("timeseries", "Denegaciones ABAC por recurso", [(
        'sum by (resource_type, action) (rate(contecflow_abac_denials_total[5m]))', "{{resource_type}} {{action}}")],
        unidad="ops")

    t.fila("Errores")
    t.panel("table", "Códigos de error más frecuentes (1 h)", [(
        f'topk(20, sum by (codigo, estado) (increase(contecflow_http_errores_total{{{E}}}[1h])) > 0)', "")], h=10)
    t.panel("table", "Rutas con más errores (1 h)", [(
        f'topk(20, sum by (ruta, estado) (increase(contecflow_http_errores_total{{{E}}}[1h])) > 0)', "")], h=10)
    t.panel("timeseries", "Errores por estado", [(
        f'sum by (estado) (rate(contecflow_http_errores_total{{{E}}}[5m]))', "{{estado}}")], unidad="ops", w=24)
    return t


def ia():
    t = Tablero("contecflow-ia", "Contecflow · IA",
                "Uso, tokens, coste estimado y errores de IA por empresa y módulo.", ["contecflow", "ia"],
                con_empresa=True)
    t.fila("Resumen (últimas 24 h, de la base)")
    t.panel("stat", "Llamadas", [(f'sum(contecflow_negocio_ia_peticiones_24h{{{E}}})', "")], w=6, h=4)
    t.panel("stat", "Coste USD", [(f'sum(contecflow_negocio_ia_coste_usd_24h{{{E}}})', "")], w=6, h=4, unidad="currencyUSD")
    t.panel("stat", "Tokens", [(f'sum(contecflow_negocio_ia_tokens_24h{{{E}}})', "")], w=6, h=4)
    t.panel("stat", "% con error", [(
        f'sum(contecflow_negocio_ia_peticiones_24h{{{E},resultado="error"}}) / '
        f'clamp_min(sum(contecflow_negocio_ia_peticiones_24h{{{E}}}), 1)', "")], w=6, h=4, unidad="percentunit",
        umbrales=[(0.05, "orange"), (0.2, "red")])
    t.fila("Por empresa y módulo")
    t.panel("bargauge", "Coste 24 h por empresa", [(
        f'sum by (empresa) (contecflow_negocio_ia_coste_usd_24h{{{E}}})', "{{empresa}}")], unidad="currencyUSD")
    t.panel("bargauge", "Coste 24 h por módulo", [(
        f'sum by (modulo) (contecflow_negocio_ia_coste_usd_24h{{{E}}})', "{{modulo}}")], unidad="currencyUSD")
    t.panel("timeseries", "Llamadas/s por módulo (en caliente)", [(
        f'sum by (modulo) (rate(contecflow_ia_peticiones_total{{{E}}}[5m]))', "{{modulo}}")], unidad="ops")
    t.panel("timeseries", "Coste USD/h por empresa (en caliente)", [(
        f'sum by (empresa) (rate(contecflow_ia_coste_usd_total{{{E}}}[15m])) * 3600', "{{empresa}}")], unidad="currencyUSD")
    t.panel("timeseries", "Tokens/s por sentido", [(
        f'sum by (sentido) (rate(contecflow_ia_tokens_total{{{E}}}[5m]))', "{{sentido}}")])
    t.panel("timeseries", "Errores de IA por empresa", [(
        f'sum by (empresa) (rate(contecflow_ia_peticiones_total{{{E},resultado="error"}}[5m]))', "{{empresa}}")], unidad="ops")
    t.panel("timeseries", "Tope diario agotado (llamadas cortadas)", [(
        f'sum by (empresa) (increase(contecflow_ia_presupuesto_agotado_total{{{E}}}[15m]))', "{{empresa}}")], w=24)
    return t


def sla():
    t = Tablero("contecflow-service-desk", "Contecflow · Service desk y SLA",
                "Tickets, SLA en riesgo e incumplido (tickets, demanda y vulnerabilidades) por empresa.",
                ["contecflow", "service-desk", "sla"], con_empresa=True)
    t.fila("SLA")
    t.panel("stat", "SLA incumplido (tickets)", [(f'sum(contecflow_negocio_sla{{{E},ambito="tickets",estado="incumplido"}})', "")],
            w=6, h=4, umbrales=[(1, "red")])
    t.panel("stat", "SLA en riesgo (tickets)", [(f'sum(contecflow_negocio_sla{{{E},ambito="tickets",estado="en_riesgo"}})', "")],
            w=6, h=4, umbrales=[(1, "orange")])
    t.panel("stat", "SLA incumplido (demanda)", [(f'sum(contecflow_negocio_sla{{{E},ambito="demanda",estado="incumplido"}})', "")],
            w=6, h=4, umbrales=[(1, "red")])
    t.panel("stat", "SLA incumplido (vulnerabilidades)", [(
        f'sum(contecflow_negocio_sla{{{E},ambito="vulnerabilidades",estado="incumplido"}})', "")], w=6, h=4, umbrales=[(1, "red")])
    t.panel("timeseries", "SLA por ámbito y estado", [(
        f'sum by (ambito, estado) (contecflow_negocio_sla{{{E}}})', "{{ambito}} {{estado}}")])
    t.panel("bargauge", "SLA incumplido por empresa", [(
        f'sum by (empresa) (contecflow_negocio_sla{{{E},estado="incumplido"}})', "{{empresa}}")])
    t.fila("Tickets")
    t.panel("timeseries", "Abiertos por prioridad", [(
        f'sum by (prioridad) (contecflow_negocio_tickets_abiertos{{{E}}})', "{{prioridad}}")], apilado=True)
    t.panel("timeseries", "Creados 24 h por tipo", [(
        f'sum by (tipo) (contecflow_negocio_tickets_creados_24h{{{E}}})', "{{tipo}}")], apilado=True)
    t.panel("timeseries", "Creados (en caliente) por prioridad y canal", [(
        'sum by (priority, source) (rate(contecflow_tickets_created_total{tenant_id=~"$empresa"}[15m]))',
        "{{priority}} {{source}}")], unidad="ops")
    t.panel("timeseries", "Resueltos 24 h por empresa", [(
        f'sum by (empresa) (contecflow_negocio_tickets_resueltos_24h{{{E}}})', "{{empresa}}")])
    return t


def riesgo():
    t = Tablero("contecflow-riesgo", "Contecflow · Riesgo y vulnerabilidades",
                "Hallazgos de vulnerabilidad abiertos, críticas, SLA de remediación e índice de riesgo por empresa.",
                ["contecflow", "riesgo", "vulnerabilidades"], con_empresa=True)
    t.panel("stat", "Críticas abiertas", [(f'sum(contecflow_negocio_vulnerabilidades_abiertas{{{E},severidad="critical"}})', "")],
            w=6, h=4, umbrales=[(1, "red")])
    t.panel("stat", "Altas abiertas", [(f'sum(contecflow_negocio_vulnerabilidades_abiertas{{{E},severidad="high"}})', "")],
            w=6, h=4, umbrales=[(1, "orange")])
    t.panel("stat", "SLA de remediación vencido", [(
        f'sum(contecflow_negocio_sla{{{E},ambito="vulnerabilidades",estado="incumplido"}})', "")], w=6, h=4, umbrales=[(1, "red")])
    t.panel("stat", "Índice de riesgo (peor)", [(f'max(contecflow_negocio_indice_riesgo{{{E},tipo="bruto"}})', "")],
            w=6, h=4, umbrales=[(40, "orange"), (70, "red")])
    t.panel("timeseries", "Abiertas por severidad", [(
        f'sum by (severidad) (contecflow_negocio_vulnerabilidades_abiertas{{{E}}})', "{{severidad}}")], apilado=True)
    t.panel("bargauge", "Críticas por empresa", [(
        f'sum by (empresa) (contecflow_negocio_vulnerabilidades_abiertas{{{E},severidad="critical"}})', "{{empresa}}")])
    t.panel("timeseries", "Índice de riesgo (bruto y aceptado)", [(
        f'contecflow_negocio_indice_riesgo{{{E}}}', "{{empresa}} {{tipo}}")])
    t.panel("timeseries", "SLA de remediación (en riesgo / vencido)", [(
        f'sum by (estado) (contecflow_negocio_sla{{{E},ambito="vulnerabilidades"}})', "{{estado}}")])
    return t


DEST.mkdir(parents=True, exist_ok=True)
for fabrica, fichero in ((plataforma, "plataforma.json"), (negocio, "negocio-por-empresa.json"),
                         (seguridad, "seguridad.json"), (ia, "ia.json"), (sla, "service-desk-sla.json"),
                         (riesgo, "riesgo-vulnerabilidades.json")):
    t = fabrica()
    (DEST / fichero).write_text(json.dumps(t.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(fichero, len(t.paneles), "paneles")
