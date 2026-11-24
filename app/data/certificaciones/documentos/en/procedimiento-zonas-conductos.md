# Zones, conduits and security level procedure — {{empresa}}

| Field | Value |
|---|---|
| Type | Procedure |
| Code | {{codigo_documento}} |
| Version | {{version}} |
| Owner | {{propietario}} |
| Approved by | {{aprobador}} (Documents approval workflow) |
| Approval date | {{fecha_aprobacion}} |
| Next review | {{fecha_revision}} |
| Classification | {{clasificacion}} |
| Scope | {{alcance}} |

> Template drafted by contecflow. Replace the `{{...}}` placeholders and adapt the content to your organisation. It does not include copyrighted standards text; if your company holds a licence, it may import the official text into the catalogue.

## 1. Purpose

Describe how {{empresa}} partitions its plant systems into zones and conduits and sets the target SL for each zone.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}. It includes the plants and automation systems listed in {{plantas_ot}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `sistema-bajo-consideracion` | Definition of the system under consideration | iec62443 ZCR 1 |
| `evaluacion-riesgos-ot` | OT cybersecurity risk assessment | iec62443 ZCR 2, iec62443 ZCR 4, iec62443 ZCR 5, iec62443 SPE 1 |
| `zonas-y-conductos` | Zones and conduits | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | Target security level per zone | iec62443 ZCR 5, iec62443 ZCR 6 |
| `especificacion-requisitos-ciberseguridad` | System cybersecurity requirements specification | iec62443 ZCR 6 |
| `aprobacion-propietario-activo` | Approval by the asset owner | iec62443 ZCR 7 |

## 4. Roles and responsibilities

- **OT**: Implements the measures in the plants and automation systems.
- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Process owner**: Applies the document within their process and is accountable for its controls.

## 5. Procedure steps

### 5.1 System under consideration

Boundaries and inventory.

{{detalle_sistema_bajo_consideracion}}

### 5.2 Initial assessment

Risk without countermeasures.

{{detalle_evaluacion_inicial}}

### 5.3 Partitioning

Grouping criteria and reflection in the CMDB.

{{detalle_particion}}

### 5.4 Detailed assessment and SL-T

By zone and conduit.

{{detalle_evaluacion_detallada_y_sl_t}}

### 5.5 Requirements and approval

Specification and owner sign-off.

{{detalle_requisitos_y_aprobacion}}

## 6. Records and evidence

- Zones and SL record

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
