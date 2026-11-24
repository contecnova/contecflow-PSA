# Critical suppliers record — {{empresa}}

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

Record the critical suppliers and the status of their assessment.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `seguridad-proveedores` | Security in supplier relationships | iso27001 A.5.19, tisax 6.1.1, nis2 art.21.2.d, iec62443 SPE 1 |
| `seguimiento-proveedores` | Monitoring of supplier services and assurance reports | iso27001 A.5.22, tisax 6.1.1, sox ITGC-CO-05, jsox ITGC-EXT-01 |
| `cadena-suministro-tic` | ICT supply chain security | iso27001 A.5.21, nis2 art.21.2.d, nis2 art.21.3, iec62443 SM-9 |

## 4. Roles and responsibilities

- **Compliance Officer**: Coordinates the evidence and its mapping to each standard.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Supplier | Name | Yes |
| Service | Description | Yes |
| Criticality | Level | Yes |
| Assessment | Date and result | Yes |
| Assurance | Certificates, labels or SOC reports | Yes |
| Next review | Date | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
