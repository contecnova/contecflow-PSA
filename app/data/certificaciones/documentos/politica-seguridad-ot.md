# Política de seguridad de los sistemas de automatización — {{empresa}}

| Campo | Valor |
|---|---|
| Tipo | Política |
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

Establecer el programa de seguridad de las plantas y sistemas de automatización de {{empresa}}.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}. Incluye las plantas y sistemas de automatización indicados en {{plantas_ot}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `programa-seguridad-ot` | Programa de seguridad para sistemas de automatización | iec62443 SPE 1 |
| `zonas-y-conductos` | Zonas y conductos | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | Nivel de seguridad objetivo por zona | iec62443 ZCR 5, iec62443 ZCR 6 |
| `acceso-redes-no-confiables` | Acceso desde redes no confiables | iec62443 SR 1.13, iec62443 NDR 1.13 |
| `gestion-eventos-ot` | Gestión de eventos e incidentes en planta | iec62443 SPE 7 |

## 4. Funciones y responsabilidades

- **Dirección**: Aprueba el documento y asigna los recursos necesarios.
- **OT**: Aplica las medidas en las plantas y sistemas de automatización.
- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.

## 5. Directrices

### 5.1 Organización OT

Responsables por planta y relación con seguridad corporativa.

{{detalle_organizacion_ot}}

### 5.2 Zonas y conductos

Criterios de partición y SL objetivo por zona.

{{detalle_zonas_y_conductos}}

### 5.3 Acceso remoto

Condiciones y aprobación del acceso de proveedores.

{{detalle_acceso_remoto}}

### 5.4 Cambios y parches

Ventanas de mantenimiento y pruebas previas.

{{detalle_cambios_y_parches}}

### 5.5 Incidentes en planta

Coordinación con la respuesta corporativa.

{{detalle_incidentes_en_planta}}

## 6. Registros y evidencias

- Registro de zonas y SL

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
