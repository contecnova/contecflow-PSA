# Asset inventory — {{empresa}}

| Field | Value |
|---|---|
| Type | Record |
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

Record the assets in scope with their owner, classification and criticality.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `inventario-activos` | Inventory of information assets | iso27001 A.5.9, tisax 1.3.1, nis2 art.21.2.i, iec62443 SR 7.8, iec62443 CR 7.8, iec62443 SPE 2 |
| `clasificacion-informacion` | Information classification | iso27001 A.5.12, tisax 1.3.2, iec62443 SPE 5 |

## 4. Roles and responsibilities

- **IT**: Implements the technical measures and provides evidence from the systems.
- **Process owner**: Applies the document within their process and is accountable for its controls.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Asset | Name and CMDB identifier | Yes |
| Type | Information, system, OT component, service | Yes |
| Owner | Responsible person | Yes |
| Classification | Level | Yes |
| Site or zone | Location | Yes |
| Criticality | According to the impact analysis | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
