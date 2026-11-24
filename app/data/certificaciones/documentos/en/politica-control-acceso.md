# Access control policy — {{empresa}}

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

Establish how access at {{empresa}} is granted, reviewed and removed on the basis of need-to-know and least privilege.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `politica-control-acceso` | Access control policy | iso27001 A.5.15, tisax 4.2.1, nis2 art.21.2.i, iec62443 SPE 6, sox ITGC-APD-00, jsox ITGC-SEG-00 |
| `gestion-identidades` | Identity lifecycle | iso27001 A.5.16, tisax 4.1.1, tisax 4.1.3, iec62443 SR 1.1, iec62443 SR 1.3, iec62443 SR 1.4, iec62443 CR 1.1, iec62443 CR 1.3, iec62443 CR 1.4, iec62443 SG-6 |
| `informacion-autenticacion` | Credential and password management | iso27001 A.5.17, tisax 4.1.2, iec62443 SR 1.5, iec62443 SR 1.7, iec62443 CR 1.5, iec62443 CR 1.7, sox ITGC-APD-05, jsox ITGC-SEG-05 |
| `autenticacion-segura` | Strong and multi-factor authentication | iso27001 A.8.5, tisax 4.1.2, nis2 art.21.2.j, iec62443 SR 1.10, iec62443 SR 1.11, iec62443 CR 1.10, iec62443 CR 1.11 |
| `accesos-privilegiados` | Privileged access | iso27001 A.8.2, tisax 4.2.1, sox ITGC-APD-04, jsox ITGC-SEG-04 |
| `segregacion-funciones` | Segregation of duties | iso27001 A.5.3, sox ITGC-APD-06, jsox ITGC-SEG-06 |
| `revision-periodica-accesos` | Periodic access recertification | iso27001 A.5.18, tisax 4.2.1, sox ITGC-APD-03, jsox ITGC-SEG-03 |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **IT**: Implements the technical measures and provides evidence from the systems.
- **Process owner**: Applies the document within their process and is accountable for its controls.
- **HR**: Integrates the requirements into people processes.
- **Internal audit**: Independently verifies that it is applied.

## 5. Guidelines

### 5.1 Principles

Need-to-know, least privilege, unique identities and segregation of duties.

{{detalle_principios}}

### 5.2 Authentication

Password and multi-factor requirements by type of access ({{politica_mfa}}).

{{detalle_autenticacion}}

### 5.3 Privileged access

Temporary elevation, justification and activity logging.

{{detalle_accesos_privilegiados}}

### 5.4 Periodic review

Recertification frequency by criticality ({{frecuencia_recertificacion}}).

{{detalle_revision_periodica}}

### 5.5 Exceptions

How they are requested, approved and expire.

{{detalle_excepciones}}

## 6. Records and evidence

- Recertification campaigns
- MFA coverage report

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
