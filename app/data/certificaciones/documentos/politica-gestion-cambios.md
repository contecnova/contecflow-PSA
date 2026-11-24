# Política de gestión de cambios — {{empresa}}

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

Asegurar que todo cambio en sistemas e infraestructuras de {{empresa}} se evalúa, prueba y aprueba de forma independiente.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `gestion-cambios` | Gestión de cambios | iso27001 A.8.32, tisax 5.2.1, nis2 art.21.2.e, sox ITGC-PC-01, jsox ITGC-DES-05 |
| `pruebas-cambios` | Pruebas de los cambios | iso27001 A.8.32, sox ITGC-PC-02, jsox ITGC-DES-02 |
| `aprobacion-independiente-paso-produccion` | Aprobación independiente del paso a producción | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `cambios-emergencia` | Cambios de emergencia | iso27001 A.8.32, sox ITGC-PC-05, jsox ITGC-DES-05 |
| `separacion-entornos` | Separación de entornos y seguridad del entorno de desarrollo | iso27001 A.8.31, tisax 5.2.2, iec62443 SM-7, sox ITGC-PC-04, jsox ITGC-DES-04 |

## 4. Funciones y responsabilidades

- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Auditoría interna**: Comprueba de forma independiente que se aplica.

## 5. Directrices

### 5.1 Tipos de cambio

Estándar, normal y de emergencia.

{{detalle_tipos_de_cambio}}

### 5.2 Evaluación y CAB

Criterios de riesgo y composición del comité.

{{detalle_evaluacion_y_cab}}

### 5.3 Segregación

El autor no aprueba ni pasa a producción su propio cambio.

{{detalle_segregacion}}

### 5.4 Emergencias

Aprobación a posteriori en plazo.

{{detalle_emergencias}}

## 6. Registros y evidencias

- Registro de cambios

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
