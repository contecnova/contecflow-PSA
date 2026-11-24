# Product security updates procedure — {{empresa}}

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

Describe the qualification, documentation and delivery of security updates.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `actualizaciones-seguridad-producto` | Product security updates | iec62443 SUM-1, iec62443 SUM-2, iec62443 SUM-3, iec62443 SUM-4, iec62443 SUM-5, iec62443 EDR 3.10, iec62443 HDR 3.10, iec62443 NDR 3.10 |
| `sbom-y-versiones-firmadas` | SBOM and tagged and signed releases | iec62443 SM-9, iec62443 SUM-3 |
| `integridad-artefactos-desarrollo` | Integrity of development artefacts | iso27001 A.8.4, iec62443 SM-6 |

## 4. Roles and responsibilities

- **Process owner**: Applies the document within their process and is accountable for its controls.
- **IT**: Implements the technical measures and provides evidence from the systems.

## 5. Procedure steps

### 5.1 Qualification

Testing before publication.

{{detalle_cualificacion}}

### 5.2 Documentation

Notes and dependent components.

{{detalle_documentacion}}

### 5.3 Delivery

Signature and verification by the customer.

{{detalle_entrega}}

### 5.4 Deadlines

Delivery commitments.

{{detalle_plazos}}

## 6. Records and evidence

- Release notes
- SBOM

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
