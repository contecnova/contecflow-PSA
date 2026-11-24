# Secure development policy — {{empresa}}

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

Integrate security into the lifecycle of the software and devices developed by {{empresa}}.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `ciclo-desarrollo-seguro` | Secure development lifecycle | iso27001 A.8.25, tisax 5.3.1, nis2 art.21.2.e, iec62443 SM-1, sox ITGC-PD-01, jsox ITGC-DES-01 |
| `requisitos-seguridad-aplicaciones` | Security requirements for applications and products | iso27001 A.8.26, tisax 5.3.1, iec62443 SR-3, iec62443 SR-4, iec62443 SR-5 |
| `codificacion-segura` | Secure coding | iso27001 A.8.28, iec62443 SI-2 |
| `pruebas-seguridad` | Security testing in development and acceptance | iso27001 A.8.29, iec62443 SVV-1, iec62443 SVV-2, iec62443 SVV-3 |
| `separacion-entornos` | Environment separation and development environment security | iso27001 A.8.31, tisax 5.2.2, iec62443 SM-7, sox ITGC-PC-04, jsox ITGC-DES-04 |
| `aprobacion-independiente-paso-produccion` | Independent approval of production release | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `sbom-y-versiones-firmadas` | SBOM and tagged and signed releases | iec62443 SM-9, iec62443 SUM-3 |

## 4. Roles and responsibilities

- **Process owner**: Applies the document within their process and is accountable for its controls.
- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **IT**: Implements the technical measures and provides evidence from the systems.
- **Internal audit**: Independently verifies that it is applied.

## 5. Guidelines

### 5.1 Process

Lifecycle phases and the security practices in each.

{{detalle_proceso}}

### 5.2 Requirements and threats

Security requirements and threat modelling.

{{detalle_requisitos_y_amenazas}}

### 5.3 Independent review per release

The person who writes the change does not approve it for production.

{{detalle_revision_independiente_por_version}}

### 5.4 Testing

Static analysis, dependencies, security testing and penetration testing.

{{detalle_pruebas}}

### 5.5 Publication

SBOM, tagging and signing of each release.

{{detalle_publicacion}}

## 6. Records and evidence

- Review evidence per release
- SBOM

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
