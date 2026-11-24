# Product security defect management procedure — {{empresa}}

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

Describe how product security issues are received, assessed, remediated and disclosed.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `recepcion-notificaciones-vulnerabilidades` | Receipt of product vulnerability reports | iec62443 DM-1 |
| `gestion-defectos-seguridad-producto` | Product security defect management | iec62443 DM-2, iec62443 DM-3, iec62443 DM-4, iec62443 DM-6 |
| `divulgacion-vulnerabilidades` | Coordinated vulnerability disclosure | iec62443 DM-5, nis2 art.21.2.e |

## 4. Roles and responsibilities

- **Process owner**: Applies the document within their process and is accountable for its controls.
- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **IT**: Implements the technical measures and provides evidence from the systems.

## 5. Procedure steps

### 5.1 Receipt

Public channel and acknowledgement.

{{detalle_recepcion}}

### 5.2 Assessment

Severity and affected products.

{{detalle_valoracion}}

### 5.3 Correction

Deadlines by severity.

{{detalle_correccion}}

### 5.4 Disclosure

Coordinated notice to customers and authorities.

{{detalle_divulgacion}}

## 6. Records and evidence

- Defect register
- Published advisories

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
