# Registro de formación y concienciación — {{empresa}}

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

Recoger la formación recibida por cada persona.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `formacion-concienciacion` | Formación y concienciación | iso27001 7.3, iso27001 A.6.3, tisax 2.1.3, nis2 art.21.2.g, iec62443 SPE 1 |
| `formacion-ciberseguridad-direccion` | Formación en ciberseguridad del órgano de dirección | nis2 art.20.2 |
| `formacion-proteccion-prototipos` | Formación y compromiso del personal en prototipos | tisax 8.2.3 |

## 4. Funciones y responsabilidades

- **RR. HH.**: Integra los requisitos en los procesos de personas.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Persona | Identificador | Sí |
| Acción formativa | Título | Sí |
| Fecha | Fecha de realización | Sí |
| Resultado | Evaluación | Sí |
| Vencimiento | Fecha de renovación | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
