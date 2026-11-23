# Guardas por capacidad en toda la API (auditoría 22-11-2026, informe 01, M9)

**Antes (22-11-2026):** 1 425 pares (método, ruta) se guardaban solo por rol (`require_admin`,
`require_admin_or_pm`, `require_admin_or_hr`, `require_any_manager`, `require_internal_user`,
`require_worker`) y había guardas hechas a mano (`_require_admin`, `verify_admin_or_governance_role`,
`_permiso_de_gobierno`, `require_gestor_de_personas`, `if current_user.role not in …: 403`). La
matriz de capacidades (`app/core/capacidades.py`), que es lo que enseña la pantalla, decidía en 492.

**Ahora (23-11-2026):** 0 pares guardados por rol; 1 987 con `requiere_capacidad("x")` (más 12 de
`require_superadmin`, que es otra cosa: la plataforma). Medido importando `app.main` y recorriendo
`app.routes` con su grafo de dependencias (2 791 pares).

## Cómo se hizo (misma audiencia)

- **Codemod revisado** `scripts/codemods/guardas_a_capacidades.py` (`--plan` / `--aplicar`, ya
  aplicado: se niega a regenerar el bloque). Cada fichero de endpoints tiene un **área**
  (`AREA_DE_FICHERO`) y cada guarda un **conjunto de roles**; para (área, guarda) elige una
  capacidad con EXACTAMENTE esos roles:

  | Guarda de rol | Roles | Acción |
  |---|---|---|
  | `require_admin` | admin | `<área>.administrar` |
  | `require_admin_or_pm` | admin, pm | `<área>.gestionar` (o `dirigir` si el nombre ya es de otros roles) |
  | `require_admin_or_hr` | admin, hr | `<área>.rrhh` |
  | `require_any_manager` | admin, pm, team_lead, hr | `<área>.gestionar` (o `responsables`) |
  | `require_internal_user` | los cinco internos | `<área>.usar` |
  | `require_worker` | todos (incluido el externo) | `<área>.trabajar` |

- Reutiliza la capacidad del catálogo si ya existe con ese nombre, los mismos roles y **sin módulo**
  (o solo admin, a quien no se le cierra módulo): `sd.administrar`, `sd.gestionar`, `sd.completo`,
  `alm.gestionar`, `cartera.gestionar`, `software.gestionar`, `org.administrar`
  (ver tabla). El resto se crea **sin `modulo`** en el bloque generado del catálogo (99, más
  `tareas.usar` y `clientes.dirigir` a mano). Por eso no cierra más que la guarda de rol:
  `RequiereCapacidad` solo añade el cierre por módulo de un rol personalizado, y una capacidad sin
  módulo no lo tiene (el cierre por módulo lo sigue haciendo `modulos.comprobar` en
  `get_current_user`, igual que antes). El superadmin pasa con las dos.
- **Guardas a mano**, a la capacidad con el conjunto EFECTIVO (firma ∩ cuerpo):
  - `predictive_observability._require_admin` → `observabilidad.administrar` (antes no dejaba pasar
    al superadmin; ahora sí, como el resto de la API);
  - `verify_admin_or_governance_role` (28 llamadas en ABAC, ABAC admin, gobierno de IA y SOC) y
    `_permiso_de_gobierno` → `gobierno.administrar` / `ia.administrar` / `soc.administrar`, la
    primera de la firma (el 403 sigue saliendo antes que el 422 del periodo). La función se retira;
  - `alm_integracion.require_gestor_de_personas` → `alm.personas` (admin, PM, RRHH);
  - `traduccion.editor_de_contenido`: `require_internal_user` del cuerpo → `traduccion.usar`;
  - 24 `if current_user.role not in (...): 403` al principio del cuerpo (entregables, NPS,
    rentabilidad, riesgos, auto-resolución, correlación de alertas, problemas) → la firma con el
    conjunto efectivo (p. ej. entregables: `proyectos.responsables` en la firma + admin/PM en el
    cuerpo → `proyectos.dirigir`). Las comprobaciones mixtas («propietario o admin») se quedan:
    son control de objeto, no de rol.
- **Herramientas del asistente** (`app/services/ai_chat/tool_execution/politica.py`): cada una
  declara la capacidad de su ruta equivalente (antes una `RequireRole`).
- **Frontend**: `frontend/src/permisos/capacidades.ts` lleva el bloque generado (el test de la
  matriz exige que coincida con el backend). Ninguna pantalla cambia: las capacidades nuevas solo
  guardan la API.
- **De paso** (informe 03): las 4 rutas OLAP (`/analytics/olap/kpis`, `pipeline-funnel`,
  `portfolio-health`, `utilization`), que solo pedían sesión, piden `analitica.ver` como
  `/executive`, la pantalla que las usa.

## Medida M9 (audiencia antes/después)

Comparación por (método, ruta) de los roles que deja pasar la guarda de la firma, antes y después:
de 1 946 pares con guarda, **12 cambian en la firma y ninguno en la práctica**: son los que tenían
la comprobación de rol a mano en el cuerpo, que ahora va en la firma (la audiencia efectiva,
firma ∩ cuerpo, es la misma): `POST/PATCH /deliverables/...` (admin, PM), `POST/PATCH/DELETE
/profitability/{id}/milestones...` (admin, PM), `POST /nps/{id}/health-*` (admin, PM),
`POST /sd/alert-clusters/merge|run-scan` y `POST /sd/tickets/{id}/ai-auto-resolve|auto-resolution/feedback|validate` (admin).
La única diferencia real es que el superadmin pasa ahora también por las guardas que eran a mano.

Barridos (recuentos comentados en cada test):
- `tests/test_guardas_deniegan.py`: 1 382 pares de escritura con guarda (1 360 → +1 trigger-retrain,
  que el detector no veía con `_require_admin`, +21 rutas nuevas del día de otros bloques); mismo
  rol de sondeo por par; las `*.trabajar` (todos los roles) no se sondean, como `require_worker`.
- `tests/test_guardas_de_rol.py`: 1 356 funciones de escritura con guarda (mínimo subido de 929).
- `tests/test_capacidades.py`: 0 rutas donde el módulo de la capacidad no cubre la ruta.
- `tests/test_abac_coverage.py`: ninguna ruta nueva con `enforce_abac` como único control.
- `tests/test_auditoria_2026_11_22_ronda2_nucleo.py`: sin `Depends(require_*)` de rol en `app/api`,
  sin guardas a mano, bloque generado sin módulo, frontend = backend.

## Capacidades que guardan rutas (medido 23-11-2026)

| Capacidad | Roles | Pares (m�todo, ruta) |
|---|---|---|
| `alertas.administrar` | admin | 1 |
| `alertas.gestionar` | admin, pm, team_lead, hr | 1 |
| `alertas.usar` | admin, pm, team_lead, hr, employee | 1 |
| `alm.administrar` | admin | 4 |
| `alm.conexiones` | admin | 7 |
| `alm.configurar` | admin, hr | 3 |
| `alm.consultar` | admin, pm, team_lead, hr, employee | 11 |
| `alm.gestionar` | admin, pm, team_lead, hr | 91 |
| `alm.personas` | admin, pm, hr | 3 |
| `analitica.gestionar` | admin, pm | 6 |
| `analitica.responsables` | admin, pm, team_lead, hr | 7 |
| `analitica.usar` | admin, pm, team_lead, hr, employee | 3 |
| `analitica.ver` | admin, pm | 9 |
| `aprobaciones.administrar` | admin | 17 |
| `aprobaciones.gestionar` | admin, pm, team_lead, hr | 5 |
| `ausencias.administrar` | admin | 3 |
| `ausencias.config` | admin, hr | 21 |
| `ausencias.gestionar` | admin, pm, team_lead, hr | 4 |
| `ausencias.responsables` | admin, pm, team_lead, hr | 7 |
| `ausencias.trabajar` | admin, pm, team_lead, hr, employee, subcontractor | 5 |
| `ausencias.usar` | admin, pm, team_lead, hr, employee | 7 |
| `automatizacion.administrar` | admin | 2 |
| `automatizacion.gestionar` | admin, pm, team_lead, hr | 22 |
| `bi.administrar` | admin | 59 |
| `bi.gestionar` | admin, pm | 8 |
| `bi.usar` | admin, pm, team_lead, hr, employee | 53 |
| `bpm.gestionar` | admin, pm | 9 |
| `bpm.usar` | admin, pm, team_lead, hr, employee | 10 |
| `cab.administrar` | admin | 16 |
| `cab.gestionar` | admin, pm, team_lead, hr | 10 |
| `cambios.responsables` | admin, pm, team_lead, hr | 7 |
| `cartera.gestionar` | admin, pm | 12 |
| `cartera.usar` | admin, pm, team_lead, hr, employee | 3 |
| `clientes.dirigir` | admin, pm | 2 |
| `clientes.gestionar` | admin, pm, team_lead, hr | 47 |
| `cmdb.administrar` | admin | 21 |
| `cmdb.gestionar` | admin, pm | 17 |
| `cmdb.usar` | admin, pm, team_lead, hr, employee | 3 |
| `colaboracion.administrar` | admin | 11 |
| `colaboracion.gestionar` | admin, pm, team_lead, hr | 12 |
| `colaboracion.trabajar` | admin, pm, team_lead, hr, employee, subcontractor | 1 |
| `colaboracion.usar` | admin, pm, team_lead, hr, employee | 25 |
| `comercial.administrar` | admin | 5 |
| `comercial.gestionar` | admin, pm, team_lead, hr | 15 |
| `comercial.usar` | admin, pm, team_lead, hr, employee | 1 |
| `competencias.gestionar` | admin, hr | 6 |
| `competencias.usar` | admin, pm, team_lead, hr, employee | 1 |
| `contratos.administrar` | admin | 1 |
| `contratos.gestionar` | admin, pm, team_lead, hr | 7 |
| `costes.config` | admin, hr | 12 |
| `demanda.config` | admin | 15 |
| `demanda.gestionar` | admin, pm | 3 |
| `demanda.ver` | admin, pm, team_lead, hr, employee | 6 |
| `divisas.administrar` | admin | 3 |
| `divisas.gestionar` | admin, pm, team_lead, hr | 1 |
| `divisas.usar` | admin, pm, team_lead, hr, employee | 1 |
| `empresa.administrar` | admin | 18 |
| `empresa.gestionar` | admin, pm, team_lead, hr | 31 |
| `evaluaciones.gestionar` | admin, hr | 15 |
| `evaluaciones.responsables` | admin, pm, team_lead, hr | 2 |
| `exportar.gestionar` | admin, pm | 1 |
| `exportar.usar` | admin, pm, team_lead, hr, employee | 1 |
| `facturacion.gestionar` | admin, pm, team_lead, hr | 37 |
| `facturacion.usar` | admin, pm, team_lead, hr, employee | 1 |
| `finanzas.gestionar` | admin, pm | 6 |
| `finanzas.responsables` | admin, pm, team_lead, hr | 16 |
| `finanzas.ver` | admin, pm | 1 |
| `firma.administrar` | admin | 12 |
| `formacion.gestionar` | admin, hr | 3 |
| `formacion.responsables` | admin, pm, team_lead, hr | 3 |
| `formacion.usar` | admin, pm, team_lead, hr, employee | 1 |
| `gastos.dirigir` | admin, pm | 1 |
| `gastos.responsables` | admin, pm, team_lead, hr | 7 |
| `gastos.trabajar` | admin, pm, team_lead, hr, employee, subcontractor | 6 |
| `gastos.usar` | admin, pm, team_lead, hr, employee | 4 |
| `gobierno.administrar` | admin | 68 |
| `gobierno.gestionar` | admin, pm, team_lead, hr | 4 |
| `gobierno.usar` | admin, pm, team_lead, hr, employee | 3 |
| `horas_extra.config` | admin, hr | 7 |
| `horas_extra.gestionar` | admin, pm, team_lead, hr | 4 |
| `horas_extra.trabajar` | admin, pm, team_lead, hr, employee, subcontractor | 10 |
| `ia.administrar` | admin | 34 |
| `ia.asignacion_config` | admin, hr | 4 |
| `ia.gestionar` | admin, pm, team_lead, hr | 25 |
| `ia.rrhh` | admin, hr | 3 |
| `ia.usar` | admin, pm, team_lead, hr, employee | 33 |
| `informes.gestionar` | admin, pm | 6 |
| `informes.usar` | admin, pm, team_lead, hr, employee | 2 |
| `integraciones.administrar` | admin | 26 |
| `integraciones.desarrollo` | admin, pm | 4 |
| `integraciones.gestionar` | admin, pm | 8 |
| `integraciones.importar` | admin, pm, team_lead, hr | 4 |
| `integraciones.responsables` | admin, pm, team_lead, hr | 18 |
| `integraciones.usar` | admin, pm, team_lead, hr, employee | 24 |
| `interno.cargos` | admin | 8 |
| `interno.gestionar` | admin, pm | 19 |
| `interno.portal` | admin, pm, team_lead, hr, employee | 18 |
| `observabilidad.administrar` | admin | 3 |
| `okr.gestionar` | admin, pm, team_lead, hr | 7 |
| `okr.usar` | admin, pm, team_lead, hr, employee | 1 |
| `org.administrar` | admin | 47 |
| `org.rrhh` | admin, hr | 1 |
| `panel.administrar` | admin | 2 |
| `panel.gestionar` | admin, pm, team_lead, hr | 3 |
| `partes.gestionar` | admin, pm, team_lead, hr | 6 |
| `personas.administrar` | admin | 4 |
| `personas.config` | admin, hr | 12 |
| `personas.gestionar` | admin, pm, team_lead, hr | 2 |
| `personas.rrhh` | admin, hr | 1 |
| `personas.usar` | admin, pm, team_lead, hr, employee | 1 |
| `portal.formularios` | admin, pm | 3 |
| `presupuestos.gestionar` | admin, pm, team_lead, hr | 32 |
| `proveedores.config` | admin, pm | 4 |
| `proveedores.gestionar` | admin, pm | 45 |
| `proveedores.portal` | subcontractor | 10 |
| `proveedores.ver` | admin, pm, team_lead, hr | 16 |
| `proyectos.administrar` | admin | 3 |
| `proyectos.config` | admin, pm | 21 |
| `proyectos.dirigir` | admin, pm | 59 |
| `proyectos.responsables` | admin, pm, team_lead, hr | 39 |
| `proyectos.usar` | admin, pm, team_lead, hr, employee | 28 |
| `recursos.gestionar` | admin, pm, team_lead, hr | 24 |
| `recursos.usar` | admin, pm, team_lead, hr, employee | 1 |
| `reservas.administrar` | admin | 5 |
| `reservas.gestionar` | admin, pm, team_lead, hr | 17 |
| `reservas.usar` | admin, pm, team_lead, hr, employee | 1 |
| `reuniones.config` | admin | 6 |
| `reuniones.usar` | admin, pm, team_lead, hr, employee | 31 |
| `sd.administrar` | admin | 108 |
| `sd.completo` | admin, pm, team_lead, hr, employee | 58 |
| `sd.config` | admin, pm, team_lead, hr | 18 |
| `sd.disenar_flujos` | admin, pm | 6 |
| `sd.gestionar` | admin, pm, team_lead, hr | 53 |
| `sd.trabajar` | admin, pm, team_lead, hr, employee, subcontractor | 10 |
| `seguridad.administrar` | admin | 19 |
| `seguridad.recertificar` | admin, pm, team_lead, hr | 2 |
| `soc.administrar` | admin | 5 |
| `software.administrar` | admin | 13 |
| `software.gestionar` | admin, pm | 89 |
| `tareas.dirigir` | admin, pm | 6 |
| `tareas.trabajar` | admin, pm, team_lead, hr, employee, subcontractor | 2 |
| `tarifas.gestionar` | admin, pm, team_lead, hr | 9 |
| `traduccion.administrar` | admin | 5 |
| `traduccion.usar` | admin, pm, team_lead, hr, employee | 13 |
