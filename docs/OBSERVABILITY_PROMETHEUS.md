# Observability — Prometheus

Contecflow PSA exposes a Prometheus-compatible `/metrics` endpoint with HTTP RED
metrics, business-domain counters, scheduled-job durations, ABAC denials and
outbound API latency. This doc covers activation, scraping, alerting and the
Grafana dashboard.

## 1. Activation

Set these environment variables on the API service:

```bash
METRICS_ENABLED=1
METRICS_AUTH_TOKEN=<a-long-random-secret>            # optional but recommended
PROMETHEUS_MULTIPROC_DIR=/tmp/prom_multiproc          # required for N>1 workers
```

When `METRICS_ENABLED=0` (default) the endpoint is not registered at all and the
instrumentation middleware is not installed — zero overhead.

If `PROMETHEUS_MULTIPROC_DIR` is set, the directory must exist and be writable
by every worker process. Add this to your Dockerfile:

```dockerfile
RUN mkdir -p /tmp/prom_multiproc && chmod 1777 /tmp/prom_multiproc
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prom_multiproc
```

## 2. Exposed metrics

### HTTP (RED) — emitted automatically by the instrumentator

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | counter | `handler`, `method`, `status` |
| `http_request_duration_seconds` | histogram | `handler`, `method` |
| `contecflow_http_requests_inprogress` | gauge | `handler`, `method` |

Paths excluded from instrumentation: `/health`, `/ready`, `/metrics`,
`/favicon.ico`, `/static/*`, `/api/v1/docs*`, `/api/v1/openapi.json`.

### Business-domain — emitted by `app/core/metrics.py`

| Metric | Type | Labels |
|---|---|---|
| `contecflow_app_info` | gauge | `version`, `environment` |
| `contecflow_tickets_created_total` | counter | `tenant_id`, `ticket_type`, `priority`, `source` |
| `contecflow_invoices_created_total` | counter | `tenant_id`, `status` |
| `contecflow_business_event_total` | counter | `event`, `tenant_id` |
| `contecflow_abac_denials_total` | counter | `resource_type`, `action` |
| `contecflow_scheduled_job_duration_seconds` | histogram | `job_name`, `status` |
| `contecflow_external_api_calls_total` | counter | `provider`, `outcome` |
| `contecflow_external_api_latency_seconds` | histogram | `provider` |

## 3. Prometheus scrape config

```yaml
# prometheus.yml
scrape_configs:
  - job_name: contecflow-api
    metrics_path: /metrics
    static_configs:
      - targets: ['contecflow-api:8000']
        labels:
          service: contecflow-psa
          env: production
    authorization:
      type: Bearer
      credentials: <METRICS_AUTH_TOKEN value>
    scrape_interval: 15s
    scrape_timeout: 10s
```

In Kubernetes, prefer a `ServiceMonitor` (kube-prometheus-stack) and store the
token in a `Secret` referenced via `bearerTokenSecret`.

## 4. Alerting rules (PromQL)

```yaml
groups:
  - name: contecflow-api
    interval: 30s
    rules:
      - alert: ContecflowHighErrorRate
        expr: |
          sum by (handler) (rate(http_requests_total{status="5xx"}[5m]))
            / sum by (handler) (rate(http_requests_total[5m])) > 0.01
        for: 10m
        labels: { severity: page }
        annotations:
          summary: "5xx rate > 1% on {{ $labels.handler }}"

      - alert: ContecflowHighLatencyP95
        expr: |
          histogram_quantile(0.95,
            sum by (handler, le) (rate(http_request_duration_seconds_bucket[5m]))
          ) > 1.5
        for: 10m
        labels: { severity: warn }
        annotations:
          summary: "p95 latency > 1.5s on {{ $labels.handler }}"

      - alert: ContecflowExternalAPIDegraded
        expr: |
          sum by (provider) (rate(contecflow_external_api_calls_total{outcome="error"}[10m]))
            / sum by (provider) (rate(contecflow_external_api_calls_total[10m])) > 0.1
        for: 15m
        labels: { severity: warn }
        annotations:
          summary: "{{ $labels.provider }} error rate > 10%"

      - alert: ContecflowScheduledJobFailing
        expr: |
          increase(contecflow_scheduled_job_duration_seconds_count{status="error"}[1h]) > 0
        for: 5m
        labels: { severity: warn }
        annotations:
          summary: "Scheduled job {{ $labels.job_name }} failed in the last hour"

      - alert: ContecflowABACDenialSpike
        expr: |
          sum by (resource_type) (rate(contecflow_abac_denials_total[5m])) > 1
        for: 10m
        labels: { severity: info }
        annotations:
          summary: "ABAC denial spike on {{ $labels.resource_type }} — possible misconfig"
```

## 5. Grafana dashboard (golden signals + business)

Recommended panels and their queries:

| Panel | Query |
|---|---|
| Request rate (RPS) | `sum by (handler) (rate(http_requests_total[1m]))` |
| Error rate (%) | `100 * sum(rate(http_requests_total{status=~"4xx\|5xx"}[5m])) / sum(rate(http_requests_total[5m]))` |
| Latency p50/p95/p99 | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))` (repeat for 0.5 / 0.99) |
| In-flight requests | `sum(contecflow_http_requests_inprogress)` |
| Tickets created (per tenant) | `sum by (tenant_id) (rate(contecflow_tickets_created_total[5m]))` |
| Invoices created (per status) | `sum by (status) (rate(contecflow_invoices_created_total[1h]))` |
| External API p95 | `histogram_quantile(0.95, sum by (provider, le) (rate(contecflow_external_api_latency_seconds_bucket[5m])))` |
| External API error rate | `sum by (provider) (rate(contecflow_external_api_calls_total{outcome="error"}[5m])) / sum by (provider) (rate(contecflow_external_api_calls_total[5m]))` |
| Scheduled job p95 | `histogram_quantile(0.95, sum by (job_name, le) (rate(contecflow_scheduled_job_duration_seconds_bucket[1h])))` |
| ABAC denials | `sum by (resource_type, action) (rate(contecflow_abac_denials_total[5m]))` |

## 6. Adding new metrics

When introducing a new business event:

1. Add the metric definition in [app/core/metrics.py](../app/core/metrics.py).
2. Keep label cardinality bounded — `tenant_id` is fine; never use per-user ids
   or raw URLs.
3. Increment from inside a `try/except: pass` so metrics never break business
   flows.
4. Update this document's metric table and Grafana dashboard.

## 7. Known gaps

- **Xero** outbound calls go through the `xero-python` SDK and are not yet
  wrapped — would require a custom `ApiClient` subclass.
- **DB connection pool** metrics are not yet exposed; consider adding
  `sqlalchemy` pool stats via a custom collector if connection saturation
  becomes a concern.
- **Celery task metrics** are not included here; if Celery becomes the primary
  job runner, integrate `celery-exporter` rather than instrumenting in-process.
