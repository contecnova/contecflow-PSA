# Política de seguridad con proveedores — {{empresa}}

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

Asegurar que los proveedores de {{empresa}} protegen la información y los servicios según su criticidad.

## 2. Alcance

Aplica a {{alcance}} de {{empresa}}, incluidas las sedes {{sedes}}.

## 3. Controles que cubre

| Control común | Título | Correspondencias |
|---|---|---|
| `seguridad-proveedores` | Seguridad en la relación con proveedores | iso27001 A.5.19, tisax 6.1.1, nis2 art.21.2.d, iec62443 SPE 1 |
| `acuerdos-proveedores` | Requisitos de seguridad en contratos | iso27001 A.5.20, tisax 1.2.4, tisax 6.1.1, nis2 art.21.2.d |
| `cadena-suministro-tic` | Seguridad de la cadena de suministro TIC | iso27001 A.5.21, nis2 art.21.2.d, nis2 art.21.3, iec62443 SM-9 |
| `seguimiento-proveedores` | Seguimiento de servicios de proveedores e informes de aseguramiento | iso27001 A.5.22, tisax 6.1.1, sox ITGC-CO-05, jsox ITGC-EXT-01 |
| `servicios-nube` | Uso seguro de servicios en la nube y externos | iso27001 A.5.23, tisax 1.3.3, tisax 5.3.3, tisax 5.3.4 |

## 4. Funciones y responsabilidades

- **Responsable de cumplimiento**: Coordina las evidencias y su relación con cada norma.
- **Responsable de seguridad**: Mantiene el documento, vela por su aplicación e informa de las desviaciones.
- **Finanzas**: Es propietaria de los controles sobre la información financiera.
- **Proveedor**: Cumple los requisitos contractuales y aporta sus informes de aseguramiento.

## 5. Directrices

### 5.1 Clasificación de proveedores

Criterios de criticidad, incluidos los proveedores TIC directos.

{{detalle_clasificacion_de_proveedores}}

### 5.2 Evaluación previa

Cuestionario, etiquetas TISAX, certificados e informes SOC.

{{detalle_evaluacion_previa}}

### 5.3 Cláusulas contractuales

Seguridad, confidencialidad, notificación de incidentes, auditoría y salida.

{{detalle_clausulas_contractuales}}

### 5.4 Seguimiento

Revisión periódica y gestión de cambios del servicio.

{{detalle_seguimiento}}

### 5.5 Salida

Devolución y borrado de la información.

{{detalle_salida}}

## 6. Registros y evidencias

- Registro de proveedores críticos
- Evaluaciones

## 7. Incumplimiento

El incumplimiento de este documento se trata según el proceso disciplinario y el de no conformidades de {{empresa}}.

## 8. Control de cambios

| Versión | Fecha | Autor | Aprobador | Cambios |
|---|---|---|---|---|
| {{version}} | {{fecha_aprobacion}} | {{autor}} | {{aprobador}} | Versión inicial |
