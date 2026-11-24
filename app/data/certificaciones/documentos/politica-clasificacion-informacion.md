# Política de clasificación y tratamiento de la información — {{empresa}}

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

Definir los niveles de clasificación de {{empresa}} y cómo se trata la información de cada nivel.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `clasificacion-informacion` | Clasificación de la información | iso27001 A.5.12, tisax 1.3.2, iec62443 SPE 5 |
| `etiquetado-informacion` | Etiquetado de la información | iso27001 A.5.13, tisax 1.3.2 |
| `transferencia-informacion` | Intercambio de información | iso27001 A.5.14, tisax 5.1.2 |
| `borrado-informacion` | Borrado de información y persistencia | iso27001 A.8.10, tisax 5.3.3, iec62443 SR 4.2, iec62443 CR 4.2 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.

## 5. Directrices

### 5.1 Niveles

Defina los niveles ({{niveles_clasificacion}}) y criterios de asignación.

{{detalle_niveles}}

### 5.2 Etiquetado

Cómo se marca cada nivel en documentos, correos y sistemas.

{{detalle_etiquetado}}

### 5.3 Tratamiento

Almacenamiento, transmisión, impresión y destrucción por nivel.

{{detalle_tratamiento}}

### 5.4 Información de clientes

Cómo se respeta la clasificación que imponen los clientes.

{{detalle_informacion_de_clientes}}

## 6. Registros y evidencias

- Inventario con clasificación

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
