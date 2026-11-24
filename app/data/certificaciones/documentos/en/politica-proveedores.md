# Supplier security policy — {{empresa}}

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

Ensure that the suppliers of {{empresa}} protect information and services according to their criticality.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `seguridad-proveedores` | Security in supplier relationships | iso27001 A.5.19, tisax 6.1.1, nis2 art.21.2.d, iec62443 SPE 1 |
| `acuerdos-proveedores` | Security requirements in contracts | iso27001 A.5.20, tisax 1.2.4, tisax 6.1.1, nis2 art.21.2.d |
| `cadena-suministro-tic` | ICT supply chain security | iso27001 A.5.21, nis2 art.21.2.d, nis2 art.21.3, iec62443 SM-9 |
| `seguimiento-proveedores` | Monitoring of supplier services and assurance reports | iso27001 A.5.22, tisax 6.1.1, sox ITGC-CO-05, jsox ITGC-EXT-01 |
| `servicios-nube` | Secure use of cloud and external services | iso27001 A.5.23, tisax 1.3.3, tisax 5.3.3, tisax 5.3.4 |

## 4. Roles and responsibilities

- **Compliance Officer**: Coordinates the evidence and its mapping to each standard.
- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **Finance**: Owns the controls over financial information.
- **Supplier**: Meets the contractual requirements and provides its assurance reports.

## 5. Guidelines

### 5.1 Supplier classification

Criticality criteria, including direct ICT suppliers.

{{detalle_clasificacion_de_proveedores}}

### 5.2 Prior assessment

Questionnaire, TISAX labels, certificates and SOC reports.

{{detalle_evaluacion_previa}}

### 5.3 Contractual clauses

Security, confidentiality, incident notification, audit and exit.

{{detalle_clausulas_contractuales}}

### 5.4 Follow-up

Periodic review and management of service changes.

{{detalle_seguimiento}}

### 5.5 Exit

Return and deletion of information.

{{detalle_salida}}

## 6. Records and evidence

- Critical suppliers record
- Assessments

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
