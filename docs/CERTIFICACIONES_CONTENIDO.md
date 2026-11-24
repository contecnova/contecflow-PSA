# Contenido del módulo Certificaciones

**Estado:** fase 3 de `docs/propuestas/CERTIFICACIONES.md` (contenido). Redactado el 24-11-2026.
**Ubicación:** `app/data/certificaciones/`. Lo carga el código del módulo; este documento describe el formato, la
cobertura y las decisiones. Test de forma y coherencia: `tests/test_contenido_certificaciones.py`.

| Fichero | Contenido |
|---|---|
| `marcos.yaml` | 6 marcos: `iso27001`, `tisax`, `nis2`, `sox`, `jsox`, `iec62443` |
| `controles.yaml` | Biblioteca única: **207 controles comunes** con sus correspondencias |
| `plantillas/<marco>.yaml` | Una plantilla de programa por marco (6) |
| `plantillas/programa_integrado.yaml` | Las seis normas a la vez sin repetir trabajo |
| `documentos/<clave>.md` | **44 plantillas de documentos** (13 políticas, 18 procedimientos, 13 registros) |

---

## 1. Aviso de derechos de autor

- **ISO/IEC 27001, IEC 62443, el catálogo VDA ISA (TISAX) y el marco COSO tienen derechos de autor.** En este
  contenido solo hay **identificadores** (A.5.1, SR 1.1, 1.2.3…) y **títulos y descripciones redactados por
  nosotros**. No se ha copiado ni parafraseado frase a frase ningún texto de esas normas.
- **NIS2** (Directiva (UE) 2022/2555), **la ley SOX** y **la Ley de Instrumentos Financieros y Mercados de Japón (FIEA)**
  son textos legales públicos: se citan por artículo o sección y podrían incluirse literalmente. Aun así, las
  descripciones actuales son propias y breves; si se quiere el texto literal, se importa como se explica en §6.
- Los **códigos de ITGC, cierre (FC/FCRP), entidad (ELC) y aplicación (ITAC)** de SOX y J-SOX **no son
  numeración oficial** (la ley no numera controles): son un catálogo de referencia propio, estable, con las
  áreas habituales de las auditorías de control interno (acceso, cambios, desarrollo, operaciones, cierre,
  segregación, entorno de control). `ITGC-APD-00` y `ITGC-SEG-00` son la política general de acceso; `ITGC-CO-00`
  e `ITENV-01`, la comprensión del entorno de TI.
- Las plantillas de documentos son esqueletos propios con marcadores (`{{empresa}}`, `{{alcance}}`, `{{version}}`,
  `{{aprobador}}`, `{{fecha_aprobacion}}`, `{{detalle_…}}`…).

## 2. Formato

### 2.1 `marcos.yaml`
`{clave, nombre, version, publico, niveles, descripcion}`; `iec62443` añade `partes` (clave, nombre y rango de ids).
**`niveles` es la lista de valores válidos del campo `nivel` de las correspondencias:**

| Marco | Niveles | Significado |
|---|---|---|
| iso27001 | `clausulas`, `anexo_a` | Requisitos del sistema de gestión (4–10) o control del Anexo A |
| tisax | `AL2`, `AL3`, `prototipos` | Los requisitos de seguridad de la información llevan `AL2` = «aplica desde AL2» (en AL3 se evalúan los mismos, con verificación in situ). El capítulo 8 lleva `prototipos` (exige AL3). El nivel del programa se elige con el parámetro `nivel_tisax` |
| nis2 | `gobernanza`, `medidas`, `notificacion`, `registro` | Art. 20, art. 21, art. 23 y art. 3/27 |
| sox, jsox | `ley`, `entidad`, `itgc`, `cierre`, `aplicacion` | Sección o artículo de ley, controles a nivel de entidad, controles generales de TI, cierre de periodos, controles automáticos |
| iec62443 | `2-1`, `3-2`, `3-3`, `4-1`, `4-2` | **Decisión: las partes son niveles** (no submarcos). Así un programa activa las partes que le tocan y la matriz filtra por parte. El SL objetivo **no** es un nivel: se fija por zona en el programa (parámetro `sl_objetivo` como valor por defecto) |

### 2.2 `controles.yaml`
`{clave_comun, titulo, descripcion, dominio, evidencia_sugerida, medible_por_plataforma, correspondencias: [{marco, id_control, nivel}]}`.
- `clave_comun`: kebab-case, **estable** (no se renombra; si un control se retira, se marca en el código, no se reutiliza la clave).
- `dominio` (18): gobierno, riesgos, activos, accesos, criptografia, personas, fisica, operaciones, comunicaciones,
  desarrollo, producto, proveedores, incidentes, continuidad, cumplimiento, informacion_financiera, ot, prototipos.
- `medible_por_plataforma`: **46 controles** se pueden medir solos (MFA, recertificación, registro inmutable, CAB,
  copias, contraseñas, SoD, retención, CMDB, vulnerabilidades, incidentes, proveedores).

### 2.3 `plantillas/*.yaml`
`{clave, nombre, marcos, parametros, fases, riesgos, documentos}`.
- `parametros`: `{clave, tipo: entero|booleano|opcion, opciones, por_defecto}`. `por_defecto` es el escenario «la
  empresa más complicada posible». Además de los pedidos (`num_sedes`, `tiene_ot`, `cotiza_en`, `nivel_tisax`,
  `sl_objetivo`, `entidad_nis2`) hay dos más, necesarios para generar solo lo que aplica:
  `proteccion_prototipos` (módulo de prototipos de TISAX) y `desarrolla_producto` (62443-4-1 y 4-2).
- `fases`: siempre las 11 mismas claves: `arranque`, `carencias`, `riesgos`, `aplicabilidad`, `implantacion`,
  `formacion`, `auditoria_interna`, `revision_direccion`, `certificacion`, `cierre_hallazgos`, `seguimiento`.
- `tareas`: `{clave, nombre, raci: {R, A, C: [..], I: [..]}, dias, depende_de, controles, entregables, aplica_si?}`.
  `R` y `A` son **un solo rol** (regla RACI: un único responsable de aprobar); `C` e `I` son listas. Roles:
  direccion, responsable_seguridad, responsable_cumplimiento, ti, ot, rrhh, finanzas, auditoria_interna,
  propietario_proceso, proveedor. `dias` = días laborables de duración. Dependencias fin-comienzo.
- `riesgos`: `{clave, titulo, probabilidad: baja|media|alta, impacto: bajo|medio|alto|critico, mitigacion}`
  (correspondencia con `TemplateRisk`: baja→low, media→medium, alta→high; bajo→minor, medio→moderate, alto→major, critico→critical).
- `documentos`: `{clave, nombre, tipo: politica|procedimiento|registro, controles}`; `clave` = `documentos/<clave>.md`.

### 2.4 Expresión `aplica_si` (§4 de las plantillas)
- Gramática: `<parametro> <op> <literal>`, unidas con `and` u `or` (sin paréntesis; `and` antes que `or`).
- Operadores: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`. Literales: `true`, `false`, enteros, `'texto'`, `['a', 'b']`.
- Ejemplos: `num_sedes > 1`, `tiene_ot == true and sl_objetivo in ['SL3', 'SL4']`, `cotiza_en in ['eeuu', 'ambos']`.
- **Regla de generación:** si una tarea no aplica, no se crea y **sus sucesoras heredan sus dependencias**
  (transitivamente). Ejemplo: en J-SOX, `js_tres_documentos` depende de `sx_rcm`; si no se cotiza en EE. UU., hereda
  las dependencias de `sx_rcm`. Las dependencias a tareas que no están en la plantilla se han quitado al generar.

## 3. Cobertura por marco

| Marco | Ids cubiertos | Detalle | Controles comunes con correspondencia |
|---|---|---|---|
| ISO/IEC 27001:2022 | **118** | **93/93 del Anexo A** (A.5.1–A.5.37, A.6.1–A.6.8, A.7.1–A.7.14, A.8.1–A.8.34) + 25 requisitos de cláusulas 4–10 | 118 |
| TISAX (VDA ISA 6) | **63** | 45 de seguridad de la información (capítulos 1–7) + 18 de protección de prototipos (8.1.1–8.1.6, 8.2.1–8.2.6, 8.3.1–8.3.2, 8.4.1–8.4.2, 8.5.1–8.5.2) | 85 |
| NIS2 | **25** | art. 20.1, 20.2; art. 21.1, 21.2 a)–j), 21.3, 21.4; art. 23.1–23.3 y 23.4 a)–e); art. 3 y 27 (clasificación y registro) | 40 |
| SOX | **41** | Sec. 302, 404(a), 404(b), 802, 906; ITGC: acceso (APD 00–08), cambios (PC 01–06), desarrollo (PD 01–04), operaciones (CO 00–05); cierre FC 01–05; entidad ELC 01–05; ITAC-01 | 40 |
| J-SOX | **35** | FIEA art. 24-4-2, 24-4-4, 193-2-2; ITGC: seguridad/acceso (SEG 00–08), desarrollo y mantenimiento (DES 01–06), operación (OPE 01–04), externalización (EXT-01); entorno de TI (ITENV-01); cierre FCRP 01–05; entidad ELC 01–05; ITAC-01 | 40 |
| IEC 62443 | **186** | 2-1: SPE 1–8 (8) · 3-2: ZCR 1–7 (7) · 3-3: SR 1.1–7.8, FR1–FR7 completos (51) · 4-1: SM-1–13, SR-1–5, SD-1–4, SI-1–2, SVV-1–5, DM-1–6, SUM-1–5, SG-1–7 (47) · 4-2: CR y requisitos por tipo SAR/EDR/HDR/NDR (73) | 94 |

**Unificación:** de los 207 controles comunes, **123 sirven a dos o más normas** (71 a dos, 29 a tres, 15 a cuatro,
4 a cinco y 4 a las seis: `politica-control-acceso`, `preparacion-tic-continuidad`, `copias-seguridad` y `ciclo-desarrollo-seguro`). Solo 84 son de una sola norma, casi
todos por ser específicos (prototipos, notificación NIS2, cierre contable, requisitos técnicos de 62443, cláusulas ISO).

## 4. Decisiones de unificación

1. **El Anexo A de ISO 27001 es la columna vertebral**: cada control del Anexo A tiene al menos un control común, y a
   él se cuelgan TISAX, NIS2, SOX/J-SOX y 62443 cuando piden lo mismo (p. ej. `copias-seguridad` = A.8.13 + ISA 5.2.9
   + NIS2 21.2.c + SR/CR 7.3 + ITGC-CO-03 + ITGC-OPE-03).
2. **A.5.18 (derechos de acceso) se divide en tres** controles comunes —alta con aprobación, baja oportuna y
   recertificación— porque SOX/J-SOX los prueban por separado y la plataforma mide la recertificación sola.
3. **A.8.32 (cambios) se divide en cinco**: gestión de cambios, pruebas, aprobación independiente del paso a
   producción, cambios de emergencia y (con A.8.9) configuración. Así encajan los ITGC de cambios y la decisión 3
   de la propuesta (revisión independiente por versión).
4. **IEC 62443-3-3 y 4-2 comparten numeración**: SR x.y y CR x.y van en el mismo control común. Los requisitos
   solo de componente (EDR/HDR/NDR/SAR 2.4, 2.13, 3.2, 3.10–3.14) van con su prefijo de tipo.
5. **NIS2 art. 23 se separa por plazo** (24 h, 72 h, intermedio, 1 mes, comunicación a destinatarios), porque cada
   plazo es una tarea, un reloj y una evidencia distintos en el flujo del Service Desk.
6. **SOX y J-SOX comparten todos los controles comunes**; solo cambian los ids y las tareas de la plantilla (tres
   documentos, informe de control interno, presentación). En el programa integrado J-SOX reutiliza la RCM y las
   pruebas de SOX (`js_tres_documentos` → `sx_rcm`, `js_pruebas` → `sx_pruebas_eficacia`).
7. **Programa integrado**: las fases comunes (alcance, carencias, riesgos, SoA, políticas, formación, auditoría
   interna, revisión por la dirección, CAPA, seguimiento) existen **una sola vez**; la implantación se agrupa por
   dominio sobre la unión de controles (cada control una vez); las tareas propias de cada norma llevan `aplica_si`
   (TISAX si `nivel_tisax != 'ninguno'`, NIS2 si `entidad_nis2 != 'no'`, SOX/J-SOX según `cotiza_en`, OT y producto
   según `tiene_ot` y `desarrolla_producto`). Añade una matriz única, un plan único de pruebas reutilizable y un
   calendario integrado de auditorías externas.
8. **Cada control de un marco está enlazado al menos a una tarea** de su plantilla (lo comprueba el test), para que
   al cerrar la tarea se aporte evidencia a todos los controles y normas a la vez.

## 5. Plantillas

| Plantilla | Tareas | Con `aplica_si` | Riesgos | Documentos | Duración hasta el cierre de hallazgos* |
|---|---|---|---|---|---|
| iso27001 | 56 | 1 | 6 | 29 | ≈ 329 días laborables |
| tisax | 56 | 6 | 7 | 15 | ≈ 323 |
| nis2 | 54 | 3 | 7 | 14 | ≈ 323 |
| sox | 51 | 1 | 7 | 12 | ≈ 380 |
| jsox | 46 | 1 | 7 | 11 | ≈ 348 |
| iec62443 | 68 | 25 | 8 | 12 | ≈ 373 |
| programa_integrado | 132 | 72 | 18 | 44 | ≈ 425 |

\* Camino crítico con todos los parámetros en su valor por defecto; después vienen las tareas de seguimiento
(ciclo anual, recertificaciones, auditorías de seguimiento y renovación). Las tareas de implantación por dominio se
trocean en bloques de hasta 10 controles (15 + 4 días por control, máximo 60 días).

## 6. Cómo importar el texto oficial con licencia

1. La empresa compra la norma (ISO, IEC/ISA o el catálogo VDA ISA a través de ENX) y obtiene su licencia de uso
   interno.
2. En el módulo, por empresa, se importa un fichero (CSV o YAML) con `marco`, `id_control` y `texto_oficial`.
   Se cruza por `(marco, id_control)` con las correspondencias de `controles.yaml`; los ids que no casen se informan.
3. El texto importado se guarda **solo en el espacio de esa empresa**, nunca en este catálogo común, con referencia a
   la licencia (titular, fecha, número de licencias) y queda auditado.
4. La pantalla muestra la descripción propia y, si existe, el texto oficial de esa empresa.
5. Para NIS2, SOX y FIEA se puede cargar el texto literal en el catálogo común (son públicos), tomado de EUR-Lex,
   del Código de EE. UU. y de e-Gov Japón.

Al cambiar una norma de versión: se crea la nueva versión en `marcos.yaml`, se revisan las correspondencias y el
módulo muestra qué controles comunes se ven afectados (§3.1 de la propuesta).

## 7. Lo que no se ha cubierto y por qué

- **Módulo de protección de datos de TISAX (capítulo 9 de ISA 6)**: no estaba en el alcance pedido (AL3 + prototipos)
  y se solapa con el RGPD, ya cubierto por `privacidad-datos-personales` (A.5.34, ISA 7.1.2).
- **Mejoras de requisitos (RE) de 62443-3-3/4-2 por nivel de seguridad**: dependen del SL objetivo de cada zona y
  su enumeración se acerca al texto con derechos; se tratan con la tarea `i6_mejoras_sl_alto` y la brecha SL-T/SL-A
  por zona. Tampoco se anota el SL mínimo de cada SR.
- **Subrequisitos de 3-2** (ZCR 3.1…, 5.1…, 6.1…): se cubre cada ZCR de primer nivel.
- **Numeración de TISAX**: se ha usado la de ISA 6 tal como la conocemos (capítulo 3 sin 3.1.2; capítulo 8
  reorganizado). **Hay que verificarla contra el catálogo con licencia** al importar; los ids que no casen saldrán
  en el informe de importación del paso 2 de §6. Igual con los ids por tipo de componente de 4-2.
- **IEC 62443-2-1** se ha modelado con la edición 2024 (elementos SPE 1–8). Si un cliente trabaja con la edición
  2010 (elementos 4.2.x/4.3.x), hay que añadir esos ids.
- **SOC 1 / SOC 2** no son marcos de este contenido; la propuesta prevé migrar el SOC 2 que ya existe en el GRC.
  El SOC 1 de los proveedores aparece como control (`seguimiento-proveedores`) y tarea (`sx_soc1`).
- **Requisitos nacionales de transposición de NIS2** (plazos o formularios propios de cada país) no se incluyen:
  se parametrizan por autoridad (`{{autoridad_nis2}}`).

## 8. GRC

- **Auditoría:** el contenido es estático; los cambios se ven en git. Al cargarlo, el módulo debe auditar la
  importación y la versión del catálogo usada por cada programa.
- **RGPD:** no contiene datos personales. Las plantillas de registros que los recogen (formación, accesos a áreas
  de prototipos, notificaciones) indican plazo de conservación con marcador y acceso de solo lectura para auditoría.
- **Retención y bloqueo legal:** `politica-retencion-registros` y el control `proteccion-registros` (A.5.33, SOX 802).
- **Privilegios:** las plantillas fijan la segregación (quien prueba no implanta; quien cierra un hallazgo no lo
  corrigió; aprobación del paso a producción por persona distinta del autor), coherente con §3.10 de la propuesta.

## 9. Traducciones (24-11-2026)

El contenido se redacta en castellano y se muestra en el idioma de la interfaz (es/en/zh), con respaldo al
castellano.

- **Textos cortos** (`nombre`, `version`, `descripcion` de marcos; `titulo`, `descripcion`, `evidencia_sugerida`
  de controles; `nombre` de plantillas, fases, tareas y documentos, `entregables`, `titulo`/`mitigacion` de
  riesgos): catálogo por texto de origen, como gettext, en `i18n/en.yaml` e `i18n/zh.yaml`
  (`«texto en castellano»: «traducción»`; 1.166 textos). Se eligió frente a campos `*_i18n` dentro de cada YAML
  porque traduce también lo ya sembrado en la base de datos sin migrar nada: un control que sigue igual que la
  semilla se ve traducido y uno que la empresa editó (texto propio) se ve tal cual.
- **Esqueletos de documentos**: `documentos/en/<clave>.md` y `documentos/zh/<clave>.md`, misma estructura y
  mismos marcadores `{{...}}`. La generación desde plantilla crea los documentos en el idioma de quien genera.
- **Dónde se aplica**: `app/services/certificaciones/traduccion.py`. Todas las respuestas JSON del router de
  Certificaciones pasan por `RutaTraducida`, que traduce según la cabecera `X-Idioma` (la manda el cliente con el
  idioma de la interfaz; si no, `Accept-Language`). Los identificadores (`clave`, `marco`, `nivel`, `id_control`,
  `dominio`, `estado`, `tipo`…) nunca se traducen. La generación (`generacion.generar(..., idioma)`) escribe fases,
  tareas, riesgos, documentos, sedes («Site 1») y la descripción RACI de cada tarea (roles con nombre:
  `cert.generacion.rol.*` en `textos_de_salida_certificaciones.py`) en ese idioma.
- **Niveles** (`anexo_a`, `itgc`, `AL3`, `3-3`…): la pantalla los pinta con `cert.nivel_<nivel>`
  (`etiquetaNivel` en `components/certificaciones/comun.tsx`), nunca la clave cruda.
- **Al cambiar un texto en castellano** hay que añadir su traducción en los dos catálogos (y quitar la vieja):
  `tests/test_certificaciones_traduccion_2026_11.py` falla si falta, sobra, está vacía o es una copia del
  castellano (salvo nombres de normas y códigos), y si un documento no tiene su versión en/zh con los mismos
  marcadores.
- **Límite conocido**: la búsqueda de controles (`q`) compara con el texto guardado (castellano o el editado por la
  empresa); buscar con palabras en inglés o chino no encuentra los controles sembrados.
