# Declaración de aplicabilidad — {{empresa}}

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

Recoger, por control común y norma, si aplica, por qué y en qué estado está.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `tratamiento-riesgos-declaracion-aplicabilidad` | Tratamiento de riesgos y declaración de aplicabilidad | iso27001 6.1.3, iso27001 8.3, nis2 art.21.1 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Dirección**: Aprueba el documento y asigna los recursos necesarios.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Control común | Clave de la biblioteca | Sí |
| Correspondencias | Normas e identificadores | Sí |
| Aplica | Sí o no | Sí |
| Justificación | Motivo de inclusión o exclusión | Sí |
| Estado de implantación | No iniciado, en curso, implantado | Sí |
| Eficacia | Resultado de la última prueba | Sí |
| Responsable | Propietario del control | Sí |
| Última revisión | Fecha | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
