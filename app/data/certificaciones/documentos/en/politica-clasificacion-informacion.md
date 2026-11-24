# Information classification and handling policy — {{empresa}}

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

Define the classification levels of {{empresa}} and how information at each level is handled.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `clasificacion-informacion` | Information classification | iso27001 A.5.12, tisax 1.3.2, iec62443 SPE 5 |
| `etiquetado-informacion` | Information labelling | iso27001 A.5.13, tisax 1.3.2 |
| `transferencia-informacion` | Information exchange | iso27001 A.5.14, tisax 5.1.2 |
| `borrado-informacion` | Information deletion and persistence | iso27001 A.8.10, tisax 5.3.3, iec62443 SR 4.2, iec62443 CR 4.2 |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Process owner**: Applies the document within their process and is accountable for its controls.
- **IT**: Implements the technical measures and provides evidence from the systems.

## 5. Guidelines

### 5.1 Levels

Define the levels ({{niveles_clasificacion}}) and the assignment criteria.

{{detalle_niveles}}

### 5.2 Labelling

How each level is marked in documents, emails and systems.

{{detalle_etiquetado}}

### 5.3 Handling

Storage, transmission, printing and destruction by level.

{{detalle_tratamiento}}

### 5.4 Customer information

How the classification imposed by customers is respected.

{{detalle_informacion_de_clientes}}

## 6. Records and evidence

- Inventory with classification

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
