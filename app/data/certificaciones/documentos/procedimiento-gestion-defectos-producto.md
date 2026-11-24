# Procedimiento de gestión de defectos de seguridad del producto — {{empresa}}

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

Describir cómo se reciben, valoran, corrigen y divulgan los problemas de seguridad de los productos.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `recepcion-notificaciones-vulnerabilidades` | Recepción de avisos de vulnerabilidades del producto | iec62443 DM-1 |
| `gestion-defectos-seguridad-producto` | Gestión de defectos de seguridad del producto | iec62443 DM-2, iec62443 DM-3, iec62443 DM-4, iec62443 DM-6 |
| `divulgacion-vulnerabilidades` | Divulgación coordinada de vulnerabilidades | iec62443 DM-5, nis2 art.21.2.e |

## 4. Funciones y responsabilidades

- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.

## 5. Desarrollo del procedimiento

### 5.1 Recepción

Canal público y acuse.

{{detalle_recepcion}}

### 5.2 Valoración

Gravedad y productos afectados.

{{detalle_valoracion}}

### 5.3 Corrección

Plazos por gravedad.

{{detalle_correccion}}

### 5.4 Divulgación

Aviso coordinado a clientes y autoridades.

{{detalle_divulgacion}}

## 6. Registros y evidencias

- Registro de defectos
- Avisos publicados

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
