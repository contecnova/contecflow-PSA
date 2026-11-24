# Zones, conduits and security levels record — {{empresa}}

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

Record the zones and conduits of each plant with their target and achieved SL.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}. It includes the plants and automation systems listed in {{plantas_ot}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `zonas-y-conductos` | Zones and conduits | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | Target security level per zone | iec62443 ZCR 5, iec62443 ZCR 6 |

## 4. Roles and responsibilities

- **OT**: Implements the measures in the plants and automation systems.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Plant | Site | Yes |
| Zone or conduit | Identifier | Yes |
| Assets | CMDB references | Yes |
| Target SL | SL1–SL4 | Yes |
| Achieved SL | SL1–SL4 | Yes |
| Gap and measures | Description | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
