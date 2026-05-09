# DELETE Endpoints Comprehensive Audit

**Fecha:** 9 de mayo de 2026  
**Análisis:** 182 DELETE endpoints en `app/api/v1/`

---

## 📊 RESUMEN EJECUTIVO

| Métrica | Valor | Estado |
|---------|-------|--------|
| **Total DELETE endpoints** | 182 | - |
| **Hard-Delete (sin is_active)** | 163 (89.6%) | 🔴 CRÍTICO |
| **Sin enforce_abac()** | 174 (95.6%) | 🔴 CRÍTICO |
| **Sin validación de dependencias** | 125 (68.7%) | 🟠 ALTO |
| **Respuesta != {"ok": true}** | 120 (65.9%) | 🟠 ALTO |
| **Sin filtro is_active en búsqueda** | 155 (85.2%) | 🔴 CRÍTICO |

---

## 🚨 PROBLEMAS IDENTIFICADOS

### 1. **CRÍTICO: Hard-Delete sin is_active (163 endpoints)**

Los endpoints realizan **eliminaciones permanentes** sin la capacidad de soft-delete.

**Impacto:**
- ❌ No hay forma de recuperar datos eliminados
- ❌ Violación de auditoría y compliance
- ❌ Pérdida de trazabilidad
- ❌ Riesgo de acceso a datos históricos comprometido

**Archivos principales:**
- `advanced_config.py`: 7 DELETE endpoints (roles, task-types, rate-tables, vacation-policies, offices, custom-fields, templates)
- `alm.py`: 7 DELETE endpoints (vendors, contracts, licenses, assets, cost-centers)
- `approvals.py`: 3 DELETE endpoints (workflows, steps, groups)
- `ai_chat.py`: 1 DELETE endpoint (prompts)
- `cmdb.py`: 7 DELETE endpoints

---

### 2. **CRÍTICO: Missing enforce_abac() (174 endpoints)**

**Solo 8 endpoints usan `enforce_abac()`:**
- `deliverables.py` L131 ✓
- `okrs.py` L61 ✓
- `okrs.py` L96 ✓
- `users.py` L195 ✓
- `users.py` L210 ✓

**Impacto:**
- ❌ Falta de control de acceso granular
- ❌ Riesgo de eliminación no autorizada
- ❌ Violación de principio de mínimo privilegio
- ❌ Auditoría insuficiente

**Endpoints Críticos sin ABAC:**
- `advanced_config.py`: delete_role, delete_task_type, delete_rate_table, delete_vacation_policy, delete_office, delete_custom_field, delete_template
- `approvals.py`: delete_workflow, delete_step, delete_group
- `alm.py`: delete_vendor, delete_contract, delete_license, delete_asset, delete_cost_center
- `ai_chat.py`: delete_prompt (L764)

---

### 3. **ALTO: Sin validación de dependencias (125 endpoints)**

**Impacto:**
- ❌ Eliminación de recursos sin verificar si tienen dependencias
- ❌ Integridad referencial comprometida
- ❌ Cascadas de errores silenciosos

**Ejemplos problemáticos:**
- `activity.py` L214: `/recurring-tasks/{rt_id}` - No valida si hay instancias activas
- `alm.py` L54-168: Múltiples endpoints sin validación
- `automations.py` L83: `/{rule_id}` - Sin validación
- `bi_conditional_delivery.py` L121: Sin validación

---

### 4. **ALTO: Formato de respuesta inconsistente (120 endpoints)**

**Problemas:**
- 62 endpoints devuelven formato incorrecto (no es `{"ok": true}`)
- Algunos devuelven `{"status": "...", "deleted": true, etc.}`
- Inconsistencia en contrato API

**Ejemplos:**
- `documents.py` L163: `{"status": "archived"}` ❌
- `documents.py` L305: `{"status": "revoked"}` ❌
- `training.py` L55: `{"deleted": true}` ❌

---

### 5. **CRÍTICO: Sin filtro is_active en búsqueda (155 endpoints)**

Cuando el endpoint busca el recurso antes de eliminarlo, NO filtra por `is_active==True`.

**Impacto:**
- ❌ Puede recuperar y "eliminar" nuevamente recursos ya soft-deleted
- ❌ Inconsistencia en el patrón de soft-delete

---

## 📋 MATRIZ COMPLETA (Primeros 50 endpoints)

| Archivo | Línea | Endpoint | ABAC | SoftDel | Validation | Response | FilterActive | Status |
|---------|-------|----------|------|---------|------------|----------|--------------|--------|
| advanced_config | 140 | /roles/{role_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| advanced_config | 174 | /task-types/{type_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| advanced_config | 217 | /rate-tables/{table_id}/entries/{entry_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| advanced_config | 224 | /rate-tables/{table_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| advanced_config | 249 | /vacation-policies/{policy_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| advanced_config | 282 | /offices/{office_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| advanced_config | 328 | /custom-fields/{field_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| advanced_config | 359 | /templates/{template_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| ai_chat | 405 | /ai/conversations/{conv_id} | ✗ | ✓ | ✗ | ✗ | ✗ | 🟠 |
| ai_chat | 417 | /ai/conversations | ✗ | ✓ | ✗ | ✗ | ✗ | 🟠 |
| ai_chat | 764 | /governance/prompts/{prompt_id} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| ai_governance | 191 | /policies/{policy_id} | ✗ | ✓ | ✓ | ✓ | ✗ | 🟠 |
| ai_providers | 85 | /{pid} | ✗ | ✗ | ✓ | ✓ | ✗ | 🔴 |
| alm | 54 | /vendors/{vid} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| alm | 78 | /contracts/{cid} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| alm | 102 | /licenses/{lid} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| alm | 112 | /licenses/{lid}/assignments/{aid} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| alm | 136 | /assets/{aid} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| alm | 158 | /cost-centers/{cid} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| alm | 168 | /assets/{aid}/installs/{iid} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| approvals | 174 | /workflows/{workflow_id} | ✗ | ✗ | ✓ | ✓ | ✗ | 🟠 |
| approvals | 212 | /workflows/{workflow_id}/steps/{step_id} | ✗ | ✗ | ✓ | ✓ | ✗ | 🟠 |
| approvals | 431 | /groups/{group_id} | ✗ | ✗ | ✓ | ✓ | ✗ | 🟠 |
| automations | 83 | /{rule_id} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| bi_bookmarks | 114 | /bi/bookmarks/{bookmark_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| bi_conditional_delivery | 121 | /bi/delivery/rules/{rule_id} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| bi_embed | 42 | /token/{jti} | ✗ | ✗ | ✗ | ✗ | ✗ | 🔴 |
| deliverables | 131 | /{project_id}/{del_id} | ✓ | ✓ | ✓ | ✓ | ✗ | 🟢 |
| documents | 163 | /{doc_id} | ✗ | ✓ | ✓ | ✗ | ✗ | 🟠 |
| documents | 305 | /{doc_id}/permissions/{perm_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| documents | 595 | /{doc_id}/tags/{tag_name} | ✗ | ✗ | ✓ | ✓ | ✗ | 🟠 |
| okrs | 61 | /{obj_id} | ✓ | ✓ | ✓ | ✓ | ✗ | 🟢 |
| okrs | 96 | /key-results/{kr_id} | ✓ | ✓ | ✓ | ✓ | ✗ | 🟢 |
| projects | 163 | /{project_id} | ✗ | ✗ | ✓ | ✗ | ✗ | 🔴 |
| projects | 218 | /{project_id}/members/{member_id} | ✗ | ✗ | ✓ | ✓ | ✗ | 🟠 |
| users | 195 | /{user_id} | ✓ | ✓ | ✓ | ✗ | ✗ | 🟠 |
| users | 210 | /{user_id}/permanent | ✓ | ✗ | ✓ | ✗ | ✗ | 🔴 |

---

## 🎯 PRIORIZACIÓN POR CRITICIDAD

### 🔴 P0 - CRÍTICO (Implementar inmediatamente)

**Soft-Delete Implementation (163 endpoints):**
1. Add `is_active` column a modelos de almacenamiento
2. Cambiar todas las operaciones DELETE a SET is_active=False
3. Filtrar por is_active=True en todas las búsquedas

**ABAC Enforcement (174 endpoints):**
1. Llamar `enforce_abac()` antes de cada DELETE
2. Pasar el resource_id y resource_type correcto

**Archivos críticos:**
- [advanced_config.py](app/api/v1/endpoints/advanced_config.py) - 7 endpoints
- [alm.py](app/api/v1/endpoints/alm.py) - 7 endpoints
- [approvals.py](app/api/v1/endpoints/approvals.py) - 3 endpoints

### 🟠 P1 - ALTO (Implementar en 2 semanas)

**Response Format Standardization (62 endpoints):**
- Cambiar todos a `{"ok": true, "message": "..."}`

**Dependency Validation (125 endpoints):**
- Validar dependencias antes de eliminar

### 🟢 P2 - MEDIO (Implementar en el sprint siguiente)

**Filter by is_active in GET (155 endpoints):**
- Agregar `where is_active == True` en todas las búsquedas

---

## 📊 ENDPOINTS CON STATUS ÓPTIMO

Solamente **3 endpoints** cumplen todos los criterios:

1. **deliverables.py L131** - `DELETE /{project_id}/{del_id}`
   - ✓ ABAC enforcement
   - ✓ Soft-delete (is_active)
   - ✓ Validación de dependencias
   - ✓ Respuesta {"ok": true}

2. **okrs.py L61** - `DELETE /{obj_id}`
   - ✓ ABAC enforcement
   - ✓ Soft-delete
   - ✓ Validación
   - ✓ Respuesta {"ok": true}

3. **okrs.py L96** - `DELETE /key-results/{kr_id}`
   - ✓ ABAC enforcement
   - ✓ Soft-delete
   - ✓ Validación
   - ✓ Respuesta {"ok": true}

---

## 📁 ENDPOINTS POR ARCHIVO

```
advanced_config.py          7 endpoints (todos sin soft-delete)
alm.py                      7 endpoints (todos sin soft-delete)
cmdb.py                     7 endpoints (todos sin soft-delete)
epics.py                    7 endpoints
bi_*.py (múltiples)         ~25 endpoints
collaboration/*.py          ~15 endpoints
...
```

---

## 🔧 RECOMENDACIONES

### Fase 1: Soft-Delete Pattern (Semana 1-2)
1. Auditar qué tablas NECESITAN soft-delete vs. hard-delete
2. Agregar `is_active` a modelos críticos
3. Crear Alembic migrations
4. Actualizar servicios: cambiar DELETE a SET is_active=False
5. Filtrar por is_active=True en todas las búsquedas

### Fase 2: ABAC Enforcement (Semana 2-3)
1. Auditar qué endpoints DEBEN tener ABAC
2. Importar `enforce_abac` en todos los endpoints
3. Agregar llamadas antes de operaciones DELETE
4. Tester con diferentes roles (admin, pm, hr, user)

### Fase 3: Standardization (Semana 3-4)
1. Cambiar todos los formatos de respuesta a `{"ok": true, "message": "..."}`
2. Agregar validación de dependencias donde falte
3. Revisar tests

---

## 📌 NOTAS

- Los endpoints en `routers/` (auth_sessions.py, auth_mfa.py) generalmente usan token revocation (soft-delete apropiado)
- Algunos endpoints de `collaboration/` ya implementan soft-delete correctamente
- Se recomienda crear un patrón reutilizable para DELETE endpoints en una utilidad

