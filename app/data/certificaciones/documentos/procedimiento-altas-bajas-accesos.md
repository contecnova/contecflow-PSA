# Procedimiento de altas, cambios y bajas de accesos — {{empresa}}

| Campo | Valor |
|---|---|
| Tipo | Procedimiento |
| Código | {{codigo_documento}} |
| Versión | {{version}} |
| Propietario | {{propietario}} |
| Aprobado por | {{aprobador}} (flujo de aprobación de Documentos) |
| Fecha de aprobación | {{fecha_aprobacion}} |
| Próxima revisión | {{fecha_revision}} |
| Clasificación | {{clasificacion}} |
| Alcance | {{alcance}} |

> Plantilla redactada por contecflow. Sustituya los marcadores `{{...}}` y adapte el contenido a su organización. No incluye texto de normas con derechos de autor; si su empresa tiene licencia, puede importar el texto oficial en el catálogo.

## 1. Objeto

Describir cómo se solicitan, aprueban, aplican y retiran los accesos.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `alta-modificacion-accesos` | Alta y modificación de accesos con aprobación | iso27001 A.5.18, tisax 4.2.1, sox ITGC-APD-01, jsox ITGC-SEG-01 |
| `baja-accesos` | Retirada oportuna de accesos | iso27001 A.5.18, sox ITGC-APD-02, jsox ITGC-SEG-02 |
| `gestion-identidades` | Ciclo de vida de identidades | iso27001 A.5.16, tisax 4.1.1, tisax 4.1.3, iec62443 SR 1.1, iec62443 SR 1.3, iec62443 SR 1.4, iec62443 CR 1.1, iec62443 CR 1.3, iec62443 CR 1.4, iec62443 SG-6 |
| `cuentas-servicio-y-dispositivos` | Cuentas de servicio, genéricas y de dispositivos | iec62443 SR 1.2, iec62443 CR 1.2, sox ITGC-APD-08, jsox ITGC-SEG-08 |

## 4. Funciones y responsabilidades

- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **RR. HH.**: Integra los requisitos en los procesos de personas.

## 5. Desarrollo del procedimiento

### 5.1 Solicitud y aprobación

Quién solicita y quién aprueba.

{{detalle_solicitud_y_aprobacion}}

### 5.2 Aplicación

Plazos y comprobaciones.

{{detalle_aplicacion}}

### 5.3 Cambio de puesto y baja

Origen en RR. HH. y plazo máximo ({{plazo_baja}}).

{{detalle_cambio_de_puesto_y_baja}}

### 5.4 Cuentas de servicio

Responsable y rotación de secretos.

{{detalle_cuentas_de_servicio}}

## 6. Registros y evidencias

- Solicitudes aprobadas
- Informe de bajas

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
