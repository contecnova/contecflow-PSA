# Backup and restore procedure — {{empresa}}

| Field | Value |
|---|---|
| Type | Procedure |
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

Describe how backups are made, protected and tested.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `copias-seguridad` | Backup and restore | iso27001 A.8.13, tisax 5.2.9, nis2 art.21.2.c, iec62443 SR 7.3, iec62443 CR 7.3, sox ITGC-CO-03, jsox ITGC-OPE-03 |
| `preparacion-tic-continuidad` | IT and OT continuity and recovery | iso27001 A.5.30, tisax 5.2.8, nis2 art.21.2.c, iec62443 SR 7.4, iec62443 CR 7.4, iec62443 SPE 8, sox ITGC-CO-04, jsox ITGC-OPE-04 |

## 4. Roles and responsibilities

- **IT**: Implements the technical measures and provides evidence from the systems.
- **OT**: Implements the measures in the plants and automation systems.

## 5. Procedure steps

### 5.1 Backup policy

What is kept, when, and for how long.

{{detalle_politica_de_copias}}

### 5.2 Protection

Encryption and isolated copy.

{{detalle_proteccion}}

### 5.3 Restore testing

Frequency and criteria.

{{detalle_pruebas_de_restauracion}}

## 6. Records and evidence

- Backup report
- Restore tests

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
