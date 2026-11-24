# Política criptográfica y de gestión de claves — {{empresa}}

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

Fijar los algoritmos, longitudes y ciclo de vida de claves y certificados de {{empresa}}.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `uso-criptografia` | Uso de la criptografía y gestión de claves | iso27001 A.8.24, tisax 5.1.1, nis2 art.21.2.h, iec62443 SR 4.3, iec62443 CR 4.3 |
| `certificados-y-claves-publicas` | Certificados y autenticación por clave pública | iec62443 SR 1.8, iec62443 SR 1.9, iec62443 CR 1.8, iec62443 CR 1.9, iec62443 CR 1.14 |
| `confidencialidad-informacion` | Confidencialidad de la información en reposo y en tránsito | iec62443 SR 4.1, iec62443 CR 4.1 |
| `proteccion-claves-firma` | Protección de claves privadas de firma del producto | iso27001 A.8.24, iec62443 SM-8 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.

## 5. Directrices

### 5.1 Algoritmos aprobados

Lista de algoritmos y longitudes mínimas.

{{detalle_algoritmos_aprobados}}

### 5.2 Cifrado en reposo y en tránsito

Dónde es obligatorio.

{{detalle_cifrado_en_reposo_y_en_transito}}

### 5.3 Ciclo de vida de claves

Generación, custodia, rotación, revocación y destrucción.

{{detalle_ciclo_de_vida_de_claves}}

### 5.4 Claves de firma del producto

Custodia en HSM y acceso dual.

{{detalle_claves_de_firma_del_producto}}

## 6. Registros y evidencias

- Inventario de claves y certificados

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
