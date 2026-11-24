# Access provisioning, change and removal procedure — {{empresa}}

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

Describe how access is requested, approved, granted and removed.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `alta-modificacion-accesos` | Provisioning and modification of access with approval | iso27001 A.5.18, tisax 4.2.1, sox ITGC-APD-01, jsox ITGC-SEG-01 |
| `baja-accesos` | Timely removal of access | iso27001 A.5.18, sox ITGC-APD-02, jsox ITGC-SEG-02 |
| `gestion-identidades` | Identity lifecycle | iso27001 A.5.16, tisax 4.1.1, tisax 4.1.3, iec62443 SR 1.1, iec62443 SR 1.3, iec62443 SR 1.4, iec62443 CR 1.1, iec62443 CR 1.3, iec62443 CR 1.4, iec62443 SG-6 |
| `cuentas-servicio-y-dispositivos` | Service, generic and device accounts | iec62443 SR 1.2, iec62443 CR 1.2, sox ITGC-APD-08, jsox ITGC-SEG-08 |

## 4. Roles and responsibilities

- **IT**: Implements the technical measures and provides evidence from the systems.
- **Process owner**: Applies the document within their process and is accountable for its controls.
- **HR**: Integrates the requirements into people processes.

## 5. Procedure steps

### 5.1 Request and approval

Who requests and who approves.

{{detalle_solicitud_y_aprobacion}}

### 5.2 Application

Deadlines and checks.

{{detalle_aplicacion}}

### 5.3 Role change and leaving

Trigger from HR and maximum deadline ({{plazo_baja}}).

{{detalle_cambio_de_puesto_y_baja}}

### 5.4 Service accounts

Owner and rotation of secrets.

{{detalle_cuentas_de_servicio}}

## 6. Records and evidence

- Approved requests
- Leavers report

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
