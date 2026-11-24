# Procedimiento de notificación de incidentes significativos (NIS2) — {{empresa}}

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

Garantizar que {{empresa}} notifica en plazo los incidentes significativos al CSIRT o a la autoridad competente ({{autoridad_nis2}}).

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `notificacion-incidentes-significativos` | Notificación de incidentes significativos | nis2 art.23.1, nis2 art.23.3 |
| `alerta-temprana-24h` | Alerta temprana en 24 horas | nis2 art.23.4.a |
| `notificacion-incidente-72h` | Notificación del incidente en 72 horas | nis2 art.23.4.b |
| `informe-intermedio-incidente` | Informe intermedio a petición | nis2 art.23.4.c |
| `informe-final-incidente` | Informe final en un mes | nis2 art.23.4.d, nis2 art.23.4.e |
| `comunicacion-destinatarios-servicio` | Comunicación a los destinatarios del servicio | nis2 art.23.1, nis2 art.23.2 |
| `contacto-autoridades` | Relación con autoridades | iso27001 A.5.5, nis2 art.23.1 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Responsable de cumplimiento**: Coordina las evidencias y su relación con cada norma.
- **Dirección**: Aprueba el documento y asigna los recursos necesarios.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.

## 5. Desarrollo del procedimiento

### 5.1 Determinación del incidente significativo

Criterios y quién decide; hora de conocimiento.

{{detalle_determinacion_del_incidente_significativ}}

### 5.2 Alerta temprana (24 h)

Contenido mínimo y canal.

{{detalle_alerta_temprana_24_h}}

### 5.3 Notificación (72 h)

Evaluación inicial, gravedad, impacto e indicadores de compromiso.

{{detalle_notificacion_72_h}}

### 5.4 Informe intermedio

A petición de la autoridad.

{{detalle_informe_intermedio}}

### 5.5 Informe final (1 mes)

Descripción, causa, medidas y efecto transfronterizo; informe de situación si sigue en curso.

{{detalle_informe_final_1_mes}}

### 5.6 Comunicación a destinatarios

Cuándo y cómo se informa a clientes.

{{detalle_comunicacion_a_destinatarios}}

## 6. Registros y evidencias

- Registro de notificaciones con sellos de tiempo

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
