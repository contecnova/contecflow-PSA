# Registro de acceso a áreas de prototipos — {{empresa}}

| Campo | Valor |
|---|---|
| Tipo | Registro |
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

Recoger las entradas y salidas de las áreas de prototipos.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `control-entrada-areas-prototipos` | Control de entrada a áreas de prototipos | tisax 8.1.5 |
| `normas-visitantes-prototipos` | Normas para visitantes en áreas de prototipos | tisax 8.1.6 |
| `control-acceso-proyectos-prototipos` | Autorización de acceso a proyectos de prototipos | tisax 8.2.5 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Persona | Identificador o visitante | Sí |
| Área | Identificador | Sí |
| Entrada | Fecha y hora | Sí |
| Salida | Fecha y hora | Sí |
| Acompañante | Si es visitante | Sí |
| Autorización | Referencia | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
