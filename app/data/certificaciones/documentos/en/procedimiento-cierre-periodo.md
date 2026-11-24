# Accounting period close procedure — {{empresa}}

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

Describe the period close of {{empresa}} and the subsequent lock against modifications.

## 2. Scope

This applies to {{alcance}} of {{empresa}}, including the sites {{sedes}}.

## 3. Controls covered

| Common control | Title | Mappings |
|---|---|---|
| `cierre-periodos-contables` | Accounting period close | sox FC-01, jsox FCRP-01 |
| `asientos-manuales` | Manual journal entries | sox FC-02, jsox FCRP-02 |
| `conciliaciones-cuentas` | Account reconciliations | sox FC-03, jsox FCRP-03 |
| `hojas-calculo-criticas` | Critical spreadsheets and end-user tools | sox FC-04, jsox FCRP-04 |
| `informacion-generada-por-entidad` | Accuracy and completeness of system reports | sox FC-05, jsox FCRP-05 |

## 4. Roles and responsibilities

- **Finance**: Owns the controls over financial information.
- **IT**: Implements the technical measures and provides evidence from the systems.
- **Internal audit**: Independently verifies that it is applied.

## 5. Procedure steps

### 5.1 Close calendar

Milestones per entity.

{{detalle_calendario_de_cierre}}

### 5.2 Manual journal entries

Preparation, review and approval by different people.

{{detalle_asientos_manuales}}

### 5.3 Reconciliations

Accounts and frequency.

{{detalle_conciliaciones}}

### 5.4 Lock and reopening

Authorisation and logging of any reopening.

{{detalle_bloqueo_y_reapertura}}

## 6. Records and evidence

- Calendar
- Reopening log

## 7. Non-compliance

Non-compliance with this document is handled in accordance with the disciplinary process and the nonconformity process of {{empresa}}.

## 8. Change control

| Version | Date | Author | Approver | Changes |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Initial version |
