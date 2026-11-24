# Releases, SBOM and signatures record — {{empresa}}

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

Record each published release with its SBOM, independent review and signature.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `sbom-y-versiones-firmadas` | SBOM and tagged and signed releases | iec62443 SM-9, iec62443 SUM-3 |
| `aprobacion-independiente-paso-produccion` | Independent approval of production release | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |

## 4. Roles and responsibilities

- **Process owner**: Applies the document within their process and is accountable for its controls.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Product | Name | Yes |
| Version | Tag | Yes |
| SBOM | File reference | Yes |
| Independent reviewer | A person other than the author | Yes |
| Signature | Fingerprint and certificate | Yes |
| Publication date | Date | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
