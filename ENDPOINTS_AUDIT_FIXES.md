# Auditoría de Endpoints - Plan de Correcciones

**Fecha:** 9 de mayo de 2026  
**Scope:** Validar todos los endpoints (CREATE, READ, UPDATE, DELETE)  
**Prioridad:** CRÍTICA (Data integrity, dependency validation, ABAC enforcement)

---

## 🔴 CRÍTICO - 4 Archivos Requieren Correcciones Inmediatas

### 1. **okrs.py** - Sin validaciones ni ABAC
**Ubicación:** `/app/api/v1/endpoints/okrs.py` (líneas 60-66, 91-98)

**Problemas:**
- ❌ **Hard delete sin validación de dependencias:** `delete_objective()` borra directamente sin verificar si OKR tiene Key Results
- ❌ **Sin ABAC enforcement:** Falta `enforce_abac()` call en DELETE endpoints
- ❌ **Sin soft-delete:** No usa `is_active` flag
- ⚠️ **Cascada automática pero sin informar:** FK sin `ondelete` pero ORM borra hijos implícitamente

**Endpoints Afectados:**
```
DELETE /okrs/{obj_id}              # delete_objective()
DELETE /okrs/key-results/{kr_id}   # delete_kr()
```

**Modelo:**
- `Objective` → No tiene `is_active`
- `KeyResult` → No tiene `is_active`, FK a Objective sin `ondelete` explícito

**Frontend Usage:**
- `okrsApi.delete(id)` - No maneja dependencias, solo confirmación genérica

**Correcciones Necesarias:**
- [ ] Agregar `is_active: bool = True` a Objective y KeyResult
- [ ] Cambiar CREATE validation para filtrar por `is_active == True`
- [ ] Agregar `_check_okr_dependencies()` similar a departments
- [ ] Implementar `enforce_abac()` en DELETE endpoints
- [ ] Actualizar docstring: "(soft delete)"
- [ ] Frontend: Mostrar mensaje con # de KRs antes de confirmar

---

### 2. **custom_fields.py** - Sin validaciones de cascadas
**Ubicación:** `/app/api/v1/endpoints/custom_fields.py` (líneas 129-150)

**Problemas:**
- ❌ **delete_workflow_state():** No valida si state tiene transiciones
- ❌ **delete_transition():** No valida si transitions se usan en workflow
- ❌ **Sin ABAC enforcement:** Falta `enforce_abac()` calls
- ⚠️ **Soft-delete no documentado:** ¿Es hard o soft?

**Endpoints Afectados:**
```
DELETE /custom-fields/{project_id}/states/{state_id}              # delete_workflow_state()
DELETE /custom-fields/{project_id}/transitions/{transition_id}    # delete_transition()
```

**Modelo:**
- `WorkflowState` - No tiene `is_active` field
- `WorkflowTransition` - References state via `from_state_id`, `to_state_id`

**Dependencias:**
- Tasks can be in a state → Cannot delete state with tasks in it
- Transitions define legal state changes

**Frontend Usage:**
- No validación antes de confirmar

**Correcciones Necesarias:**
- [ ] Agregar `is_active: bool = True` a WorkflowState
- [ ] Implement `_check_workflow_state_dependencies()` - verify no transitions reference it
- [ ] Implement `_check_transitions_in_use()` - verify no tasks are in those states
- [ ] Add `enforce_abac()` enforcement
- [ ] Frontend: Show # of transitions and tasks before delete

---

### 3. **deliverables.py** - Sin validaciones de tareas dependientes
**Ubicación:** `/app/api/v1/endpoints/deliverables.py` (líneas 130-142)

**Problemas:**
- ❌ **delete_deliverable():** No valida si deliverable tiene tareas asociadas
- ❌ **Sin ABAC enforcement:** Falta `enforce_abac()` call
- ❌ **Sin soft-delete:** No usa `is_active` flag
- ⚠️ **Sin documentación clara:** ¿Hard o soft delete?

**Endpoints Afectados:**
```
DELETE /deliverables/{project_id}/{del_id}  # delete_deliverable()
```

**Modelo:**
- `Deliverable` - No tiene `is_active`
- `Task` - Has FK to Deliverable via `deliverable_id`

**Dependencias:**
- Tasks can be linked to deliverable
- Cannot delete if tasks reference it

**Frontend Usage:**
- Simple delete without dependency check

**Correcciones Necesarias:**
- [ ] Agregar `is_active: bool = True` a Deliverable
- [ ] Implement `_check_deliverable_dependencies()` - count linked tasks
- [ ] Implement `enforce_abac()` enforcement
- [ ] Update docstring: "(soft delete)"
- [ ] Frontend: Show # of linked tasks before delete

---

### 4. **imputations.py** - Sin validaciones de relaciones
**Ubicación:** `/app/api/v1/endpoints/imputations.py` (líneas 89-102)

**Problemas:**
- ❌ **delete_imputation():** No valida contexto/relaciones antes de delete
- ❌ **Sin soft-delete:** No usa `is_active` flag
- ⚠️ **Sin documentación clara:** ¿Hard o soft delete?
- ⚠️ **Solo validación de permisos:** No hay dependency check

**Endpoints Afectados:**
```
DELETE /imputations/{imputation_id}  # delete_imputation()
```

**Modelo:**
- `Imputation` - No tiene `is_active`
- Relaciones: Project, Task, User, TimeEntry, Cost

**Dependencias:**
- Imputations are financial records
- Should not delete if invoice/payment references it

**Frontend Usage:**
- Simple delete, no dependency info

**Correcciones Necesarias:**
- [ ] Agregar `is_active: bool = True` a Imputation
- [ ] Implement `_check_imputation_dependencies()` - check billing, invoices, payments
- [ ] Update docstring: "(soft delete)"
- [ ] Frontend: Show financial impact before delete

---

## 🟡 IMPORTANTE - 8 Archivos con Inconsistencias

### Inconsistency Pattern 1: **Soft-Delete Not Consistently Filtered**

**Affected Files:**
- tasks.py - queries don't filter `is_active` by default
- epics.py - LIST doesn't have `is_active` param
- enterprise.py - subcontractors LIST has `is_active` param but inconsistent
- bi_collaboration.py - shares don't have is_active
- training.py - courses don't have is_active

**Fix Pattern:**
- [ ] Ensure all GET /{id} endpoints return 404 if `is_active == False`
- [ ] Ensure all LIST endpoints have `is_active: Optional[bool]` parameter
- [ ] Update docstring to document default behavior

### Inconsistency Pattern 2: **No Cycle Detection in Task Service**

**Location:** `app/services/task_service.py`

**Problem:**
- `bookings_service.py` has cycle detection for task dependencies
- But `task_service.py` doesn't implement it
- Risk: Creating circular dependencies that break scheduling

**Fix:**
- [ ] Port cycle detection from bookings_service to task_service
- [ ] Test: Create A→B, B→C, C→A should fail

### Inconsistency Pattern 3: **ABAC Not Enforced Uniformly**

**Affected:**
- okrs.py - ❌ No enforce_abac()
- custom_fields.py - ⚠️ Partial
- deliverables.py - ❌ No enforce_abac()
- imputations.py - ⚠️ Only permission check, not ABAC

**Fix:**
- [ ] Audit all DELETE endpoints for `enforce_abac()` calls
- [ ] Add missing calls
- [ ] Document ABAC policy for each domain

### Inconsistency Pattern 4: **Error Response Format**

**Problem:**
```python
# ✅ CONSISTENT (some files)
raise HTTPException(400, "Ya existe...")
return {"deleted": True}

# ❌ INCONSISTENT (other files)
return {"ok": True}
return {"deleted": True}
return {"message": "..."}
```

**Fix:**
- [ ] Standardize DELETE response: `{"ok": true}` or `{"deleted": true}`
- [ ] Include dependency info if applicable: `{"ok": true, "dependencies_found": [...]}`

---

## ✅ GOOD PATTERNS - Keep These

### users.py - Best Practice
```python
# ✅ Soft delete with two endpoints
DELETE /users/{user_id}              # soft delete
DELETE /users/{user_id}/permanent    # hard delete

# ✅ WITH ABAC enforcement
enforce_abac(db, current_user, "user", ...)

# ✅ WITH dependency checking (implicit via FK cascade)
# ✅ WITH is_active filtering
```

### documents.py - Best Practice
```python
# ✅ Explicit soft delete in docstring
"Archive document (soft delete)"

# ✅ WITH access control
check_document_access(doc, current_user, DocumentAccessLevel.admin)

# ✅ WITH ABAC enforcement
enforce_abac(db, current_user, "document", ...)
```

### tasks.py - Good Validation
```python
# ✅ Dependency validation
self_reference check
duplicate dependency check
existence validation (404 if not found)

# ✅ Type safety
TaskDependency model with types (FS, SS, FF, SF)
```

---

## 📋 AUDIT CHECKLIST BY CRUD OPERATION

### CREATE Operations ✅
- [x] Validate required fields (Pydantic schemas)
- [x] Check for duplicates with `is_active == True` filter
- [x] Enforce ABAC write permission
- [x] Set default values (is_active=True, created_at, etc.)
- [x] Return proper HTTP 201 with ID

### READ Operations ✅
- [x] Enforce ABAC read permission
- [x] Filter deleted items by `is_active == True` by default
- [x] Support `is_active` query param for explicit filtering
- [x] Return 404 if not found or deleted
- [x] Serialize response (use service layer)

### UPDATE Operations ✅
- [x] Validate ownership or ABAC permission
- [x] Prevent updating deleted items (check `is_active`)
- [x] Update `updated_at` timestamp
- [x] Validate new values (no duplicates, etc.)
- [x] Return updated object

### DELETE Operations ❌ CRITICAL
- [ ] ⚠️ **VALIDATE DEPENDENCIES FIRST** - most critical issue
- [ ] Check for soft-delete vs hard-delete
- [ ] Enforce ABAC delete permission
- [ ] Log deletion (audit trail)
- [ ] Return dependency info if delete blocked
- [ ] Handle cascades correctly (FK ondelete)
- [ ] Update `is_active` for soft-delete (don't use `db.delete()`)

---

## 🔧 IMPLEMENTATION PLAN

### Phase 1: Fix 4 Critical Files (Today)
1. okrs.py - Add soft-delete + dependency validation + ABAC
2. custom_fields.py - Add dependency validation + ABAC
3. deliverables.py - Add soft-delete + dependency validation + ABAC
4. imputations.py - Add soft-delete + dependency validation

**Deliverables:**
- [ ] Migration to add `is_active` columns
- [ ] Service layer functions for dependency validation
- [ ] Updated endpoints with validations
- [ ] Tests for delete → recreate cycles
- [ ] Frontend updates to show dependencies

### Phase 2: Fix Inconsistencies (Next)
- [ ] Standardize soft-delete filtering across all LIST endpoints
- [ ] Add cycle detection to task_service.py
- [ ] Audit ABAC enforcement completeness
- [ ] Standardize error response formats

### Phase 3: Frontend Updates (Next)
- [ ] Add dependency dialogs before delete
- [ ] Show counts (# of tasks, relationships, etc.)
- [ ] Implement cascading confirmations
- [ ] Add undo functionality for soft-deletes

---

## 📊 TESTING REQUIREMENTS

### Delete → Recreate Cycle (Already Passing for settings)
```python
# Should now pass for: okrs, deliverables, imputations, custom_fields
def test_delete_and_recreate(db):
    obj1 = create_obj(data, db)
    delete_obj(obj1.id, db)
    obj2 = create_obj(data, db)  # Should work
    assert obj1.id != obj2.id
    assert len(get_objects(db)) == 1  # Only 1 active
```

### Dependency Validation
```python
def test_delete_blocked_by_dependencies(db):
    parent = create_parent(db)
    child = create_child(parent_id=parent.id, db)
    res = delete_parent(parent.id, db)
    assert res["ok"] == False
    assert "dependencies" in res
    assert len(res["dependencies"]) > 0
```

### Cycle Detection
```python
def test_cycle_detection_in_dependencies(db):
    # A → B → C → A (cycle!)
    a = create_task("A", db)
    b = create_task("B", db)
    c = create_task("C", db)
    add_dependency(a, b, db)
    add_dependency(b, c, db)
    res = add_dependency(c, a, db)  # Should fail
    assert res.status_code == 400
    assert "cycle" in res.json()["detail"].lower()
```

---

## 📝 DOCUMENTATION UPDATES

**Add to DOCS.md:**
- [ ] Section: "Delete Operation Standards"
- [ ] Sub-sections per endpoint pattern
- [ ] Examples of dependency validation responses
- [ ] Migration strategy for soft-delete rollout
- [ ] Audit trail for soft-deletes

---

**Status:** 🔴 READY FOR IMPLEMENTATION  
**Estimated Effort:** 4-6 hours  
**Blockers:** None  
**Next Step:** Begin Phase 1 fixes  
