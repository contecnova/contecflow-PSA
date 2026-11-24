# Vulnerability management procedure — {{empresa}}

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

Describe how technical vulnerabilities in IT and OT are detected, prioritised and remediated.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `gestion-vulnerabilidades-tecnicas` | Technical vulnerability management | iso27001 A.8.8, tisax 5.2.5, nis2 art.21.2.e, iec62443 SPE 4, iec62443 SPE 8 |
| `inteligencia-amenazas` | Threat intelligence | iso27001 A.5.7, nis2 art.21.2.e |
| `pruebas-intrusion` | Penetration testing | iso27001 A.8.8, iso27001 A.8.29, iec62443 SVV-4 |

## 4. Roles and responsibilities

- **IT**: Implements the technical measures and provides evidence from the systems.
- **OT**: Implements the measures in the plants and automation systems.
- **Security Officer**: Maintains the document, oversees its application and reports deviations.

## 5. Procedure steps

### 5.1 Detection

Scans, vendor advisories and intelligence.

{{detalle_deteccion}}

### 5.2 Prioritisation

Deadlines by severity ({{plazos_parcheo}}).

{{detalle_priorizacion}}

### 5.3 Remediation in OT

Maintenance windows and compensating measures.

{{detalle_correccion_en_ot}}

### 5.4 Exceptions

Risk acceptance with an expiry date.

{{detalle_excepciones}}

## 6. Records and evidence

- Scan reports
- Measured deadlines

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
