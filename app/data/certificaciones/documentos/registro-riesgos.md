# Registro de riesgos — {{empresa}}

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

Recoger los riesgos evaluados y su tratamiento.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `evaluacion-riesgos` | Evaluación de riesgos de seguridad | iso27001 6.1.1, iso27001 6.1.2, iso27001 8.2, tisax 1.4.1, nis2 art.21.1, nis2 art.21.2.a, iec62443 SPE 1 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.

## 5. Campos del registro

| Campo | Descripción | Obligatorio |
|---|---|---|
| Riesgo | Descripción | Sí |
| Activos afectados | Referencias | Sí |
| Probabilidad | Escala | Sí |
| Impacto | Escala | Sí |
| Nivel inherente | Cálculo | Sí |
| Tratamiento | Opción y controles | Sí |
| Nivel residual | Cálculo | Sí |
| Propietario | Quien acepta | Sí |

## 6. Conservación y acceso

- Plazo de conservación: {{plazo_retencion}}; sujeto a bloqueo legal cuando proceda.
- Acceso de solo lectura para auditoría interna y auditores externos autorizados por el portal.
- Toda modificación queda en el registro de auditoría de la plataforma.

## 7. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
