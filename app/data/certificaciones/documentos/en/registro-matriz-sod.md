# Segregation of duties matrix — {{empresa}}

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

Record the incompatible duties, the conflicts detected and their compensating controls.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `segregacion-funciones` | Segregation of duties | iso27001 A.5.3, sox ITGC-APD-06, jsox ITGC-SEG-06 |
| `asientos-manuales` | Manual journal entries | sox FC-02, jsox FCRP-02 |

## 4. Roles and responsibilities

- **Finance**: Owns the controls over financial information.
- **IT**: Implements the technical measures and provides evidence from the systems.

## 5. Record fields

| Field | Description | Required |
|---|---|---|
| Duty A | Permission or role | Yes |
| Duty B | Incompatible permission or role | Yes |
| Risk | What the conflict allows | Yes |
| Users in conflict | List | Yes |
| Compensating control | Description and owner | Yes |

## 6. Retention and access

- Retention period: {{plazo_retencion}}; subject to legal hold where applicable.
- Read-only access for internal audit and external auditors authorised through the portal.
- Every modification is logged in the platform audit log.

## 7. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
