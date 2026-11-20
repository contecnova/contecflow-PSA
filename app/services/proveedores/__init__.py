"""Proveedores y externalizacion (19-11-2026, migracion 189).

Diseno: `docs/PROVEEDORES_Y_EXTERNALIZACION.md`. El proveedor es
`subcontractors` con tipo (`freelance` | `company`) y modos
(`staff_augmentation`, `outsourcing`, `managed_services`). Las personas
externas siguen en `app/services/externos/` (recurso, acceso, baja).

Modulos:

- `tipos`: enumeraciones y reglas fijas (una sola fuente).
- `ficha`: clasificacion, alta de freelance en un paso, ficha completa,
  suspender/reactivar/baja, cuadro global y proveedores asignables.
- `asignabilidad`: quien puede recibir trabajo (before_flush de `Task`) y
  formacion/evaluaciones solo con `training_enabled`.
- `contratos`: contratos, plantillas y lineas de precio.
- `servicios`: servicios gestionados y su SLA medido en su cola del SD.
- `paquetes`: trabajo externalizado (alcance, ciclo, aceptacion con UAT),
  tareas externalizadas e informes.
- `consumo`: consumo registrado y medicion automatica.
- `facturacion`: prevision, estados de cuenta, conciliacion, aprobacion con
  segregacion y coste en el proyecto.
- `grc`: documentos, riesgo, accesos, requisitos, avisos diarios, controles
  del informe de cumplimiento y RGPD del freelance.
- `rendimiento`: cuadro de mando del proveedor.
"""
