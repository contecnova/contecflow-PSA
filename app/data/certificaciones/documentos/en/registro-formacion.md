# Training and awareness record — {{empresa}}

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

Record the training received by each person.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `formacion-concienciacion` | Training and awareness | iso27001 7.3, iso27001 A.6.3, tisax 2.1.3, nis2 art.21.2.g, iec62443 SPE 1 |
| `formacion-ciberseguridad-direccion` | Cybersecurity training for the management body | nis2 art.20.2 |
| `formacion-proteccion-prototipos` | Staff training and commitment on prototypes | tisax 8.2.3 |

## 4. Roles and responsibilities

- **HR**: Integrates the requirements into people processes.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Person | Identifier | Yes |
| Training activity | Title | Yes |
| Date | Date performed | Yes |
| Result | Assessment | Yes |
| Expiry | Renewal date | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
