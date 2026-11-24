# Change and production release procedure — {{empresa}}

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

Describe the flow of a change from the request to its post-implementation review.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `gestion-cambios` | Change management | iso27001 A.8.32, tisax 5.2.1, nis2 art.21.2.e, sox ITGC-PC-01, jsox ITGC-DES-05 |
| `pruebas-cambios` | Testing of changes | iso27001 A.8.32, sox ITGC-PC-02, jsox ITGC-DES-02 |
| `aprobacion-independiente-paso-produccion` | Independent approval of production release | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `cambios-emergencia` | Emergency changes | iso27001 A.8.32, sox ITGC-PC-05, jsox ITGC-DES-05 |
| `gestion-configuracion` | Configuration management | iso27001 A.8.9, iec62443 SR 7.6, iec62443 CR 7.6, iec62443 SPE 2, sox ITGC-PC-06, jsox ITGC-DES-06 |

## 4. Roles and responsibilities

- **IT**: Implements the technical measures and provides evidence from the systems.
- **Process owner**: Applies the document within their process and is accountable for its controls.
- **Internal audit**: Independently verifies that it is applied.

## 5. Procedure steps

### 5.1 Request

Minimum data and classification.

{{detalle_solicitud}}

### 5.2 Assessment and approval

CAB and independent approval per release.

{{detalle_evaluacion_y_aprobacion}}

### 5.3 Testing

Environment and evidence.

{{detalle_pruebas}}

### 5.4 Production release

Who performs it and how it is recorded.

{{detalle_paso_a_produccion}}

### 5.5 Post-implementation review

PIR where applicable.

{{detalle_revision_posterior}}

## 6. Records and evidence

- Change log

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
