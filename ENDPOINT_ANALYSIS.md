# Análisis de Estructura de Endpoints

**Fecha:** 9 de mayo de 2026  
**Scope:** `app/api/v1/endpoints/` (118 archivos) + `app/api/v1/routers/` (11 archivos)

---

## 📊 RESUMEN EJECUTIVO

### Estadísticas
- **Archivos analizados:** 129
- **Endpoints con DELETE:** ~55 archivos
- **Archivos con soft-delete (is_active):** ~30
- **Archivos con validaciones de dependencias:** ~15
- **Archivos con routers separados:** 11

---

## 🔴 ARCHIVOS CON DELETE ENDPOINTS

### Categoría 1: Hard Delete (sin validación explícita de dependencias)
1. **m365.py** - `DELETE /calendar/events/{event_id}` (hard delete de eventos)
2. **bi_query_builder.py** - `DELETE /queries/{query_id}` (hard delete de queries guardadas)
3. **report_builder.py** - `DELETE /templates/{template_id}` (hard delete de templates)
4. **okrs.py** - `DELETE /{obj_id}`, `DELETE /key-results/{kr_id}` (hard delete de OKRs)
5. **tasks.py** - `DELETE /{task_id}`, `DELETE /dependencies/{dep_id}` 
6. **cab.py** - `DELETE /webhooks/{trigger_id}`, `DELETE /dashboard-widgets/reset`
7. **bi_intelligence.py** - `DELETE /templates/{template_id}`, `DELETE /schedules/{schedule_id}`
8. **epics.py** - `DELETE /wiki/spaces/{space_id}`, `DELETE /wiki/pages/{page_id}`
9. **cmdb.py** - `DELETE /relations/{relation_id}` (CMDB relations)
10. **custom_fields.py** - `DELETE /custom-fields/`, `DELETE /project-workflows/states/`, `DELETE /transitions/`, `DELETE /permissions/`
11. **expenses.py** - `DELETE /my/{expense_id}` (solo borradores)
12. **billing_reports.py** - `DELETE /report-catalog/{report_id}`, `DELETE /automation-workflows/{wf_id}`, `DELETE /scheduled-reports/{report_id}`

### Categoría 2: Soft Delete (is_active = false)
1. **users.py** - `DELETE /{user_id}` (soft) + `DELETE /{user_id}/permanent` (hard)
   - ⚠️ **Patrón:** Dos endpoints para dos operaciones distintas
   - Validación: `enforce_abac()`, impide auto-eliminación
   
2. **enterprise.py** - `DELETE /subcontractors/{sub_id}` (soft), `DELETE /workers/{worker_id}` (soft)
   - Patrón explícito en docstring: `(soft delete)`
   
3. **documents.py** - `DELETE /{doc_id}` (soft = archive)
   - Patrón explícito: "Archive document (soft delete)"
   - Validación: `check_document_access()` con `DocumentAccessLevel.admin`
   
4. **training.py** - `DELETE /courses/{course_id}` (soft via `soft_delete_course()`)
   
5. **service_desk/problem_management.py** - `DELETE /templates/{template_id}` (soft)
   - Validación: `tpl.is_active = False`
   
6. **service_desk/workflow_designer.py** - `DELETE /blueprints/{blueprint_id}` (soft)
   - Docstring: "Archivar blueprint (soft delete)"
   
7. **abac.py** - `DELETE /policies/{policy_id}` (soft)
   - Docstring: "Delete (soft) an ABAC policy"
   
8. **deliverables.py** - `DELETE /{project_id}/{del_id}` (soft)
   
9. **imputations.py** - `DELETE /{imputation_id}` (soft)
   
10. **bi_collaboration.py** - `DELETE .../share/{share_id}` (revoke_dashboard_share)
   
11. **mfa.py** - `DELETE /organizations/{org_id}/remove-user/{user_id}` (remoción de usuario)
   
12. **mfa.py** - `DELETE /mfa/disable` (desactivar MFA)

### Categoría 3: Sin Validación Explícita de Dependencias
⚠️ **PROBLEMA:** Estos archivos hacen DELETE sin verificar si existen registros dependientes:
- **tasks.py** - `delete_task()` no valida tareas con dependencias
- **epics.py** - `delete_page()` no valida páginas referenciadas
- **custom_fields.py** - `delete_workflow_state()` no valida si hay transiciones que lo referencian
- **okrs.py** - No valida relaciones con Key Results
- **bi_query_builder.py** - No valida si query se usa en dashboards

---

## ✅ ARCHIVOS CON VALIDACIONES DE DEPENDENCIAS

### Con Validaciones Explícitas
1. **tasks.py / issue_types.py** - Task dependencies
   ```python
   # Validaciones:
   - self-reference check (predecessor != successor)
   - duplicate dependency check
   - create_task_dependency valida que ambas tareas existan (404)
   - cycle detection en algunos servicios (bookings_service.py)
   ```

2. **epics.py / issue_types.py** - Epic dependencies
   ```python
   # Validaciones:
   - self-reference check
   - duplicate check
   - validates epic existence
   ```

3. **service_desk/cmdb.py** - CMDB relations
   ```python
   # Validaciones:
   - build_ci_relation() valida que source_ci_id y target_ci_id existan
   - _get_scoped_ci_or_404() verifica acceso ABAC
   - get_dependency_graph_d3() traversa sin límite (⚠️ puede ser ineficiente)
   ```

4. **documents.py** - Document access
   ```python
   # Validaciones:
   - get_document_or_404()
   - check_document_access() con niveles de acceso
   ```

5. **abac.py** - ABAC policies
   ```python
   # Validaciones:
   - verify_admin_or_governance_role()
   - ABACDependency dependency checking
   ```

### **⚠️ SIN Validaciones Explícitas**
- **okrs.py** - No valida si OKR tiene Key Results hijos
- **custom_fields.py** - No valida cascadas de workflow states
- **training.py** - No valida inscripciones antes de soft-delete
- **imputations.py** - No valida relaciones antes de delete
- **billing_reports.py** - No valida si report se usa en otros lugares

---

## 🔄 ARCHIVOS CON SOFT-DELETE (is_active)

### Uso Correcto (explícito en docstring)
1. **users.py** - `is_active: bool` en schema, `deactivate_user_record()` sets `is_active=False`
2. **enterprise.py** - Subcontractors y workers, docstring menciona "soft delete"
3. **documents.py** - `archive_document()` comentario explícito
4. **service_desk/problem_management.py** - `is_active = False`
5. **service_desk/workflow_designer.py** - Docstring "Archivar blueprint"
6. **abac.py** - Docstring "Delete (soft)"

### Uso Implícito (en parámetros de query)
1. **bpmn_processes.py** - `is_active: Optional[bool] = None` para filtrar
2. **enterprise.py** - `list_subcontractors(is_active, db)`
3. **automations.py** - `is_active: Optional[bool]` para list operations
4. **bi_intelligence.py** - `is_active` en delivery schedules
5. **public_forms.py** - `is_active: bool = True` por defecto
6. **activity.py** - `list_recurring_tasks_payload(db, project_id, is_active)`
7. **ai_governance.py** - `is_active` en policies
8. **jira_integration.py** - `filter(JiraConfig.is_active == True)`
9. **service_desk/cmdb.py** - `is_active` en providers
10. **service_desk/autonomous.py** - `is_active` para filtrar
11. **service_desk/connectors_marketplace.py** - `is_active == True` en queries
12. **collaboration/workspaces.py** - `is_active` en workspace responses
13. **collaboration/compliance.py** - `is_active` en retention policies y legal holds
14. **collaboration/bots.py** - `is_active` en webhooks

### ⚠️ **Patrón Inconsistente:**
- Algunos archivos filtran por `is_active == True` en queries
- Otros no especifican `is_active` en GETs, devolviendo registros inactivos
- No hay patrón uniforme de defaults

---

## 🔗 PATRONES DE DEPENDENCIAS Y RELACIONES

### 1. **Task Dependencies (bien documentado)**
- **Ubicación:** `tasks.py`, `issue_types.py`, `service_desk/problem_management.py`
- **Modelo:** `TaskDependency`, `TaskDependencyMeta`
- **Tipos:** `FS` (finish-to-start), `SS`, `FF`, `SF`
- **Validaciones:**
  - ✅ Self-reference check
  - ✅ Duplicate check
  - ✅ Existence validation
  - ⚠️ Cycle detection SOLO en `bookings_service.py`, no en `task_service.py`
- **Endpoints:**
  - `POST /dependencies` - crear
  - `DELETE /dependencies/{dep_id}` - eliminar
  - `GET /dependencies` - listar
  - `POST /{task_id}/cascade-reschedule` - impacto en cascada

### 2. **Epic Dependencies**
- **Ubicación:** `epics.py`, `issue_types.py`
- **Modelo:** `EpicDependency`, `EpicDependencyMeta`
- **Tipos:** `finish_to_start`, `start_to_start`, `finish_to_finish`, `relates_to`
- **Validaciones:** Similar a task dependencies
- **Endpoints:**
  - `POST /epic-dependencies` - crear
  - `DELETE /epic-dependencies/{dep_id}` - eliminar
  - `GET /epic-dependencies/{project_id}` - listar

### 3. **CMDB Relations (muy sofisticado)**
- **Ubicación:** `service_desk/cmdb.py`, `service_desk/cmdb_relation_service.py`
- **Modelo:** `CIRelation`
- **Tipos:** `depends_on`, `hosts`, `part_of`, `connects_to`, `runs_on`
- **Validaciones:**
  - ✅ Scope checking via ABAC
  - ✅ CI existence verification
  - ⚠️ Sin cycle detection
  - ⚠️ Traversal sin límite reachable (pero con `limit=300`)
- **Endpoints:**
  - `GET /cmdb/{ci_id}/relations` - impacto directo
  - `POST /cmdb/relations` - crear relación
  - `DELETE /relations/{relation_id}` - eliminar
  - `GET /cmdb/{ci_id}/dependency-graph` - grafo D3.js
  - `GET /cmdb/{ci_id}/blast-radius` - análisis de impacto

### 4. **Falta de Documentación Explícita**
- **OKRs:** No hay endpoint explícito de dependencias
- **Custom Fields:** No hay validación de cascadas de workflow
- **Training:** No valida inscripciones antes de delete
- **Deliverables:** No valida tareas antes de delete
- **Reports:** No valida uso en dashboards

---

## 🚨 PATRONES INCONSISTENTES ENCONTRADOS

### 1. **Patrón CRUD Duplicado**
```python
# ❌ INCONSISTENCIA: users.py tiene ambos
DELETE /users/{user_id}              # soft delete
DELETE /users/{user_id}/permanent    # hard delete

# ✅ CORRECTO: enterprise.py es consistente
DELETE /subcontractors/{sub_id}      # solo soft delete (docstring)
```

### 2. **Validaciones de Dependencias Inconsistentes**
```python
# ✅ tasks.py: valida existencia en create_task_dependency()
# ✅ epics.py: valida existencia en add_epic_dependency()
# ❌ okrs.py: NO valida si OKR tiene dependientes
# ❌ custom_fields.py: NO valida cascadas en states
```

### 3. **Soft-Delete Inconsistente**
```python
# ✅ documents.py - explícito en docstring: "soft delete"
# ✅ enterprise.py - explícito en docstring: "(soft delete)"
# ⚠️ deliverables.py - NO menciona soft/hard
# ⚠️ imputations.py - NO menciona soft/hard
# ❌ training.py - usa soft_delete_course() pero no es claro
```

### 4. **Filtering de is_active Inconsistente**
```python
# ✅ jira_integration.py
filter(JiraConfig.is_active == True)

# ✅ service_desk/connectors_marketplace.py
filter(IntegrationConnector.is_active == True)

# ❌ No hay filtro por defecto en muchos LIST endpoints
# ❌ Algunos endpoints devuelven registros inactivos
```

### 5. **Error Handling Inconsistente**
```python
# ✅ issue_types.py
if msg.startswith("404:"):
    raise HTTPException(404, msg[4:])

# ⚠️ tasks.py
raise HTTPException(400, "Una tarea no puede depender de sí misma")

# ❌ okrs.py
return {"deleted": True}  # sin validación previa
```

### 6. **ABAC Enforcement Inconsistente**
```python
# ✅ documents.py
enforce_abac(db, current_user, "document", ...)
check_document_access(doc, current_user, DocumentAccessLevel.admin)

# ✅ users.py
enforce_abac(db, current_user, "user", ...)

# ❌ okrs.py
NO enforce_abac() call en delete

# ⚠️ custom_fields.py
NO enforce_abac() en algunos endpoints
```

---

## 📋 MATRIZ DE ESTADO POR ARCHIVO

| Archivo | DELETE | Soft? | Depend.Val | ABAC | is_active | Estado |
|---------|--------|-------|-----------|------|-----------|--------|
| users.py | ✅ | ✅ | ✅ | ✅ | ✅ | 🟢 OK |
| documents.py | ✅ | ✅ | ✅ | ✅ | ✅ | 🟢 OK |
| tasks.py | ✅ | ❌ | ⚠️ | ✅ | ❌ | 🟡 WARN |
| abac.py | ✅ | ✅ | ✅ | ✅ | ❌ | 🟡 WARN |
| enterprise.py | ✅ | ✅ | ❌ | ✅ | ✅ | 🟡 WARN |
| okrs.py | ✅ | ❌ | ❌ | ❌ | ❌ | 🔴 CRÍTICO |
| custom_fields.py | ✅ | ❌ | ❌ | ⚠️ | ❌ | 🔴 CRÍTICO |
| epics.py | ✅ | ❌ | ✅ | ✅ | ❌ | 🟡 WARN |
| cmdb.py | ✅ | ❌ | ✅ | ✅ | ❌ | 🟡 WARN |
| training.py | ✅ | ✅ | ❌ | ✅ | ❌ | 🟡 WARN |
| deliverables.py | ✅ | ❌ | ❌ | ❌ | ❌ | 🔴 CRÍTICO |
| imputations.py | ✅ | ❌ | ❌ | ❌ | ❌ | 🔴 CRÍTICO |
| expenses.py | ✅ | ❌ | ⚠️ | ✅ | ❌ | 🟡 WARN |
| bi_intelligence.py | ✅ | ⚠️ | ❌ | ✅ | ✅ | 🟡 WARN |
| bi_collaboration.py | ✅ | ⚠️ | ❌ | ✅ | ❌ | 🟡 WARN |

---

## 🎯 RECOMENDACIONES POR PRIORIDAD

### 🔴 CRÍTICO (Impacto Alto)

1. **okrs.py** - Implementar validaciones de dependencias
   - [ ] Validar que OKR no tenga Key Results antes de delete
   - [ ] Implementar enforce_abac()
   - [ ] Documentar si es soft o hard delete

2. **custom_fields.py** - Validar cascadas de workflow
   - [ ] Validar que state no tenga transiciones
   - [ ] Validar que transición no esté en uso
   - [ ] Implementar enforce_abac() en delete endpoints

3. **deliverables.py** - Validar dependencias
   - [ ] Validar que deliverable no tenga tareas asociadas
   - [ ] Documentar soft vs hard delete
   - [ ] Implementar enforce_abac()

4. **imputations.py** - Validar relaciones
   - [ ] Validar contexto antes de delete
   - [ ] Documentar si es soft o hard delete

### 🟡 IMPORTANTE (Impacto Medio)

5. **tasks.py** - Mejorar validaciones
   - [ ] Validar cascade-reschedule impact limit
   - [ ] Implementar cycle detection en task_service.py
   - [ ] Documentar límites de recursión

6. **Unified is_active filtering**
   - [ ] Decidir default behavior (incluir/excluir inactivos)
   - [ ] Implementar filtro consistente en todos LIST endpoints
   - [ ] Documentar en DOCS.md

7. **ABAC Enforcement** - Audit trail
   - [ ] Auditar que todos DELETE endpoints usen enforce_abac()
   - [ ] Documentar audit trail para soft-deletes

### 🟢 MENOR (Buenas Prácticas)

8. **Documentación** - Marcar explícitamente soft vs hard delete
   - [ ] Actualizar docstrings en todos DELETE endpoints
   - [ ] Crear pattern standard en código

9. **Error Messages** - Estandarizar respuestas
   - [ ] Usar formato consistente de errores de dependencias
   - [ ] Incluir IDs de registros bloqueantes en respuesta

10. **Testing** - Validaciones de cascada
    - [ ] Tests para cycle detection
    - [ ] Tests para dependency validation

---

## 📝 NOTAS TÉCNICAS

### Cycle Detection
- ✅ **Implementado en:** `bookings_service.py` (task dependencies)
- ❌ **Falta en:** `task_service.py`, epics, CMDB relations
- **Riesgo:** Deadlocks en graphs

### Traversal Limits
- ✅ **CMDB:** `limit=300, depth=6` en `/dependency-graph`
- ⚠️ **Tasks:** No hay límite explícito en `cascade_reschedule()`
- **Riesgo:** Stack overflow en casos patológicos

### ABAC Coverage
- ✅ **Alto:** users, documents, abac policies
- ⚠️ **Medio:** tasks, epics, cmdb
- ❌ **Bajo:** okrs, training, custom_fields

### Schema Consistency
- ✅ **Bien documentados:** Task/Epic dependencies (TaskDependencyMeta, EpicDependencyMeta)
- ⚠️ **Parcialmente:** CMDB relations, workflows
- ❌ **Falta:** OKR dependencies, Custom field cascades

---

## 📊 ARCHIVOS QUE IMPLEMENTAN CRUD COMPLETO

| Patrón | Archivos |
|--------|----------|
| Create+Read+Update | users, tasks, projects, clients, templates |
| Create+Read+Delete | okrs, deliverables, imputations, expenses |
| Read+Update+Delete | custom_fields, training, billing_reports |
| Create+Delete (sin Update) | task/epic dependencies, CMDB relations |
| Create+Read (sin Delete) | notifications, activity, timesheets |

---

**Generado:** 9 de mayo de 2026 · Análisis estructurado de 129 archivos de endpoints
