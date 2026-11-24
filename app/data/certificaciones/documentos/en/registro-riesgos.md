# Risk register — {{empresa}}

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

Record the assessed risks and their treatment.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `evaluacion-riesgos` | Security risk assessment | iso27001 6.1.1, iso27001 6.1.2, iso27001 8.2, tisax 1.4.1, nis2 art.21.1, nis2 art.21.2.a, iec62443 SPE 1 |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Process owner**: Applies the document within their process and is accountable for its controls.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Risk | Description | Yes |
| Affected assets | References | Yes |
| Likelihood | Scale | Yes |
| Impact | Scale | Yes |
| Inherent level | Calculation | Yes |
| Treatment | Option and controls | Yes |
| Residual level | Calculation | Yes |
| Owner | Person who accepts | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
