# Política de continuidad y recuperación — {{empresa}}

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

Asegurar que {{empresa}} mantiene y recupera sus servicios críticos con el nivel de seguridad necesario.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `preparacion-tic-continuidad` | Continuidad y recuperación de TI y OT | iso27001 A.5.30, tisax 5.2.8, nis2 art.21.2.c, iec62443 SR 7.4, iec62443 CR 7.4, iec62443 SPE 8, sox ITGC-CO-04, jsox ITGC-OPE-04 |
| `seguridad-durante-interrupcion` | Seguridad durante una interrupción | iso27001 A.5.29, nis2 art.21.2.c |
| `gestion-crisis` | Gestión de crisis | tisax 1.6.3, nis2 art.21.2.c |
| `copias-seguridad` | Copias de seguridad y restauración | iso27001 A.8.13, tisax 5.2.9, nis2 art.21.2.c, iec62443 SR 7.3, iec62443 CR 7.3, sox ITGC-CO-03, jsox ITGC-OPE-03 |
| `redundancia` | Redundancia de instalaciones de tratamiento | iso27001 A.8.14, tisax 5.2.8 |

## 4. Funciones y responsabilidades

- **Dirección**: Aprueba el documento y asigna los recursos necesarios.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **OT**: Aplica las medidas en las plantas y sistemas de automatización.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.

## 5. Directrices

### 5.1 Análisis de impacto

Servicios críticos, RTO y RPO.

{{detalle_analisis_de_impacto}}

### 5.2 Estrategias

Redundancia, copias y sitios alternativos.

{{detalle_estrategias}}

### 5.3 Gestión de crisis

Comité, activación y comunicación.

{{detalle_gestion_de_crisis}}

### 5.4 Pruebas

Calendario y criterios de éxito.

{{detalle_pruebas}}

## 6. Registros y evidencias

- BIA
- Informes de pruebas

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
