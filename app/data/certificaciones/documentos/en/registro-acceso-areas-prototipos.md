# Prototype area access record — {{empresa}}

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

Record entries to and exits from the prototype areas.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `control-entrada-areas-prototipos` | Entry control to prototype areas | tisax 8.1.5 |
| `normas-visitantes-prototipos` | Visitor rules in prototype areas | tisax 8.1.6 |
| `control-acceso-proyectos-prototipos` | Authorisation of access to prototype projects | tisax 8.2.5 |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Person | Identifier or visitor | Yes |
| Area | Identifier | Yes |
| Entry | Date and time | Yes |
| Exit | Date and time | Yes |
| Escort | If a visitor | Yes |
| Authorisation | Reference | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
