# DELETE Endpoints Comprehensive Audit Report
## Análisis Exhaustivo de 182 DELETE Endpoints en contecflow-PSA

**Análisis ejecutado:** 9 de mayo de 2026  
**Total endpoints analizados:** 182  
**Archivos generados:** 
- `DELETE_ENDPOINTS_AUDIT.md` - Reporte detallado  
- `DELETE_ENDPOINTS_MATRIX.csv` - Matriz completa para Excel

---

## 📊 RESUMEN CRÍTICO

| Categoría | Cantidad | Porcentaje | Severidad |
|-----------|----------|-----------|-----------|
| **Hard-Delete sin is_active** | 163 | 89.6% | 🔴 CRÍTICO |
| **Sin enforce_abac()** | 174 | 95.6% | 🔴 CRÍTICO |
| **Sin validación de dependencias** | 125 | 68.7% | 🟠 ALTO |
| **Respuesta != {"ok": true}** | 120 | 65.9% | 🟠 ALTO |
| **Sin filtro is_active en GET** | 155 | 85.2% | 🔴 CRÍTICO |
| **Endpoints CORRECTOS** | 3 | 1.6% | 🟢 OK |

---

## 🚨 PROBLEMAS ENCONTRADOS POR SEVERIDAD

### 🔴 P0 - CRÍTICO (Implementar inmediatamente)

#### 1. Hard-Delete Pattern (163 endpoints = 89.6%)
**Problema:** 163 endpoints realizan eliminación permanente sin is_active

**Impacto:**
- ❌ NO recuperación de datos
- ❌ Pérdida de auditoría
- ❌ Violación de compliance
- ❌ Datos históricos irrecuperables

**Archivos principales sin soft-delete:**
1. `advanced_config.py` (7 endpoints)
   - L140: /roles/{role_id}
   - L174: /task-types/{type_id}
   - L217: /rate-tables/{table_id}/entries/{entry_id}
   - L224: /rate-tables/{table_id}
   - L249: /vacation-policies/{policy_id}
   - L282: /offices/{office_id}
   - L328: /custom-fields/{field_id}

2. `alm.py` (7 endpoints)
   - L54: /vendors/{vid}
   - L78: /contracts/{cid}
   - L102: /licenses/{lid}
   - L112: /licenses/{lid}/assignments/{aid}
   - L136: /assets/{aid}
   - L158: /cost-centers/{cid}
   - L168: /assets/{aid}/installs/{iid}

3. `cmdb.py` (7 endpoints)
   - L48: /wiki-tags/{tag_id}
   - L60: /wiki-pages/{page_id}/tags/{tag_id}
   - L250: /items/{item_id}
   - L278: /relations/{relation_id}
   - L360: /kanban/columns/{column_id}
   - L406: /sprint-plans/{plan_id}
   - L447: /sla-calendars/{cal_id}

4. Otros archivos: `approvals.py`, `automations.py`, `bi_*.py`, `bookings.py`, `epics.py`, etc.

#### 2. Missing enforce_abac() (174 endpoints = 95.6%)
**Problema:** Solo 8 endpoints usan enforce_abac()

**Endpoints CORRECTOS con ABAC:**
- ✓ deliverables.py L131
- ✓ okrs.py L61
- ✓ okrs.py L96
- ✓ users.py L195
- ✓ users.py L210
- ✓ custom_fields.py L130 (WorkflowState)
- ✓ custom_fields.py L150 (WorkflowTransition)
- ✓ imputations.py L90

**Impacto de falta de ABAC:**
- ❌ Control de acceso no granular
- ❌ Riesgo de eliminación no autorizada
- ❌ Violación de RBAC
- ❌ Auditoría insuficiente

---

### 🟠 P1 - ALTO (Implementar en 2 semanas)

#### 3. Response Format Inconsistency (120 endpoints = 65.9%)
**Problema:** Formatos de respuesta inconsistentes

**Formatos encontrados:**
- `{"ok": true}` - CORRECTO (62 endpoints)
- `{"status": "..."}` - INCORRECTO
- `{"deleted": true}` - INCORRECTO
- `{"message": "..."}` - INCORRECTO

**Ejemplos de endpoints con formato incorrecto:**
- documents.py L163: `{"status": "archived"}`
- documents.py L305: `{"status": "revoked"}`
- training.py L55: `{"deleted": true}`
- users.py L195: `{"message": "..."}`

#### 4. Missing Dependency Validation (125 endpoints = 68.7%)
**Problema:** No validan dependencias antes de eliminar

**Impacto:**
- ❌ Integridad referencial comprometida
- ❌ Cascadas de errores
- ❌ Estados inconsistentes

**Ejemplos:**
- activity.py L214: `/recurring-tasks/{rt_id}` sin validar instancias
- alm.py L54-168: Múltiples endpoints sin validación
- automations.py L83: Sin validar rules en uso
- bi_conditional_delivery.py L121: Sin validación

---

## ✅ ENDPOINTS CORRECTAMENTE IMPLEMENTADOS (3 total)

### 1. deliverables.py L131 - DELETE /{project_id}/{del_id}
```python
@router.delete("/{project_id}/{del_id}", summary="Eliminar entregable (soft delete)")
def delete_deliverable(...):
    enforce_abac(db, current_user, "deliverable", del_id, action="delete")  # ✓ ABAC
    deliverable_service.delete_deliverable(db, d)                           # ✓ Soft-delete
    return {"ok": True, "message": f"Entregable '{d.name}' eliminado"}       # ✓ Response OK
```

**Cumple:**
- ✓ enforce_abac()
- ✓ Soft-delete (is_active)
- ✓ Response {"ok": true}
- ✓ Validación de dependencias

### 2. okrs.py L61 - DELETE /{obj_id}
```python
@router.delete("/{obj_id}", summary="Eliminar objetivo (soft delete)")
def delete_objective(obj_id: str, ...):
    enforce_abac(db, cu, "okr", obj_id, action="delete")        # ✓ ABAC
    obj = okr_service.get_objective(db, obj_id)
    result = okr_service.delete_objective(db, obj)              # ✓ Soft-delete
    return result                                                # ✓ Response OK
```

### 3. okrs.py L96 - DELETE /key-results/{kr_id}
Similar a L61, con ABAC, soft-delete y validación.

---

## 📁 MATRIZ POR ARCHIVO (Top 10 problemas)

| Archivo | Endpoints | Hard-Delete | No ABAC | Bad Response | Notes |
|---------|-----------|-------------|---------|--------------|-------|
| advanced_config | 7 | 7 | 7 | 7 | TODAS sin soft-delete |
| alm | 7 | 7 | 7 | 7 | TODAS sin soft-delete |
| cmdb | 7 | 7 | 7 | 7 | TODAS sin soft-delete |
| approvals | 3 | 3 | 3 | 0 | Respuesta OK pero sin soft-delete |
| bi_platform | 2 | 0 | 2 | 0 | Soft-delete pero sin ABAC |
| epics | 7 | 7 | 7 | 7 | TODAS sin soft-delete |
| enterprise | 8 | 7 | 8 | 8 | TODAS sin soft-delete |
| ai_chat | 3 | 1 | 3 | 1 | Conversaciones soft-del pero sin ABAC |

---

## 🎯 PLAN DE FIXES PRIORIZADO

### Fase 1: Soft-Delete Implementation (Semana 1-2)
**Objetivo:** Implementar pattern de is_active en 163 endpoints

1. **Identificar modelos que necesitan is_active:**
   - Role, TaskType, RateTable, VacationPolicy, Office, CustomField
   - Vendor, Contract, License, Asset, CostCenter
   - WikiTag, WikiPage, KanbanColumn, SprintPlan, SLACalendar
   - Workflow, WorkflowStep, ApprovalGroup
   - Y 130+ más

2. **Crear Alembic migration:** Agregar is_active columnas

3. **Actualizar servicios:** 
   - Cambiar `db.delete(entity)` a `entity.is_active = False; db.commit()`
   - Filtrar todas las búsquedas: `.filter(Model.is_active == True)`

4. **Endpoints críticos a actualizar:**
   - advanced_config.py (7)
   - alm.py (7)
   - cmdb.py (7)
   - approvals.py (3)
   - epics.py (7)
   - enterprise.py (8)

### Fase 2: ABAC Enforcement (Semana 2-3)
**Objetivo:** Agregar enforce_abac() a 174 endpoints

```python
# Template
@router.delete("/{resource_id}")
def delete_resource(resource_id: str, db: Session = Depends(get_db), 
                   current_user: User = Depends(...)):
    # 1. Buscar recurso
    resource = get_resource(db, resource_id)
    
    # 2. ABAC enforcement
    enforce_abac(db, current_user, "resource_type", resource_id, action="delete")
    
    # 3. Validar dependencias
    if has_dependencies(db, resource_id):
        raise HTTPException(400, "Resource has active dependencies")
    
    # 4. Soft-delete
    resource.is_active = False
    db.commit()
    
    return {"ok": True, "message": "Deleted"}
```

### Fase 3: Response Format Standardization (Semana 3-4)
**Objetivo:** Todos los endpoints devuelven `{"ok": true, "message": "..."}`

```python
# Incorrecto (cambiar)
return {"status": "archived"}
return {"deleted": True}
return {}

# Correcto (estándar)
return {"ok": True, "message": "Resource archived successfully"}
return {"ok": True, "message": "Deleted"}
```

### Fase 4: Dependency Validation (Semana 4-5)
**Objetivo:** Validar dependencias en 125 endpoints

```python
# Template
@router.delete("/{resource_id}")
def delete_resource(...):
    resource = get_resource(db, resource_id)
    
    # Check dependencies
    if has_active_related_records(db, resource_id):
        raise HTTPException(400, f"Cannot delete: {count} related records exist")
    
    resource.is_active = False
    db.commit()
    return {"ok": True}
```

---

## 📋 CHECKLIST DE VERIFICACIÓN

Para cada DELETE endpoint, verificar:

- [ ] ¿Tiene `enforce_abac(db, current_user, "type", resource_id, action="delete")`?
- [ ] ¿Usa soft-delete (`is_active = False`) o hard-delete (`db.delete()`)?
- [ ] ¿Filtra por `is_active == True` cuando busca el recurso?
- [ ] ¿Valida dependencias antes de eliminar?
- [ ] ¿Respuesta es `{"ok": true, "message": "..."}` o compatible?
- [ ] ¿Está en la matriz CSV del proyecto?
- [ ] ¿Tests pasan correctamente?

---

## 📌 NOTAS IMPORTANTES

1. **Archivos especiales:**
   - `routers/auth_sessions.py` (L56): Token revocation - OK
   - `routers/auth_mfa.py` (L347): Passkey deletion - OK
   - `routers/collaboration/*.py`: Algunos ya tienen soft-delete

2. **Consideraciones:**
   - Algunos endpoints no NECESITAN ABAC (ej: delete own resource)
   - Algunos modelos podrían NO necesitar soft-delete (ej: logs)
   - Revisar per modelo qué pattern aplica

3. **Testing:**
   - Incluir tests con diferentes roles
   - Verificar que soft-deleted recursos no aparecen en listados
   - Validar que ABAC bloquea acceso no autorizado

---

## 📌 REFERENCIAS

- **DOCS.md** - Documentar según preferencias del usuario
- **Soft-Delete Pattern:** Ya implementado en deliverables, okrs
- **ABAC Pattern:** `enforce_abac(db, user, resource_type, resource_id, action="delete")`

