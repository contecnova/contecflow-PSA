# Certificaciones y cumplimiento continuo — manual técnico

**Migraciones:** 212 (`212_certificaciones`, tablas) y 213 (`213_certificaciones_id_semilla`, columna
`cert_correspondencias.id_semilla` para las bases que ya tenían la 212). **Fecha:** 24-11-2026.
**Propuesta y decisiones:** [propuestas/CERTIFICACIONES.md](propuestas/CERTIFICACIONES.md).
**Contenido (marcos, controles, plantillas, documentos):** [CERTIFICACIONES_CONTENIDO.md](CERTIFICACIONES_CONTENIDO.md).
**Manual funcional (cómo se usa):** README §15.9.

Normas: ISO/IEC 27001:2022, TISAX (VDA ISA 6, AL2/AL3 y prototipos), NIS2, SOX, J-SOX, ISA/IEC 62443
(2-1, 3-2, 3-3, 4-1, 4-2) y SOC 2 (migrado del GRC). Funciona como Licencias, pero para cumplimiento: un punto de
control con trazabilidad completa.

---

## 1. Piezas

| Pieza | Código |
|---|---|
| Modelo | `app/models/certificaciones.py` (21 tablas `cert_*`) |
| Servicios | `app/services/certificaciones/` (`catalogo`, `expresiones`, `generacion`, `programas`, `evidencias`, `auditorias`, `externos`, `certificados`, `nis2`, `proveedores`, `panel`, `trabajos`, `rgpd`, `comun`) |
| API | `app/api/v1/endpoints/certificaciones.py`, prefijo `/api/v1/certificaciones` |
| Textos de salida | `app/services/textos_de_salida_certificaciones.py` (avisos y plantillas NIS2 en es/en/zh) |
| Errores con código | `cert_*` en `app/core/codigos_de_error.py` (fuente: `scripts/codemods/errores_con_codigo/certificaciones.json`) |
| Pantallas | `frontend/src/pages/CertificacionesPage.tsx`, `frontend/src/components/certificaciones/*`, `frontend/src/pages/AuditorPublicoPage.tsx` (`/auditor/:token`), Configuración › Seguridad y GRC › Certificaciones (`ConfigCertificaciones.tsx`) |
| i18n | bloque `cert` de `frontend/src/i18n/langs/{es,en,zh}.mjs`, `nav.certificaciones`, `nav.group_compliance`, `ajustes.s_certificaciones(_d)` |
| Trabajos de fondo | `cert-vencimientos` (diario, 07:35) y `cert-nis2-relojes` (cada 15 min) en `app/worker.py` |
| Arranque | `app/main.py` pone al día la biblioteca sembrada sin editar (`catalogo.sincronizar_sembrado`) |
| Tests | `tests/test_certificaciones.py` (módulo) y `tests/test_contenido_certificaciones.py` (forma del contenido) |

## 2. Modelo de datos (migración 212)

Todas con `organization_id` NOT NULL y sus únicos con la empresa delante (`tests/test_unicos_por_organizacion.py`).

| Tabla | Qué guarda | Únicos |
|---|---|---|
| `cert_marcos` | Marco: clave, nombre, versión (y la anterior), público o con derechos, niveles válidos, sembrado/editado/huella | `(org, clave)` |
| `cert_controles` | Biblioteca única: clave común, título y descripción propios, dominio, evidencia sugerida, medida automática | `(org, clave_comun)` |
| `cert_correspondencias` | Control ↔ id en cada marco, nivel, versión, **texto oficial con licencia** de la empresa, `id_semilla`, `afectado_por_version` | `(org, marco, id_control, control)` |
| `cert_configuracion` | Una fila por empresa (ver §8) | `(org)` |
| `cert_programas` | Alcance (entidades, sedes, países, plantas OT, sistemas, procesos, zonas con SL), objetivos `[{marco, nivel, niveles, sl_objetivo}]`, responsable, patrocinador, calendario, proyecto, plantilla y parámetros | `(org, codigo)` CERT-0001 |
| `cert_aplicabilidad` | Fila de la declaración y de la matriz: aplica + justificación, estado de implantación, eficacia, responsable, quién implantó y quién evaluó, revisión, medición automática | `(org, programa, control, sede)` (sede vacía = toda la organización) |
| `cert_control_tareas` | Tareas que implantan el control | `(org, fila, tarea)` |
| `cert_pruebas` | Pruebas SOX/J-SOX: diseño o eficacia operativa, periodo, población, muestra, método, resultado, excepciones, quién probó | — |
| `cert_evidencias` | Evidencia de un control (de un programa, de una fila o de la biblioteca): documento, tarea, `compliance_evidence_id` (GRC), URI, SHA-256, contenido del sistema, validez y caducidad | — |
| `cert_entidades` | Empresas colaboradoras (certificadoras, proveedores ENX, consultoras, auditores SOX, laboratorios 62443, autoridades), enlazables a Proveedores (`subcontractor_id`) | `(org, nombre)` |
| `cert_auditores` | Personas externas: cualificación, independencia, conflictos, NDA, periodo de actuación, supresión RGPD | — |
| `cert_accesos` | Acceso temporal de solo lectura: auditor, programa, **huella** del token, desde/hasta, revocación, usos | `(org, token_hash)` |
| `cert_accesos_registro` | Cada consulta del auditor: recurso, detalle, IP, momento | — |
| `cert_auditorias` | Interna, certificación F1/F2, seguimiento, renovación, cliente, regulatoria; plan, agenda, muestras, conclusión | `(org, codigo)` AUD-0001 |
| `cert_hallazgos` | NC mayor/menor, observación, oportunidad; quién corrigió y quién cerró | `(org, codigo)` HAL-0001 |
| `cert_acciones` | CAPA: causa, plan, plazo, responsable, tarea, hecha/verificada y por quién | — |
| `cert_certificados` | Número, marco, entidad, alcance, nivel, emisión, validez, estado, ENX (TISAX), próxima auditoría del ciclo, avisos | `(org, numero)` |
| `cert_incidentes` | Incidente NIS2: ticket, conocido el, significativo, transfronterizo, impacto, autoridad, envíos, avisos del reloj | `(org, codigo)` NIS2-0001 |
| `cert_comunicaciones` | Registro de lo enviado a la autoridad | — |
| `cert_proveedores` | Evaluación de proveedores críticos (enlazada a `subcontractors`) | — |
| `cert_paquetes` | Paquetes del auditor generados: quién (o qué acceso), cuándo, SHA-256 | — |

Migración: idempotente (mira tablas e índices), SQLite y Postgres, `downgrade` real (borra las 21 tablas en orden
inverso; las tareas, proyectos y documentos generados se quedan en sus módulos; `compliance_evidence` no se toca).
La 213 añade `id_semilla` si falta y la rellena con `id_control` en las filas sembradas.

## 3. Biblioteca y carga del contenido (§3.1)

`catalogo.cargar()` lee `app/data/certificaciones/` y lo **valida** (se cachea por la fecha de los ficheros):

- marcos: clave, nombre, niveles (lista de textos), sin repetidos;
- controles: clave kebab, título, correspondencias a marcos que existen y con un `nivel` de sus `niveles`, sin
  repetidas; una `medible_por_plataforma` desconocida es un aviso (no se medirá);
- plantillas: parámetros `entero|booleano|opcion` con `por_defecto` válido, fases y tareas con clave y nombre
  únicos, RACI con `R` y `A` de un solo rol y `C`/`I` listas, `controles` y `depende_de` que existen, `aplica_si`
  válida y solo con parámetros declarados, documentos `politica|procedimiento|registro` con controles que existen.

Lo que falla queda fuera y se ve en `GET /certificaciones/catalogo/validacion` (y en el log); el resto se usa.

**Siembra por empresa** (`sembrar`, idempotente): crea lo que falta y pone al día lo sembrado que nadie editó
(`editado = False` y huella distinta). La primera vez que una empresa abre el módulo se siembra sola
(`asegurar_sembrado`); al arrancar, `sincronizar_sembrado` repite para cada empresa que ya sembró (igual que
`bpmn_process_service.sincronizar_catalogo_sembrado`). Editar un control (`PATCH /catalogo/controles/{id}`) lo
marca `editado` y la semilla ya no lo toca.

**Versiones:** si un marco cambia de versión en `marcos.yaml`, se guarda la anterior (`version_anterior`) y sus
correspondencias nuevas, o retiradas que tenían texto oficial, se marcan `afectado_por_version`
(`GET /catalogo/controles?afectados=true`). Se quitan con «Revisada» (`POST /catalogo/correspondencias/{id}/revisada`).
Las retiradas sin texto oficial se borran.

**Texto oficial con licencia** (`POST /catalogo/texto-oficial`): filas `{marco, id_control, texto_oficial?,
id_control_nuevo?}` + datos de la licencia. Se cruza por `id_control` o por `id_semilla`; con `id_control_nuevo` se
corrige el identificador (ids de referencia de TISAX ISA 6 y 62443-4-2) **sin perder el enlace**: la semilla lo
reconoce por `id_semilla`. Solo en el espacio de la empresa; queda auditado con los datos de la licencia.

**GRC «Marcos y evidencias»** (`migrar_grc`, dentro de la siembra): los ids de `app/core/marcos_de_cumplimiento.py`
entran como correspondencias de los marcos `iso27001` y `soc2` (SOC 2 se crea si falta; cada criterio cuelga del
control común que cubre el mismo requisito de ISO: CC6.1→A.8.5, CC6.2→A.5.18, CC6.3→A.5.15, CC7.2→A.8.16; lo que no
casa crea un control `grc-…`). Cada `compliance_evidence` se enlaza una vez como evidencia de su control
(`origen = grc`, `compliance_evidence_id`), aplicando los alias (A.9.2 → A.5.18). La tabla del GRC y su API siguen
igual: nada se copia fuera ni se pierde.

## 4. Programa, declaración de aplicabilidad y matriz (§3.2, §3.3)

- `poblar_aplicabilidad`: una fila (sede general) por control que exige algún objetivo, filtrando por los
  `niveles` del objetivo (TISAX `AL2`/`AL3`/`prototipos`, partes de 62443…). Idempotente; no borra.
- Una sede que difiere tiene su fila (`POST /aplicabilidad/{id}/sedes`); en la matriz, las demás heredan la general.
- Estado en la matriz: `no_aplica` (excluido con justificación obligatoria), `no_cumple` (medición en rojo o
  eficacia «no eficaz»), `cumple` (implantado + eficaz + evidencia válida), `caducado` (implantado y solo evidencias
  caducadas), `en_curso`, `pendiente`.
- **Cumplimiento continuo** (`POST /programas/{id}/medir` y el trabajo diario): los controles con
  `medible_por_plataforma` se miden solos (MFA, contraseñas, cadena de auditoría, SoD, copias, retención con el
  informe de cumplimiento; recertificación, revisión de proveedores, CMDB, vulnerabilidades, CAB e incidentes con
  sus tablas), cada medida en su punto de guardado. Aportan una evidencia del sistema por control y día
  (`informe_sistema`, contenido JSON + SHA-256, 31 días en verde). Las tareas enlazadas cerradas aportan la suya.

## 5. Evidencias (§3.4)

Cuentan para una fila: las suyas, las del programa sin fila para ese control y las de la biblioteca (GRC y
sistema). Estado: `valida`, `caducada` (por `caduca_el` o alta + `caducidad_evidencia_dias`),
`pendiente_aprobacion` (documento no aprobado con `exigir_evidencia_aprobada`, flujo de **Documentos**) y
`pendiente` (tarea sin hacer). Una evidencia manual sin documento necesita enlace, contenido o tarea; la huella
SHA-256 se valida. Los documentos de las plantillas nacen en Documentos con `requires_approval = True`.

## 6. Generación desde plantilla (§4)

`POST /programas/desde-plantilla` (`generacion.generar`):

1. Parámetros: validados contra la plantilla; los que faltan toman `por_defecto`; uno desconocido es 422.
2. Objetivos: TISAX `AL2` (+`AL3`) (+`prototipos` si `proteccion_prototipos`), fuera con `ninguno`; NIS2 fuera con
   `entidad_nis2 = no`; SOX con `cotiza_en ∈ {eeuu, ambos}`, J-SOX con `{japon, ambos}`; IEC 62443 `2-1` siempre,
   `3-2`/`3-3` con OT y `4-1`/`4-2` si desarrolla producto; el SL objetivo es el valor por defecto de la zona OT.
3. Tareas que cumplen `aplica_si` (intérprete propio, sin `eval`); las sucesoras de una que no aplica **heredan sus
   dependencias** (transitivamente).
4. Proyecto: se reutiliza `plantillas_de_proyecto` (plantilla derivada con fases, tareas con rol R, duración, RACI y
   controles en la descripción, dependencias FS, riesgos mapeados a `TemplateRisk`, documentos), se instancia (el
   planificador pone las fechas) y la plantilla derivada se archiva (`is_active = False`) como traza.
5. Programa + declaración; cada tarea creada se enlaza a sus controles (`cert_control_tareas`).
6. Documentos de la plantilla en Documentos (con los marcadores `{{empresa}}`, `{{alcance}}`, `{{autoridad_nis2}}`…
   rellenos) enlazados como evidencia de sus controles.

`crear` e `instanciar` de las plantillas de proyecto confirman por su cuenta: si algo falla después, el proyecto
queda creado (se ve en la auditoría `GENERATE` que no llegó).

## 7. Auditorías, hallazgos, CAPA, auditores, certificados y NIS2

- **CAPA** (§3.5): cada acción crea una tarea en el proyecto del programa (o en `proyecto_capa_id`); estados
  `abierta → en_curso → hecha → verificada | no_eficaz`. Una NC no se cierra con acciones sin verificar.
- **Acceso del auditor** (§3.6, decisión 2): exige NDA firmado, independencia declarada y que el periodo caiga en el
  de actuación; dura como mucho `acceso_auditor_max_dias`. El token se muestra una vez y solo se guarda su SHA-256.
  `GET /certificaciones/auditor/{token}` (vista) y `.../paquete` (paquete firmado) son rutas anónimas
  (docs/seguridad/rutas_anonimas.md): sesión de sistema con motivo, **publican** la empresa del acceso, solo ven su
  programa y apuntan cada consulta en `cert_accesos_registro` y en la auditoría (`AUDITOR_READ`). Revocado, caducado
  o auditor suprimido/inactivo: 401 `cert_acceso_no_valido`.
- **Certificados** (§3.7): sin `valido_hasta`, 3 años; sin `proxima_auditoria`, seguimiento a 12 y 24 meses y
  renovación al vencer; TISAX no puede pasar de 3 años. Cambiar fechas rearma los avisos.
- **NIS2** (§3.8): relojes desde `detectado_en`: alerta `nis2_alerta_horas` (24), notificación
  `nis2_notificacion_horas` (72), informe final `nis2_informe_final_dias` (30) desde la notificación. Cada reloj
  `cumplido|tarde|pendiente|vencido|no_aplica`. `POST /incidentes/{id}/comunicaciones` registra el envío y para el
  reloj (la notificación cuenta como alerta si no la hubo; el informe final exige notificación). Plantillas por
  idioma: `GET /incidentes/{id}/plantilla/{tipo}`. Avisos 6 h antes y al vencer, una vez cada uno.
- **Panel y paquete** (§3.9): el paquete (declaración, matriz, pruebas, evidencias con huella, auditorías,
  hallazgos, acciones, certificados) se firma con Ed25519 (`informe_de_cumplimiento.firmar`, la clave publicada de la
  cadena de auditoría) y deja traza en `cert_paquetes`.

## 8. Configuración

Configuración › Seguridad y GRC › **Certificaciones** (`/settings/certificaciones`, `certificaciones.administrar`;
`GET/PUT /certificaciones/config`). Tabla propia por empresa (`cert_configuracion`), no son ajustes de entorno ni
de `RUNTIME_FLAG_GROUPS`:

| Campo | Defecto | Uso |
|---|---|---|
| `aviso_certificado_dias` | 90 | Aviso antes de que venza un certificado |
| `aviso_auditoria_dias` | 30 | Aviso antes de la auditoría del ciclo |
| `caducidad_evidencia_dias` | 365 | Caducidad por defecto de una evidencia |
| `aviso_evidencia_dias` | 30 | Aviso antes de que caduque una evidencia |
| `exigir_evidencia_aprobada` | sí | La evidencia documental solo cuenta con el documento aprobado |
| `acceso_auditor_max_dias` | 30 | Duración máxima del acceso temporal |
| `autoridad_nis2` | — | CSIRT o autoridad competente por defecto |
| `nis2_alerta_horas` / `nis2_notificacion_horas` / `nis2_informe_final_dias` | 24 / 72 / 30 | Relojes NIS2 |
| `proyecto_capa_id` | — | Proyecto de las tareas CAPA de programas sin proyecto |

## 9. Capacidades y segregación de funciones (§3.10)

| Capacidad | Roles | Qué abre |
|---|---|---|
| `certificaciones.ver` | dirección, PM, jefe de equipo, RRHH | Pantalla y lectura (sonda estricta `GET /certificaciones/panel`) |
| `certificaciones.gestionar` | dirección, PM | Programas, declaración, evidencias, CAPA (hacer), certificados, proveedores, NIS2, medir |
| `certificaciones.auditar` | dirección, PM, jefe de equipo | Pruebas, eficacia, auditorías, hallazgos (cerrar), verificar CAPA, accesos de auditores, paquete |
| `certificaciones.administrar` | dirección | Configuración, biblioteca, texto oficial, borrados y RGPD de auditores (sonda estricta `GET /certificaciones/config`) |

SoD en el servicio (403 con código, infracción registrada en GRC si hay regla del módulo y `SOD_BLOCKED` en
auditoría): quien implanta no da el control por eficaz (`cert_sod_implantador_no_evalua`), quien prueba no es quien
implantó (`cert_sod_implantador_no_prueba`), quien corrigió un hallazgo o hizo alguna de sus acciones no lo cierra
(`cert_sod_corrector_no_cierra`) y quien hizo una acción no verifica su eficacia (`cert_sod_ejecutor_no_verifica`).

## 10. GRC del módulo

- **Auditoría:** cada cambio va al registro encadenado (`resource = certificaciones`, `resource_name =
  <entidad>:<id>`, `metadata.entidad`): CREATE/UPDATE/DELETE, SEED, IMPORT, GENERATE, MEASURE, EVALUATE, TEST,
  CORRECT, CLOSE, DONE, VERIFY, GRANT, REVOKE, NOTIFY, EXPORT, AUDITOR_READ, GDPR_EXPORT/GDPR_ERASE, SOD_BLOCKED.
  El correo y los conflictos de interés de un auditor no se escriben en claro en la auditoría.
- **Retención y bloqueo legal** (`app/db/bloqueo_legal.py`): `cert_evidencias`, `cert_auditorias` (cerradas, con
  hallazgos y CAPA en cascada), `cert_programas` (cerrados), `cert_incidentes` (cerrados o descartados, con
  comunicaciones), `cert_auditores` (inactivos) y `cert_accesos_registro`. Textos `retencion_tipo_cert_*`.
- **RGPD** (`certificaciones/rgpd.py`): auditores externos (copia y supresión por ficha o por correo desde las
  solicitudes RGPD de `cab_service/gdpr.py`: seudonimiza, revoca accesos y quita la IP del registro; bajo bloqueo
  legal, 409 `cert_auditor_bajo_bloqueo_legal`); las personas internas reciben sus papeles en la copia RGPD
  (`certification_*`).
- **Privilegio mínimo:** capacidades propias; el auditor externo solo ve su programa y solo lee.

## 11. BPM

Procesos sembrados (lineales, categoría `admin`, textos en `frontend/src/pages/bpm/catalogo/textosLineales/`):
`cert_program` (programa de certificación), `cert_audit_capa` (auditoría → hallazgo → CAPA) y `nis2_incident`
(incidente notificable con sus relojes). Ver docs/BPM.md.

## 12. API

| Método y ruta | Capacidad |
|---|---|
| `GET /panel` | ver |
| `GET, PUT /config` | administrar |
| `GET /catalogo/marcos`, `GET /catalogo/controles`, `GET /plantillas` | ver |
| `PATCH /catalogo/controles/{id}`, `POST /catalogo/correspondencias/{id}/revisada`, `POST /catalogo/sembrar`, `GET /catalogo/validacion`, `POST /catalogo/texto-oficial` | administrar |
| `GET /programas`, `GET /programas/{id}`, `GET /programas/{id}/aplicabilidad`, `GET /programas/{id}/matriz` | ver |
| `POST /programas`, `POST /programas/desde-plantilla`, `PATCH /programas/{id}`, `POST /programas/{id}/medir` | gestionar |
| `DELETE /programas/{id}` | administrar |
| `PATCH /aplicabilidad/{id}`, `POST /aplicabilidad/{id}/sedes`, `POST /aplicabilidad/{id}/tareas` | gestionar |
| `GET /aplicabilidad/{id}/tareas`, `GET /aplicabilidad/{id}/pruebas`, `GET /aplicabilidad/{id}/evidencias` | ver |
| `POST /aplicabilidad/{id}/eficacia`, `POST /aplicabilidad/{id}/pruebas` | auditar |
| `GET /evidencias` · `POST /evidencias` · `DELETE /evidencias/{id}` | ver · gestionar · administrar |
| `GET /auditorias`, `GET /auditorias/{id}`, `GET /hallazgos`, `GET /acciones` | ver |
| `POST /auditorias`, `PATCH /auditorias/{id}`, `POST /auditorias/{id}/hallazgos`, `PATCH /hallazgos/{id}`, `POST /hallazgos/{id}/cerrar`, `POST /acciones/{id}/verificar` | auditar |
| `POST /hallazgos/{id}/corregido`, `POST /hallazgos/{id}/acciones`, `PATCH /acciones/{id}`, `POST /acciones/{id}/hecha` | gestionar |
| `GET /entidades`, `GET /auditores` · `POST/PATCH /entidades`, `POST/PATCH /auditores` | ver · gestionar |
| `GET /auditores/{id}/rgpd`, `POST /auditores/{id}/suprimir` | administrar |
| `GET /accesos`, `POST /accesos`, `POST /accesos/{id}/revocar`, `GET /accesos/{id}/registro` | auditar |
| `GET /certificados`, `GET /incidentes`, `GET /incidentes/{id}`, `GET /incidentes/{id}/plantilla/{tipo}`, `GET /proveedores` | ver |
| `POST/PATCH /certificados`, `POST/PATCH /incidentes`, `POST /incidentes/{id}/comunicaciones`, `POST/PATCH /proveedores` | gestionar |
| `POST /programas/{id}/paquete`, `GET /programas/{id}/paquetes` | auditar |
| `GET /auditor/{token}`, `GET /auditor/{token}/paquete` | anónima con token |

## 13. Lo que queda fuera (y por qué)

- **Notificación a la autoridad por canal electrónico**: se registra lo enviado y se ofrece el texto; cada país
  tiene su portal (CSIRT nacional) y no hay API común. Se envía fuera y se apunta la referencia.
- **Registro de lo que hace un superadmin y elevación temporal de privilegios, SBOM y versiones firmadas**: son
  carencias del producto (§5 de la propuesta, fase 4), no del módulo.
- **Importación del texto oficial desde fichero**: la pantalla admite CSV o JSON pegado; no hay subida de fichero.
- **Edición de la agenda y las muestras de una auditoría en la pantalla**: la API las admite (`agenda`, `muestras`);
  la pantalla muestra el plan.
