# Worker Tasks Documentation

**Created:** May 8, 2026  
**Status:** Production  
**Location:** `app/worker.py` (1,689 LOC)  
**Framework:** Celery + APScheduler (dual scheduler with safety validation)

---

## 📋 Task Inventory

| # | Task Name | Frequency | Domain | Timeout | Priority |
|---|-----------|-----------|--------|---------|----------|
| 1 | `deliver_webhook_task` | On-demand | Webhooks | 5m | Normal |
| 2 | `run_alert_engine` | Every 2 mins | Alerts | 1m | High |
| 3 | `check_missing_imputations` | Every 6 hours | BI Imputation | 15m | Normal |
| 4 | `send_weekly_report` | Weekly (Monday 8am) | Reports | 30m | Low |
| 5 | `generate_retainer_invoices` | Monthly (1st) | Billing | 1h | High |
| 6 | `run_scheduled_reports` | Hourly | BI Reports | 30m | Normal |
| 7 | `run_scheduled_rotation` | Every 15 mins | Secrets | 5m | Critical |
| 8 | `run_agent_task` | On-demand | ML/AI | 1h | High |
| 9 | `jira_periodic_sync` | Every 30 mins | JIRA | 10m | Normal |
| 10 | `process_approval_timeouts` | Every 5 mins | Approvals | 2m | High |
| 11 | `revenue_monthly_recognition` | Monthly (1st) | Revenue | 1h | Critical |
| 12 | `olap_nightly_etl` | Nightly (2am) | BI/OLAP | 2h | Normal |
| 13 | `ml_model_retrain` | Weekly (Sunday 11pm) | ML | 3h | Low |
| 14 | `sla_breach_scan` | Every 5 mins | SLA: guarda estado, avisa riesgo/incumplimiento y escala | 2m | High |
| 14b | `sd_procesar_eventos_de_ticket` | Al confirmar + cada minuto | Bandeja de eventos de ticket: avisos, correo, webhooks, flujos | 1m | High |
| 15 | `problem_auto_detect` | Every 30 mins | Problems | 5m | Normal |
| 16 | `kedb_expiry_scan` | Every hour | KEDB | 5m | Normal |
| 17 | `kedb_effectiveness_scan` | Every hour | KEDB | 5m | Normal |
| 18 | `alert_correlation_scan` | Every 5 mins | Alerts | 2m | High |
| 19 | `cmdb_discovery_run` | Every hour | CMDB | 30m | Normal |
| 20 | `change_impact_batch_score` | Every 30 mins | Changes | 15m | Normal |
| 21 | `routing_outcome_scan` | Every 15 mins | Routing | 5m | Normal |
| 22 | `predictive_scan` | Hourly | Predictive AI | 15m | Normal |
| 23 | `predictive_model_eval_retrain` | Nightly (3am) | ML | 2h | Low |
| 24 | `sync_connector_data` | On-demand | Connectors | 1h | Normal |

**Total: 24 tasks across 12 domains**

---

## 🏗️ Task Domains

```
┌─────────────────────────────────────────────────────────────┐
│ CELERY WORKER ARCHITECTURE                                  │
└─────────────────────────────────────────────────────────────┘

┌───────────────────┐
│ INCOMING TRIGGERS │
├───────────────────┤
│ • Celery Beat     │ ← APScheduler or beat
│ • On-demand calls │ ← API/RPC
│ • Webhooks        │ ← External systems
│ • Events          │ ← Internal messages
└─────────┬─────────┘
          │
          ↓
  ┌───────────────────────────────────────┐
  │ CELERY BROKER (Redis)                 │
  │ Queue management & persistence        │
  └───────────────┬───────────────────────┘
                  │
         ┌────────┼────────┐
         ↓        ↓        ↓
  ┌────────┐ ┌────────┐ ┌────────┐
  │Worker 1│ │Worker 2│ │Worker 3│  ← Horizontal scaling
  │        │ │        │ │        │
  └────┬───┘ └────┬───┘ └────┬───┘
       │          │          │
       │ Runs     │ Runs     │ Runs
       │ Tasks    │ Tasks    │ Tasks
       ↓          ↓          ↓
   ┌──────────────────────────────┐
   │ DATABASE                     │
   │ • Tasks progress             │
   │ • Results cache              │
   │ • State storage              │
   └──────────────────────────────┘
```

---

## 🔄 Task Categories

### **1. REAL-TIME ALERTS & MONITORING**
- `run_alert_engine` (2 mins)
- `sla_breach_scan` (5 mins)
- `sd_procesar_eventos_de_ticket` (1 min, y al confirmar cada cambio de ticket)
- `alert_correlation_scan` (5 mins)
- `problem_auto_detect` (30 mins)

**Flow:**
```
Query incidents → Calculate SLA status → Compare thresholds 
  → Create/Update alerts → Send notifications → Record event
```

---

### **2. WEBHOOKS & INTEGRATIONS**
- `deliver_webhook_task` (on-demand, async)
- `jira_periodic_sync` (30 mins)
- `sync_connector_data` (on-demand)

**Flow:**
```
Event triggered → Serialize payload → HTTP POST to webhook URL 
  → Retry logic (exponential backoff) → Log result → Update status
```

---

### **3. BILLING & REVENUE**
- `generate_retainer_invoices` (monthly 1st)
- `revenue_monthly_recognition` (monthly 1st)

**Flow:**
```
Get contracts due → Calculate amounts → Create invoices/GL entries 
  → Send to finance → Archive previous → Update AR/GL
```

---

### **4. BI & REPORTING**
- `run_scheduled_reports` (hourly)
- `send_weekly_report` (weekly Monday 8am)
- `olap_nightly_etl` (nightly 2am)
- `check_missing_imputations` (every 6 hours)

**Flow:**
```
Query source data → Apply transformations → Build cubes 
  → Export to email/S3 → Update dashboards → Log stats
```

---

### **5. CMDB & DISCOVERY**
- `cmdb_discovery_run` (hourly)

**Flow:**
```
Get active providers (AWS, K8s, vSphere, etc) 
  → Query each cloud API → Normalize data → Reconcile with DB 
  → Detect drift → Update CIs → Deactivate stales
```

---

### **6. CHANGE MANAGEMENT**
- `change_impact_batch_score` (every 30 mins)

**Flow:**
```
Get pending changes → Calculate impact (CIs affected, risk) 
  → Update priority/score → Notify stakeholders → Archive old scores
```

---

### **7. APPROVALS & WORKFLOWS**
- `process_approval_timeouts` (every 5 mins)

**Flow:**
```
Query PENDING approvals → Check due_date → Auto-expire stales 
  → Escalate to next level → Send notifications → Update status
```

---

### **8. ROTATION & SECRETS MANAGEMENT**
- `run_scheduled_rotation` (every 15 mins, CRITICAL)

**Flow:**
```
Get secrets due for rotation → Regenerate key/password 
  → Update storage (Vault) → Notify application → Verify → Log audit
```

**⚠️ Safety:** APScheduler validates before Celery runs (no duplicates)

---

### **9. KNOWLEDGE MANAGEMENT (KEDB)**
- `kedb_expiry_scan` (hourly)
- `kedb_effectiveness_scan` (hourly)

**Flow:**
```
Query articles → Check expiry dates → Archive old → Recalculate 
  effectiveness scores → Update search index → Notify admins
```

---

### **10. PREDICTIVE AI & ML**
- `ml_model_retrain` (weekly Sunday 11pm)
- `predictive_scan` (hourly)
- `predictive_model_eval_retrain` (nightly 3am)
- `run_agent_task` (on-demand, high-compute)

**Flow:**
```
Train: Fetch training data → Validate splits → Train model 
       → Evaluate metrics → Save if improved → Log versioning

Predict: Get incidents/changes → Apply model → Get predictions 
         → Threshold filtering → Return top-N → Cache results
```

---

### **11. ROUTING & ASSIGNMENT**
- `routing_outcome_scan` (every 15 mins)

**Flow:**
```
Get unrouted tickets → Apply routing rules → Assign to queues 
  → Update SLA timers → Notify assignees → Record routing decision
```

---

### **12. WEBHOOKS & DELIVERY**
- `deliver_webhook_task` (async on-demand)

**Flow:**
```
Serialize event → Validate webhook URL → HTTP POST (3 retries) 
  → Record delivery status → Update webhook log → Retry on failure
```

---

## 📊 Execution Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ CELERY BEAT SCHEDULER                                       │
│ (APScheduler backend with safety validation)                │
└────────────┬────────────────────────────────────────────────┘
             │
    ┌────────┴─────────┐
    ↓                  ↓
┌─────────────────┐  ┌─────────────────┐
│ PERIODIC JOBS   │  │ ON-DEMAND CALLS │
│ (schedule.py)   │  │ (API endpoints) │
│ • Cron          │  │ • Manual trigger│
│ • Interval      │  │ • Event-driven  │
└────────┬────────┘  └────────┬────────┘
         │                    │
         └────────┬───────────┘
                  ↓
         ┌─────────────────────┐
         │ TASK VALIDATION     │
         │ • No duplicates     │
         │ • Check running     │
         │ • Lock enforcement  │
         └────────┬────────────┘
                  ↓
         ┌─────────────────────┐
         │ CELERY QUEUE        │
         │ (Redis broker)      │
         └────────┬────────────┘
                  ↓
    ┌─────────────┴──────────────┐
    ↓                            ↓
┌────────────────┐          ┌────────────────┐
│ WORKER POOL    │  ←────→  │ RESULT BACKEND │
│ (exec tasks)   │          │ (cache results)│
│ • retries      │          │ (1h expiry)    │
│ • timeouts     │          │                │
│ • logging      │          │                │
└────────┬───────┘          └────────────────┘
         │
         ├─→ [Task 1] ─→ DB write ─→ DB commit ─→ Success/Failure
         ├─→ [Task 2] ─→ API call ─→ Parse response ─→ Store result
         ├─→ [Task 3] ─→ Compute ─→ Cache ─→ Webhook notify
         └─→ [Task N] ─→ ...
         
         ↓ (all completed or errored)
         
    ┌──────────────────────┐
    │ TASK COMPLETION      │
    │ • Log execution time │
    │ • Record success     │
    │ • Trigger alerts     │
    │ • Update heartbeat   │
    └──────────────────────┘
```

---

## ⏱️ Scheduling Timeline (24h)

```
00:00  ├─ olap_nightly_etl (2h)
       │
02:00  ├─ olap_nightly_etl (ends)
       ├─ predictive_model_eval_retrain (starts, 2h)
       │
03:00  ├─ predictive_model_eval_retrain (runs)
       │
04:00  ├─ predictive_model_eval_retrain (ends)
       ├─ (every 5 mins) run_scheduled_rotation, alert_correlation_scan, process_approval_timeouts
       ├─ (every 5 mins) sla_breach_scan
       ├─ (every 15 mins) routing_outcome_scan, run_agent_task (if enqueued)
       ├─ (every 30 mins) jira_periodic_sync, change_impact_batch_score, problem_auto_detect
       ├─ (hourly) kedb_expiry_scan, kedb_effectiveness_scan, cmdb_discovery_run, predictive_scan, run_scheduled_reports
       ├─ (every 6 hours) check_missing_imputations
       │
08:00  ├─ send_weekly_report (only Monday)
       │
01:00  ├─ generate_retainer_invoices (monthly 1st only)
       ├─ revenue_monthly_recognition (monthly 1st only)
       │
22:00  ├─ (Sunday only) ml_model_retrain (starts, 3h)
       │
23:00  ├─ ml_model_retrain (runs)
       │
24:00  └─ ml_model_retrain (ends, or continues to next day)

Note: All times in UTC. APScheduler validates for no concurrency.
```

---

## 🔐 Safety Mechanisms

### 1. **Dual Scheduler with Validation**
```python
# Before Celery sends to queue:
scheduler.validate_not_running(task_name)  
  → Checks if task already in-flight
  → Prevents duplicate execution
  → Uses Redis lock
```

### 2. **Task Timeouts**
- Most tasks: 5–30 mins
- Heavy compute: 1–3 hours
- Exceeding timeout → Task killed + Retry or escalate

### 3. **Exponential Backoff for Retries**
```
Retry 1: 2 seconds
Retry 2: 4 seconds
Retry 3: 8 seconds
Max retries: 3 (configurable)
```

### 4. **Result Expiry**
- Results cached 1 hour
- Auto-cleanup via Redis expiration
- No stale results polluting cache

### 5. **Worker Health Checks**
- Heartbeat every 10 seconds
- Dead worker detection (timeout 30 seconds)
- Auto-reassign tasks to healthy workers

---

## 🧪 Testing & Debugging

### Run a task manually:
```python
from app.worker import run_alert_engine
result = run_alert_engine.delay()  # Async
result.get(timeout=60)  # Wait for result
```

### Monitor tasks:
```bash
celery -A app.worker events  # Real-time events
celery -A app.worker inspect active  # Active tasks
celery -A app.worker inspect stats  # Worker stats
```

### View logs:
```bash
tail -f logs/worker.log
grep "run_alert_engine" logs/worker.log
```

---

## 📈 Performance Tuning

| Parameter | Current | Recommendation |
|-----------|---------|-----------------|
| Worker processes | 4 | CPU cores × 2 |
| Pool type | Prefork | Prefork for I/O-heavy |
| Task soft limit | 30m | Depends on domain |
| Task hard limit | 1h | 50% above soft limit |
| Queue prefetch | 4 | 4 × worker processes |
| Result TTL | 1h | Tune based on usage |

---

## 📚 References

- Main file: `app/worker.py` (line 1–1689)
- Scheduler: `app/core/scheduler.py`
- Configuration: `app/core/config.py` (CELERY_* settings)
- Tests: `tests/test_worker_*.py`
- Monitoring: Flower (`http://localhost:5555`)
