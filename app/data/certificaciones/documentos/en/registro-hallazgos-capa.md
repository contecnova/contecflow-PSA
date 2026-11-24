# Findings and corrective actions record — {{empresa}}

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

Record the findings of any audit and how they are treated.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `no-conformidades-acciones-correctivas` | Nonconformities and corrective actions | iso27001 10.2, nis2 art.21.4, iec62443 SM-11, sox ELC-04, jsox ELC-04 |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Internal audit**: Independently verifies that it is applied.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Finding | Description | Yes |
| Source | Audit and standard | Yes |
| Type | Major NC, minor NC, observation, opportunity for improvement | Yes |
| Cause | Analysis | Yes |
| Action | Description, owner and deadline | Yes |
| Verification | Who and when | Yes |
| Closure | Date | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
