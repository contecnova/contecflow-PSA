# Procedimiento de zonas, conductos y nivel de seguridad — {{empresa}}

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

Describir cómo {{empresa}} parte sus sistemas de planta en zonas y conductos y fija el SL objetivo por zona.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}. Incluye las plantas y sistemas de automatización indicados en {{plantas_ot}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `sistema-bajo-consideracion` | Definición del sistema bajo consideración | iec62443 ZCR 1 |
| `evaluacion-riesgos-ot` | Evaluación de riesgos de ciberseguridad OT | iec62443 ZCR 2, iec62443 ZCR 4, iec62443 ZCR 5, iec62443 SPE 1 |
| `zonas-y-conductos` | Zonas y conductos | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | Nivel de seguridad objetivo por zona | iec62443 ZCR 5, iec62443 ZCR 6 |
| `especificacion-requisitos-ciberseguridad` | Especificación de requisitos de ciberseguridad del sistema | iec62443 ZCR 6 |
| `aprobacion-propietario-activo` | Aprobación por el propietario del activo | iec62443 ZCR 7 |

## 4. Funciones y responsabilidades

- **OT**: Aplica las medidas en las plantas y sistemas de automatización.
- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.

## 5. Desarrollo del procedimiento

### 5.1 Sistema bajo consideración

Fronteras e inventario.

{{detalle_sistema_bajo_consideracion}}

### 5.2 Evaluación inicial

Riesgo sin contramedidas.

{{detalle_evaluacion_inicial}}

### 5.3 Partición

Criterios de agrupación y reflejo en la CMDB.

{{detalle_particion}}

### 5.4 Evaluación detallada y SL-T

Por zona y conducto.

{{detalle_evaluacion_detallada_y_sl_t}}

### 5.5 Requisitos y aprobación

Especificación y firma del propietario.

{{detalle_requisitos_y_aprobacion}}

## 6. Registros y evidencias

- Registro de zonas y SL

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
