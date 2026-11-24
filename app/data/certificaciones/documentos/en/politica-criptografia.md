# Cryptography and key management policy — {{empresa}}

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

Set the algorithms, key lengths and lifecycle of the keys and certificates of {{empresa}}.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `uso-criptografia` | Use of cryptography and key management | iso27001 A.8.24, tisax 5.1.1, nis2 art.21.2.h, iec62443 SR 4.3, iec62443 CR 4.3 |
| `certificados-y-claves-publicas` | Certificates and public-key authentication | iec62443 SR 1.8, iec62443 SR 1.9, iec62443 CR 1.8, iec62443 CR 1.9, iec62443 CR 1.14 |
| `confidencialidad-informacion` | Confidentiality of information at rest and in transit | iec62443 SR 4.1, iec62443 CR 4.1 |
| `proteccion-claves-firma` | Protection of product signing private keys | iso27001 A.8.24, iec62443 SM-8 |

## 4. Roles and responsibilities

- **Security Officer**: Maintains the document, oversees its application and reports deviations.
- **IT**: Implements the technical measures and provides evidence from the systems.

## 5. Guidelines

### 5.1 Approved algorithms

List of algorithms and minimum lengths.

{{detalle_algoritmos_aprobados}}

### 5.2 Encryption at rest and in transit

Where it is mandatory.

{{detalle_cifrado_en_reposo_y_en_transito}}

### 5.3 Key lifecycle

Generation, custody, rotation, revocation and destruction.

{{detalle_ciclo_de_vida_de_claves}}

### 5.4 Product signing keys

Custody in an HSM and dual access.

{{detalle_claves_de_firma_del_producto}}

## 6. Records and evidence

- Inventory of keys and certificates

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
