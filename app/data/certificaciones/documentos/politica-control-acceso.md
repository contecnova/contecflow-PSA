# Política de control de acceso — {{empresa}}

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

Establecer cómo se conceden, revisan y retiran los accesos en {{empresa}} según necesidad de conocer y mínimo privilegio.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `politica-control-acceso` | Política de control de acceso | iso27001 A.5.15, tisax 4.2.1, nis2 art.21.2.i, iec62443 SPE 6, sox ITGC-APD-00, jsox ITGC-SEG-00 |
| `gestion-identidades` | Ciclo de vida de identidades | iso27001 A.5.16, tisax 4.1.1, tisax 4.1.3, iec62443 SR 1.1, iec62443 SR 1.3, iec62443 SR 1.4, iec62443 CR 1.1, iec62443 CR 1.3, iec62443 CR 1.4, iec62443 SG-6 |
| `informacion-autenticacion` | Gestión de credenciales y contraseñas | iso27001 A.5.17, tisax 4.1.2, iec62443 SR 1.5, iec62443 SR 1.7, iec62443 CR 1.5, iec62443 CR 1.7, sox ITGC-APD-05, jsox ITGC-SEG-05 |
| `autenticacion-segura` | Autenticación robusta y multifactor | iso27001 A.8.5, tisax 4.1.2, nis2 art.21.2.j, iec62443 SR 1.10, iec62443 SR 1.11, iec62443 CR 1.10, iec62443 CR 1.11 |
| `accesos-privilegiados` | Accesos privilegiados | iso27001 A.8.2, tisax 4.2.1, sox ITGC-APD-04, jsox ITGC-SEG-04 |
| `segregacion-funciones` | Segregación de funciones | iso27001 A.5.3, sox ITGC-APD-06, jsox ITGC-SEG-06 |
| `revision-periodica-accesos` | Recertificación periódica de accesos | iso27001 A.5.18, tisax 4.2.1, sox ITGC-APD-03, jsox ITGC-SEG-03 |

## 4. Funciones y responsabilidades

- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **TI**: Aplica las medidas técnicas y aporta las evidencias de los sistemas.
- **Propietario del proceso**: Aplica el documento en su proceso y responde de sus controles.
- **RR. HH.**: Integra los requisitos en los procesos de personas.
- **Auditoría interna**: Comprueba de forma independiente que se aplica.

## 5. Directrices

### 5.1 Principios

Necesidad de conocer, mínimo privilegio, identidades únicas y segregación de funciones.

{{detalle_principios}}

### 5.2 Autenticación

Requisitos de contraseña y multifactor por tipo de acceso ({{politica_mfa}}).

{{detalle_autenticacion}}

### 5.3 Accesos privilegiados

Elevación temporal, justificación y registro de actividad.

{{detalle_accesos_privilegiados}}

### 5.4 Revisión periódica

Frecuencia de recertificación por criticidad ({{frecuencia_recertificacion}}).

{{detalle_revision_periodica}}

### 5.5 Excepciones

Cómo se solicitan, aprueban y caducan.

{{detalle_excepciones}}

## 6. Registros y evidencias

- Campañas de recertificación
- Informe de cobertura MFA

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
