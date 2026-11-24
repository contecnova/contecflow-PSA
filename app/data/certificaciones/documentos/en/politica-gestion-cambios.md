# Change management policy — {{empresa}}

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

Ensure that every change to the systems and infrastructure of {{empresa}} is assessed, tested and approved independently.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `gestion-cambios` | Change management | iso27001 A.8.32, tisax 5.2.1, nis2 art.21.2.e, sox ITGC-PC-01, jsox ITGC-DES-05 |
| `pruebas-cambios` | Testing of changes | iso27001 A.8.32, sox ITGC-PC-02, jsox ITGC-DES-02 |
| `aprobacion-independiente-paso-produccion` | Independent approval of production release | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `cambios-emergencia` | Emergency changes | iso27001 A.8.32, sox ITGC-PC-05, jsox ITGC-DES-05 |
| `separacion-entornos` | Environment separation and development environment security | iso27001 A.8.31, tisax 5.2.2, iec62443 SM-7, sox ITGC-PC-04, jsox ITGC-DES-04 |

## 4. Roles and responsibilities

- **IT**: Implements the technical measures and provides evidence from the systems.
- **Process owner**: Applies the document within their process and is accountable for its controls.
- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Internal audit**: Independently verifies that it is applied.

## 5. Guidelines

### 5.1 Change types

Standard, normal and emergency.

{{detalle_tipos_de_cambio}}

### 5.2 Assessment and CAB

Risk criteria and committee composition.

{{detalle_evaluacion_y_cab}}

### 5.3 Segregation

The author does not approve or release their own change to production.

{{detalle_segregacion}}

### 5.4 Emergencies

Retrospective approval within the deadline.

{{detalle_emergencias}}

## 6. Records and evidence

- Change log

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
