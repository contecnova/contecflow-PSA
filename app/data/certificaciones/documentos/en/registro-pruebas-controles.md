# Control testing record — {{empresa}}

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

Record each design or effectiveness test and its result.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `evaluacion-direccion-control-interno` | Management assessment of internal control over financial reporting | sox Sec.404(a), jsox FIEA-24-4-4 |
| `independencia-probadores` | Independence of the tester | iec62443 SVV-5 |

## 4. Roles and responsibilities

- **Internal audit**: Independently verifies that it is applied.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Control | Common key | Yes |
| Test type | Design or effectiveness | Yes |
| Population | Description and size | Yes |
| Sample | Size and selection | Yes |
| Result | Effective or with exceptions | Yes |
| Tested by | A person other than the implementer | Yes |
| Date | Date | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
