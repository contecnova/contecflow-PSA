# Continuity and recovery policy — {{empresa}}

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

Ensure that {{empresa}} maintains and recovers its critical services with the necessary level of security.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `preparacion-tic-continuidad` | IT and OT continuity and recovery | iso27001 A.5.30, tisax 5.2.8, nis2 art.21.2.c, iec62443 SR 7.4, iec62443 CR 7.4, iec62443 SPE 8, sox ITGC-CO-04, jsox ITGC-OPE-04 |
| `seguridad-durante-interrupcion` | Security during disruption | iso27001 A.5.29, nis2 art.21.2.c |
| `gestion-crisis` | Crisis management | tisax 1.6.3, nis2 art.21.2.c |
| `copias-seguridad` | Backup and restore | iso27001 A.8.13, tisax 5.2.9, nis2 art.21.2.c, iec62443 SR 7.3, iec62443 CR 7.3, sox ITGC-CO-03, jsox ITGC-OPE-03 |
| `redundancia` | Redundancy of processing facilities | iso27001 A.8.14, tisax 5.2.8 |

## 4. Roles and responsibilities

- **Management**: Approves the document and allocates the necessary resources.
- **IT**: Implements the technical measures and provides evidence from the systems.
- **OT**: Implements the measures in the plants and automation systems.
- **Process owner**: Applies the document within their process and is accountable for its controls.

## 5. Guidelines

### 5.1 Impact analysis

Critical services, RTO and RPO.

{{detalle_analisis_de_impacto}}

### 5.2 Strategies

Redundancy, backups and alternate sites.

{{detalle_estrategias}}

### 5.3 Crisis management

Committee, activation and communication.

{{detalle_gestion_de_crisis}}

### 5.4 Testing

Schedule and success criteria.

{{detalle_pruebas}}

## 6. Records and evidence

- BIA
- Test reports

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
