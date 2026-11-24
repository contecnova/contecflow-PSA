# Incidents and notifications record — {{empresa}}

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

Record incidents and, where significant, each notification with its timestamp.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `respuesta-incidentes` | Incident response | iso27001 A.5.26, tisax 1.6.2, nis2 art.21.2.b |
| `notificacion-incidentes-significativos` | Notification of significant incidents | nis2 art.23.1, nis2 art.23.3 |
| `alerta-temprana-24h` | Early warning within 24 hours | nis2 art.23.4.a |
| `notificacion-incidente-72h` | Incident notification within 72 hours | nis2 art.23.4.b |
| `informe-final-incidente` | Final report within one month | nis2 art.23.4.d, nis2 art.23.4.e |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Compliance Officer**: Coordinates the evidence and its mapping to each standard.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Incident | Service Desk reference | Yes |
| Time of awareness | Date and time | Yes |
| Significant | Yes or no, and reason | Yes |
| Early warning | Date and time sent | Yes |
| Notification | Date and time sent | Yes |
| Final report | Date sent | Yes |
| Authority | Recipient | Yes |
| Communication to customers | Yes or no, and date | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
