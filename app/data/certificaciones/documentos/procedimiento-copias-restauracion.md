# Procedimiento de copias y restauración — {{empresa}}

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

Describir cómo se hacen, protegen y prueban las copias.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `copias-seguridad` | Copias de seguridad y restauración | iso27001 A.8.13, tisax 5.2.9, nis2 art.21.2.c, iec62443 SR 7.3, iec62443 CR 7.3, sox ITGC-CO-03, jsox ITGC-OPE-03 |
| `preparacion-tic-continuidad` | Continuidad y recuperación de TI y OT | iso27001 A.5.30, tisax 5.2.8, nis2 art.21.2.c, iec62443 SR 7.4, iec62443 CR 7.4, iec62443 SPE 8, sox ITGC-CO-04, jsox ITGC-OPE-04 |

## 4. Funciones y responsabilidades

- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **OT**: Aplica las medidas en las plantas y sistemas de automatización.

## 5. Desarrollo del procedimiento

### 5.1 Política de copias

Qué, cuándo y cuánto se conserva.

{{detalle_politica_de_copias}}

### 5.2 Protección

Cifrado y copia aislada.

{{detalle_proteccion}}

### 5.3 Pruebas de restauración

Frecuencia y criterios.

{{detalle_pruebas_de_restauracion}}

## 6. Registros y evidencias

- Informe de copias
- Pruebas de restauración

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
