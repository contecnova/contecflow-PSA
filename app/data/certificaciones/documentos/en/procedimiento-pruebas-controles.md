# Control testing procedure (SOX and J-SOX) — {{empresa}}

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

Describe how the design and operating effectiveness of controls are tested.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `evaluacion-direccion-control-interno` | Management assessment of internal control over financial reporting | sox Sec.404(a), jsox FIEA-24-4-4 |
| `evaluacion-deficiencias-control` | Evaluation and communication of control deficiencies | sox ELC-04, jsox ELC-04 |
| `controles-aplicacion` | Automated application controls | sox ITAC-01, jsox ITAC-01 |
| `independencia-probadores` | Independence of the tester | iec62443 SVV-5 |

## 4. Roles and responsibilities

- **Internal audit**: Independently verifies that it is applied.
- **Finance**: Owns the controls over financial information.
- **Process owner**: Applies the document within their process and is accountable for its controls.

## 5. Procedure steps

### 5.1 Design test

Walkthrough and adequacy of the design.

{{detalle_prueba_de_diseno}}

### 5.2 Effectiveness test

Population, sample size according to control frequency, and result.

{{detalle_prueba_de_eficacia}}

### 5.3 Independence

The tester did not implement and does not perform the control.

{{detalle_independencia}}

### 5.4 Deficiencies

Evaluation and aggregation.

{{detalle_deficiencias}}

## 6. Records and evidence

- Test working papers

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
