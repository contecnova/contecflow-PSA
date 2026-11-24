# Automation systems security policy — {{empresa}}

| Field | Value |
|---|---|
| Type | Policy |
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

Establish the security programme for the plants and automation systems of {{empresa}}.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}. It includes the plants and automation systems listed in {{plantas_ot}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `programa-seguridad-ot` | Security programme for automation systems | iec62443 SPE 1 |
| `zonas-y-conductos` | Zones and conduits | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | Target security level per zone | iec62443 ZCR 5, iec62443 ZCR 6 |
| `acceso-redes-no-confiables` | Access from untrusted networks | iec62443 SR 1.13, iec62443 NDR 1.13 |
| `gestion-eventos-ot` | Plant event and incident management | iec62443 SPE 7 |

## 4. Roles and responsibilities

- **Management**: Approves the document and allocates the necessary resources.
- **OT**: Implements the measures in the plants and automation systems.
- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **IT**: Implements the technical measures and provides evidence from the systems.

## 5. Guidelines

### 5.1 OT organisation

Owners per plant and relationship with corporate security.

{{detalle_organizacion_ot}}

### 5.2 Zones and conduits

Partitioning criteria and target SL per zone.

{{detalle_zonas_y_conductos}}

### 5.3 Remote access

Conditions and approval of supplier access.

{{detalle_acceso_remoto}}

### 5.4 Changes and patches

Maintenance windows and prior testing.

{{detalle_cambios_y_parches}}

### 5.5 Plant incidents

Coordination with the corporate response.

{{detalle_incidentes_en_planta}}

## 6. Records and evidence

- Zones and SL record

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
