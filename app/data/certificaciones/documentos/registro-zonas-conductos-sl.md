# Registro de zonas, conductos y niveles de seguridad — {{empresa}}

| Campo | Valor |
|---|---|
| Tipo | Registro |
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

Recoger las zonas y conductos de cada planta con su SL objetivo y alcanzado.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}. Incluye las plantas y sistemas de automatización indicados en {{plantas_ot}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `zonas-y-conductos` | Zonas y conductos | iec62443 ZCR 3, iec62443 SPE 3 |
| `nivel-seguridad-objetivo-por-zona` | Nivel de seguridad objetivo por zona | iec62443 ZCR 5, iec62443 ZCR 6 |

## 4. Funciones y responsabilidades

- **OT**: Aplica las medidas en las plantas y sistemas de automatización.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Planta | Sede | Sí |
| Zona o conducto | Identificador | Sí |
| Activos | Referencias de la CMDB | Sí |
| SL objetivo | SL1–SL4 | Sí |
| SL alcanzado | SL1–SL4 | Sí |
| Brecha y medidas | Descripción | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
