# Procedimiento de gestión de incidentes — {{empresa}}

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

Describir cómo se comunican, clasifican, responden y cierran los incidentes de seguridad en {{empresa}}.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `preparacion-gestion-incidentes` | Preparación para la gestión de incidentes | iso27001 A.5.24, tisax 1.6.1, nis2 art.21.2.b, iec62443 SPE 7 |
| `evaluacion-eventos` | Evaluación y clasificación de eventos | iso27001 A.5.25, tisax 1.6.2, nis2 art.23.3 |
| `respuesta-incidentes` | Respuesta a incidentes | iso27001 A.5.26, tisax 1.6.2, nis2 art.21.2.b |
| `lecciones-incidentes` | Aprendizaje de los incidentes | iso27001 A.5.27, tisax 1.6.2 |
| `recogida-evidencias` | Recogida y custodia de evidencias | iso27001 A.5.28 |
| `notificacion-eventos` | Comunicación de eventos por el personal | iso27001 A.6.8, tisax 1.6.1 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **OT**: Aplica las medidas en las plantas y sistemas de automatización.
- **Responsable de cumplimiento**: Coordina las evidencias y su relación con cada norma.

## 5. Desarrollo del procedimiento

### 5.1 Comunicación

Canales y datos mínimos.

{{detalle_comunicacion}}

### 5.2 Clasificación

Criterios de gravedad y de incidente significativo.

{{detalle_clasificacion}}

### 5.3 Respuesta

Contención, erradicación y recuperación.

{{detalle_respuesta}}

### 5.4 Evidencias

Recogida y custodia.

{{detalle_evidencias}}

### 5.5 Cierre y lecciones

Informe post-incidente y mejoras.

{{detalle_cierre_y_lecciones}}

## 6. Registros y evidencias

- Tickets de incidentes
- Informes post-incidente

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
