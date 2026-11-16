"""Externos como internos, con seguridad de externo (16-11-2026, migracion 178).

Un externo es un `SubcontractorWorker` (persona de un proveedor `Subcontractor`)
con su `User` de rol `subcontractor`. Trabaja como un interno —miembro de
proyecto, imputa, tickets, ausencias— y conserva la seguridad de externo: solo
ve lo suyo y sus proyectos (`politica_de_visibilidad`), nunca datos de la
organizacion ni financieros (`require_internal_user` en esas rutas).

Modulos:

- `disponibilidad`: ventana de contrato y horas contratadas (reservas,
  planificador, nivelacion, SmartMatch, prevision).
- `tarifas`: coste por hora del externo con la tarifa del proveedor vigente.
- `horas`: horas imputadas -> `hours_logged` de la asignacion y aviso de consumo.
- `asignaciones`: asignar a proyecto = ProjectMember; terminar = deja de serlo.
- `ciclo`: alta y baja por ALM, responsable interno, acceso que caduca.
- `conciliacion`: facturas del proveedor contra horas imputadas.
"""
