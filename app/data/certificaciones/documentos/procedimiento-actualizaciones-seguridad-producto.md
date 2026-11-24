# Procedimiento de actualizaciones de seguridad del producto — {{empresa}}

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

Describir la cualificación, documentación y entrega de actualizaciones de seguridad.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `actualizaciones-seguridad-producto` | Actualizaciones de seguridad del producto | iec62443 SUM-1, iec62443 SUM-2, iec62443 SUM-3, iec62443 SUM-4, iec62443 SUM-5, iec62443 EDR 3.10, iec62443 HDR 3.10, iec62443 NDR 3.10 |
| `sbom-y-versiones-firmadas` | SBOM y versiones etiquetadas y firmadas | iec62443 SM-9, iec62443 SUM-3 |
| `integridad-artefactos-desarrollo` | Integridad de los artefactos de desarrollo | iso27001 A.8.4, iec62443 SM-6 |

## 4. Funciones y responsabilidades

- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.

## 5. Desarrollo del procedimiento

### 5.1 Cualificación

Pruebas antes de publicar.

{{detalle_cualificacion}}

### 5.2 Documentación

Notas y componentes dependientes.

{{detalle_documentacion}}

### 5.3 Entrega

Firma y verificación por el cliente.

{{detalle_entrega}}

### 5.4 Plazos

Compromisos de entrega.

{{detalle_plazos}}

## 6. Registros y evidencias

- Notas de versión
- SBOM

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
