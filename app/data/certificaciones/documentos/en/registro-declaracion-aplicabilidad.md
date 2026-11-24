# Statement of Applicability — {{empresa}}

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

Record, for each common control and standard, whether it applies, why, and its status.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `tratamiento-riesgos-declaracion-aplicabilidad` | Risk treatment and Statement of Applicability | iso27001 6.1.3, iso27001 8.3, nis2 art.21.1 |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Management**: Approves the document and allocates the necessary resources.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Common control | Library key | Yes |
| Mappings | Standards and identifiers | Yes |
| Applicable | Yes or no | Yes |
| Justification | Reason for inclusion or exclusion | Yes |
| Implementation status | Not started, in progress, implemented | Yes |
| Effectiveness | Result of the latest test | Yes |
| Owner | Control owner | Yes |
| Last review | Date | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
