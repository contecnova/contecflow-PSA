# Procedimiento de gestión de vulnerabilidades — {{empresa}}

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

Describir cómo se detectan, priorizan y corrigen las vulnerabilidades técnicas en TI y OT.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `gestion-vulnerabilidades-tecnicas` | Gestión de vulnerabilidades técnicas | iso27001 A.8.8, tisax 5.2.5, nis2 art.21.2.e, iec62443 SPE 4, iec62443 SPE 8 |
| `inteligencia-amenazas` | Inteligencia de amenazas | iso27001 A.5.7, nis2 art.21.2.e |
| `pruebas-intrusion` | Pruebas de intrusión | iso27001 A.8.8, iso27001 A.8.29, iec62443 SVV-4 |

## 4. Funciones y responsabilidades

- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **OT**: Aplica las medidas en las plantas y sistemas de automatización.
- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.

## 5. Desarrollo del procedimiento

### 5.1 Detección

Escaneos, avisos de fabricantes e inteligencia.

{{detalle_deteccion}}

### 5.2 Priorización

Plazos por gravedad ({{plazos_parcheo}}).

{{detalle_priorizacion}}

### 5.3 Corrección en OT

Ventanas de mantenimiento y medidas compensatorias.

{{detalle_correccion_en_ot}}

### 5.4 Excepciones

Aceptación de riesgo con caducidad.

{{detalle_excepciones}}

## 6. Registros y evidencias

- Informes de escaneo
- Plazos medidos

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
