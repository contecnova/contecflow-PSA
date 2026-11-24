# Propuesta: módulo de Certificaciones y cumplimiento continuo

**Estado:** aparcada a la espera de decisiones (ver §8). Redactada el 24-11-2026.
**Normas objetivo:** TISAX, NIS2, ISO/IEC 27001:2022, SOX, J-SOX e ISA/IEC 62443.

La idea tiene dos caras que se resuelven con **un único módulo**:

1. **Para los clientes:** que una empresa, por compleja que sea, pueda implantar, seguir y mantener todas esas
   certificaciones dentro de contecflow. Plantillas de proyecto completas y un punto de control (como el de
   Licencias) con trazabilidad total.
2. **Para nosotros:** que contecflow, como producto y como proveedor, pueda certificarse. Usaríamos ese mismo módulo
   con nosotros mismos.

---

## 1. Punto de partida: qué exige cada norma

Un software no «cumple» por sí solo: cumple una organización. La plataforma tiene que hacer dos cosas:

- **ser un producto que pase la auditoría** como proveedor;
- **ser la herramienta con la que el cliente demuestra que cumple**, con controles y evidencias que se generan solas.

| Norma | Qué es | Qué exige a la plataforma y al proveedor |
|---|---|---|
| **ISO/IEC 27001:2022** | Sistema de gestión de seguridad de la información (SGSI), certificable | Es la base común: controles del Anexo A, gestión de riesgos, cambios, accesos, registros, proveedores y desarrollo seguro (A.8.25–A.8.32). |
| **TISAX** | Evaluación de automoción (catálogo VDA ISA) con etiqueta de ENX | ISO 27001 más estricta, por niveles (AL2/AL3), más **protección de prototipos**, clasificación de la información y protección de datos. |
| **NIS2** | Directiva UE (ley); no es una certificación | Gestión de riesgos, **notificación de incidentes (alerta temprana en 24 h, notificación en 72 h, informe final en 1 mes)**, seguridad de la cadena de suministro y responsabilidad personal de la dirección. |
| **SOX / J-SOX** | Control interno sobre la información financiera (EE. UU. / Japón) | Controles generales de TI: accesos y su **revisión periódica**, **segregación de funciones**, **gestión de cambios con aprobación independiente**, trazabilidad inalterable y cierre de periodos. A un proveedor SaaS le pedirán un **informe SOC 1 tipo II**. |
| **ISA/IEC 62443** | Ciberseguridad industrial (OT) | Como fabricante de software: **4-1** (ciclo de desarrollo seguro). Si la CMDB o el descubrimiento tocan redes de planta: **3-2** (zonas y conductos) y **4-2** (requisitos de componente). Para el cliente, además 2-1 (programa) y 3-3 (requisitos de sistema). |

---

## 2. Lo que ya existe en contecflow (medido el 24-11-2026)

No se parte de cero. Se une y se completa:

- **Plantillas de proyecto** (`app/models/advanced_config.py`: `ProjectTemplate`, `TemplatePhase`, `TemplateTask`,
  `TemplateTaskDependency`, `TemplateRisk`, `TemplateDeliverable`; pantalla `ProjectTemplatesPage`).
- **Documentos** (README §18.5): categorías, versiones, permisos por documento, aprobación por flujo, reserva y
  resumen con IA.
- **GRC** (README §15):
  - informe de cumplimiento medido y firmado;
  - **Marcos y evidencias** con controles de ISO 27001:2022 y SOC 2 y evidencias con huella SHA-256;
  - matriz de roles, segregación de funciones (SoD) y explicador de accesos;
  - **recertificación de accesos** (§15.5);
  - retención y bloqueo legal (`app/db/bloqueo_legal.py`);
  - RGPD;
  - registro de auditoría encadenado con hash.
- **Seguridad de cuentas:** MFA por política, caducidad de contraseñas, sesiones, restricciones de IP y dispositivos
  de confianza.
- **Aprobaciones**, **CAB y cambios** (incluidos los cambios estándar), **riesgos**, **PIR**.
- **ALM: licencias y activos** (README §26), con vencimientos y avisos. Es el modelo de «punto de control».
- **CMDB** y vulnerabilidades.
- **Service Desk:** incidentes, problemas y SLA. Es la base de las notificaciones NIS2.
- **BPM**, para modelar los procesos del sistema de gestión.
- **Portal de clientes y de subcontratistas**, para dar acceso externo controlado a los auditores.

---

## 3. Módulo «Certificaciones»: el punto de control

Funciona como Licencias, pero para cumplimiento. Sus piezas:

### 3.1 Catálogo de marcos y biblioteca única de controles
- Marcos: ISO 27001:2022, TISAX (VDA ISA: AL2/AL3, módulos de protección de prototipos y de protección de datos),
  NIS2, SOX, J-SOX, IEC 62443 (2-1, 3-2, 3-3, 4-1, 4-2) y los que se añadan.
- **Una biblioteca única de controles con correspondencias entre normas.** Un control implantado una vez cuenta
  para todas las que lo exigen; no son seis proyectos sueltos.
- Versionado del catálogo: cuando una norma cambia de versión, se ve qué controles se ven afectados.
- **Integración con el GRC actual:** los marcos ISO 27001 y SOC 2 que ya existen migran a esta biblioteca, sin
  duplicarse.

### 3.2 Programa de certificación por empresa
- **Alcance:** entidades jurídicas, sedes, países, plantas OT, sistemas y procesos.
- **Objetivo:** norma y nivel (TISAX AL2/AL3; nivel de seguridad SL objetivo en 62443).
- **Gobierno:** responsables, patrocinador de dirección (NIS2) y calendario.

### 3.3 Declaración de aplicabilidad y matriz completa
- Cada control lleva:
  - si **aplica o no, con justificación**;
  - **estado de implantación**;
  - **eficacia**;
  - responsable;
  - evidencias;
  - fecha de última revisión.
- **Pruebas de control** al estilo SOX y J-SOX: prueba de diseño y de eficacia operativa, población, muestreo,
  resultado y quién probó (que no puede ser quien implantó).
- **Matriz cruzada** control × norma × sede × estado: qué se cumple, qué no, qué está en curso y qué ha caducado.
- **Cumplimiento continuo:** los controles que la plataforma puede medir (MFA, recertificaciones, CAB, copias,
  registro de auditoría…) se marcan solos en verde o rojo y aportan su evidencia automáticamente.

### 3.4 Evidencias, siempre bajo control de flujos
- Se apoyan en **Documentos**: versiones, **flujo de aprobación obligatorio**, huella, permisos, retención y bloqueo
  legal.
- **Caducidad de la evidencia:** una evidencia antigua deja de contar y avisa.
- Evidencia generada por el sistema: informes firmados de la propia plataforma.

### 3.5 Auditorías, hallazgos y acciones correctivas
- Tipos de auditoría: interna, de certificación (fase 1 y fase 2), de seguimiento, de renovación, de cliente y
  regulatoria.
- Plan de auditoría, agenda y muestras pedidas.
- **Hallazgos:** no conformidad mayor, no conformidad menor, observación y oportunidad de mejora.
- **Acciones correctivas (CAPA):** análisis de causa, plan, plazo, responsable, verificación de eficacia y cierre.
  Se convierten en tareas o proyectos de la plataforma.

### 3.6 Auditores y empresas colaboradoras
- **Empresas:** entidades certificadoras, proveedores de auditoría de ENX, consultoras, auditores SOX, laboratorios
  de 62443 (ISASecure, TÜV…).
- **Personas:** cualificación y acreditaciones, independencia, **conflictos de interés**, NDA firmados y periodos de
  actuación.
- **Acceso temporal de solo lectura** (por el portal) a la parte del programa que les toque, con todo lo que
  consultan registrado.
- **Trazabilidad completa:** quién auditó qué, cuándo, con qué muestras y con qué resultado.

### 3.7 Certificados y etiquetas: ciclo de vida igual que una licencia
- Emisión, alcance, entidad certificadora y número.
- Auditorías de seguimiento (año 1 y año 2) y renovación (año 3).
- **TISAX:** etiqueta con validez de 3 años, identificador del portal ENX y alcance de la evaluación.
- **Avisos de vencimiento** y de auditoría próxima, igual que en Licencias.

### 3.8 Obligaciones regulatorias (NIS2)
- **Flujo de incidente notificable** enlazado al Service Desk, con relojes de 24 h, 72 h y 1 mes.
- Plantillas de notificación a la autoridad (CSIRT o autoridad competente) y registro de comunicaciones.
- Evaluación de proveedores críticos de la cadena de suministro, enlazada con Proveedores.

### 3.9 Panel y paquete para el auditor
- Panel: avance por norma, carencias, hallazgos abiertos, acciones vencidas, certificados por vencer y cobertura de
  evidencias.
- **Paquete del auditor:** exportación firmada (declaración de aplicabilidad, matriz, evidencias, hallazgos y
  acciones) lista para entregar.

### 3.10 GRC del propio módulo
- Auditoría de cada cambio.
- RGPD de los auditores y consultores externos.
- Retención y bloqueo legal de evidencias y auditorías.
- Mínimo privilegio: capacidades propias del módulo.
- **SoD:** quien implanta no da el control por eficaz; quien prueba no es quien implanta; quien cierra un hallazgo
  no es quien lo corrigió.
- Todo configurable desde Configuración.

---

## 4. Plantillas de proyecto: la empresa más complicada posible

**Escenario de referencia:**
- grupo multinacional con varias entidades jurídicas y países;
- cotiza en EE. UU. y en Japón (SOX y J-SOX);
- proveedor de automoción con prototipos (TISAX AL3);
- entidad esencial bajo NIS2;
- plantas industriales con OT (IEC 62443-2-1, 3-2 y 3-3);
- desarrolla su propio software y dispositivos (IEC 62443-4-1 y 4-2).

**Plantillas:** una por norma (6) más un **programa integrado** que las hace todas a la vez sin repetir trabajo.

Cada plantilla incluye:
- **Fases reales:**
  - arranque y alcance;
  - análisis de carencias y de riesgos;
  - declaración de aplicabilidad;
  - diseño e implantación;
  - formación y concienciación;
  - auditoría interna;
  - revisión por la dirección;
  - auditorías de fase 1 y fase 2 (o evaluación TISAX);
  - cierre de hallazgos;
  - seguimiento y mejora continua.
- **Tareas con RACI**, dependencias, hitos, duración estimada, riesgos típicos y entregables.
- **Plantillas de documentos:** políticas, procedimientos y registros, todos con flujo de aprobación.
- **Generación automática:** al crear el proyecto se crean el programa, la declaración de aplicabilidad y la matriz.
  Las tareas quedan enlazadas a sus controles, y al cerrarse aportan su evidencia.
- **Parámetros de alcance:** número de sedes, si tiene planta OT, si cotiza y dónde, nivel TISAX y SL objetivo. La
  plantilla genera solo lo que aplica.

---

## 5. Certificar contecflow (la otra cara)

Se crea un programa «contecflow como proveedor» con el propio módulo:

- **Normas:** ISO 27001, TISAX (los clientes de automoción lo pedirán), NIS2 como proveedor de la cadena de
  suministro, IEC 62443-4-1, y un **SOC 1 tipo II** para los clientes sujetos a SOX.
- **Carencias probables del producto**, a confirmar midiendo:
  - campañas periódicas de revisión de accesos con evidencia (la base existe: recertificación);
  - acceso privilegiado: elevación temporal y registro de lo que hace un superadmin;
  - flujo de incidentes NIS2 con plazos y notificación;
  - clasificación de la información y protección de prototipos;
  - gestión de claves y cifrado en reposo demostrable;
  - exportación de registros a un SIEM;
  - cierre de periodos financieros sin modificación posterior;
  - gestión de vulnerabilidades y aviso a clientes (hay 7 avisos de npm sin revisar);
  - zonas y conductos en la CMDB (62443-3-2).
- **Desarrollo seguro (62443-4-1, ISO A.8.25–A.8.31, cambios en SOX).** Choca con la forma actual de trabajar (solo
  main, sin ramas, sin revisión, sin controles automáticos). Exige:
  - que quien escribe el cambio no sea quien lo aprueba para producción, con revisión registrada;
  - análisis de seguridad (SAST, dependencias) y **SBOM** por versión;
  - **versiones etiquetadas y firmadas**;
  - trazabilidad del requisito al despliegue.

  Forma mínima propuesta: revisión obligatoria **por versión** antes de producción (no por commit), análisis de
  dependencias y SBOM por versión, y versiones firmadas. Ver la decisión 3 en §8.
- **Operación y organización**, fuera del código pero imprescindibles:
  - políticas, análisis de riesgos y declaración de aplicabilidad (las puede generar el propio módulo);
  - copias de seguridad y recuperación ante desastres probadas;
  - pruebas de intrusión anuales;
  - formación;
  - gestión de proveedores;
  - implicación de la dirección.
- **Auditoría externa:**
  - ISO 27001: entidad acreditada;
  - TISAX: proveedor de auditoría de ENX;
  - 62443-4-1: ISASecure o TÜV;
  - SOC 1: auditor independiente;
  - NIS2 no tiene certificado; se demuestra ante la autoridad.

---

## 6. Aviso legal sobre los textos de las normas

ISO/IEC 27001, IEC 62443, el catálogo VDA ISA y el marco COSO **tienen derechos de autor**: no se puede incluir su
texto.

- Incluimos el **identificador** de cada control con una **descripción redactada por nosotros**.
- Cada empresa puede **importar su catálogo con licencia** (texto oficial) en su espacio.
- NIS2 (directiva UE) y la ley SOX son públicas: se pueden incluir enteras.

---

## 7. Plan de trabajo

Máximo 3 agentes a la vez; dentro de cada fase, uno detrás de otro. Sin pruebas mientras se trabaja; una prueba
general obligatoria al final. GRC, documentación y BPM se actualizan en cada fase.

| Fase | Contenido |
|---|---|
| 0 | Decisiones de §8 (formulario). |
| 1 | **Base del módulo:** modelo de datos, catálogo y correspondencias, programas, declaración de aplicabilidad y matriz; migrar los marcos ISO 27001 y SOC 2 del GRC actual. |
| 2 | **Evidencias** sobre Documentos (con flujos y caducidad), **auditorías, hallazgos y acciones correctivas**, **auditores y empresas colaboradoras** (con acceso temporal), **certificados y vencimientos**, **NIS2**. |
| 3 | **Contenido:** biblioteca de controles con correspondencias, 6 plantillas más el programa integrado, y plantillas de documentos. |
| 4 | **Programa «contecflow»:** medir las carencias del producto frente a la matriz, priorizarlas y corregirlas; desarrollo seguro según la decisión 3. |
| 5 | Panel, paquete del auditor y cierre: prueba general, documentación y subida. |

---

## 8. Decisiones pendientes del usuario

1. **Catálogo:** ¿solo identificadores con descripción propia y la importación del texto con licencia por cada
   empresa? (Recomendado.)
2. **Auditores externos:** ¿acceso temporal de solo lectura por el portal, o solo el paquete exportado?
3. **Certificar contecflow:**
   - ¿Alcance SaaS, instalado en casa del cliente o ambos?
   - ¿Aceptas cambiar el flujo de trabajo con revisión independiente por versión antes de producción? Sin ella no
     se pasa SOX, ISO 27001 ni 62443-4-1.
4. **Niveles:** ¿TISAX AL2 o AL3? ¿Qué partes de 62443 y qué SL objetivo?
