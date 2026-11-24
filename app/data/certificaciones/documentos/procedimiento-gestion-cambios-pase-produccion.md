# Procedimiento de cambios y paso a producción — {{empresa}}

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

Describir el flujo de un cambio desde la solicitud hasta su revisión posterior.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `gestion-cambios` | Gestión de cambios | iso27001 A.8.32, tisax 5.2.1, nis2 art.21.2.e, sox ITGC-PC-01, jsox ITGC-DES-05 |
| `pruebas-cambios` | Pruebas de los cambios | iso27001 A.8.32, sox ITGC-PC-02, jsox ITGC-DES-02 |
| `aprobacion-independiente-paso-produccion` | Aprobación independiente del paso a producción | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `cambios-emergencia` | Cambios de emergencia | iso27001 A.8.32, sox ITGC-PC-05, jsox ITGC-DES-05 |
| `gestion-configuracion` | Gestión de la configuración | iso27001 A.8.9, iec62443 SR 7.6, iec62443 CR 7.6, iec62443 SPE 2, sox ITGC-PC-06, jsox ITGC-DES-06 |

## 4. Funciones y responsabilidades

- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **Auditoría interna**: Comprueba de forma independiente que se aplica.

## 5. Desarrollo del procedimiento

### 5.1 Solicitud

Datos mínimos y clasificación.

{{detalle_solicitud}}

### 5.2 Evaluación y aprobación

CAB y aprobación independiente por versión.

{{detalle_evaluacion_y_aprobacion}}

### 5.3 Pruebas

Entorno y evidencias.

{{detalle_pruebas}}

### 5.4 Paso a producción

Quién lo ejecuta y cómo se registra.

{{detalle_paso_a_produccion}}

### 5.5 Revisión posterior

PIR cuando proceda.

{{detalle_revision_posterior}}

## 6. Registros y evidencias

- Registro de cambios

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
