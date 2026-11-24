# Política de desarrollo seguro — {{empresa}}

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

Integrar la seguridad en el ciclo de vida del software y los dispositivos que desarrolla {{empresa}}.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `ciclo-desarrollo-seguro` | Ciclo de vida de desarrollo seguro | iso27001 A.8.25, tisax 5.3.1, nis2 art.21.2.e, iec62443 SM-1, sox ITGC-PD-01, jsox ITGC-DES-01 |
| `requisitos-seguridad-aplicaciones` | Requisitos de seguridad de las aplicaciones y productos | iso27001 A.8.26, tisax 5.3.1, iec62443 SR-3, iec62443 SR-4, iec62443 SR-5 |
| `codificacion-segura` | Codificación segura | iso27001 A.8.28, iec62443 SI-2 |
| `pruebas-seguridad` | Pruebas de seguridad en desarrollo y aceptación | iso27001 A.8.29, iec62443 SVV-1, iec62443 SVV-2, iec62443 SVV-3 |
| `separacion-entornos` | Separación de entornos y seguridad del entorno de desarrollo | iso27001 A.8.31, tisax 5.2.2, iec62443 SM-7, sox ITGC-PC-04, jsox ITGC-DES-04 |
| `aprobacion-independiente-paso-produccion` | Aprobación independiente del paso a producción | iso27001 A.8.32, sox ITGC-PC-03, sox ITGC-PD-04, jsox ITGC-DES-05 |
| `sbom-y-versiones-firmadas` | SBOM y versiones etiquetadas y firmadas | iec62443 SM-9, iec62443 SUM-3 |

## 4. Funciones y responsabilidades

- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **Auditoría interna**: Comprueba de forma independiente que se aplica.

## 5. Directrices

### 5.1 Proceso

Fases del ciclo y prácticas de seguridad en cada una.

{{detalle_proceso}}

### 5.2 Requisitos y amenazas

Requisitos de seguridad y modelado de amenazas.

{{detalle_requisitos_y_amenazas}}

### 5.3 Revisión independiente por versión

Quien escribe el cambio no lo aprueba para producción.

{{detalle_revision_independiente_por_version}}

### 5.4 Pruebas

Análisis estático, dependencias, pruebas de seguridad e intrusión.

{{detalle_pruebas}}

### 5.5 Publicación

SBOM, etiquetado y firma de cada versión.

{{detalle_publicacion}}

## 6. Registros y evidencias

- Evidencias de revisión por versión
- SBOM

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
