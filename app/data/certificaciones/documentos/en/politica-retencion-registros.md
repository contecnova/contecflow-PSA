# Records retention policy — {{empresa}}

| Field | Value |
|---|---|
| Type | Policy |
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

Set how long and how the records of {{empresa}} are retained, including legal hold.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `proteccion-registros` | Protection and retention of records | iso27001 A.5.33, sox Sec.802, jsox FIEA-24-4-4 |
| `privacidad-datos-personales` | Privacy and protection of personal data | iso27001 A.5.34, tisax 7.1.2 |
| `integridad-registros-auditoria` | Integrity of the audit log | iso27001 A.8.15, iec62443 SR 3.9, iec62443 CR 3.9 |
| `borrado-informacion` | Information deletion and persistence | iso27001 A.8.10, tisax 5.3.3, iec62443 SR 4.2, iec62443 CR 4.2 |

## 4. Roles and responsibilities

- **Compliance Officer**: Coordinates the evidence and its mapping to each standard.
- **IT**: Implements the technical measures and provides evidence from the systems.
- **Finance**: Owns the controls over financial information.

## 5. Guidelines

### 5.1 Retention schedule

Periods by record type and country.

{{detalle_calendario_de_conservacion}}

### 5.2 Financial records

Retention periods for audit documentation.

{{detalle_registros_financieros}}

### 5.3 Legal hold

When it is activated and who lifts it.

{{detalle_bloqueo_legal}}

### 5.4 Destruction

Secure deletion when the period expires.

{{detalle_destruccion}}

## 6. Records and evidence

- Retention schedule
- Legal holds

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
