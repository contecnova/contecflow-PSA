# CMDB de software, composición y vulnerabilidades

19-11-2026. Diseño (fase 1) e implementación (fase 2). Pantallas: *Soporte →
CMDB*, pestañas **Software**, **Dónde se usa**, **Por máquina** y
**Vulnerabilidades**; configuración en *Configuración → Service desk →
Software y vulnerabilidades* (`/settings/cmdb-software`).

Pregunta que tiene que contestar en segundos: «llega un CVE de PHP: ¿qué
software está hecho con ese PHP, en qué versión, en qué máquinas corre, qué
servicios sostiene y a qué clientes afecta?», y la inversa: «este software
comprado o hecho en casa, ¿con qué está hecho, sobre qué nginx corre, con qué
configuración y en qué máquina?».

## 1. Lo que había (medido el 19-11-2026)

| Pieza | Dónde | Medida |
|---|---|---|
| CI y relaciones | `sd_configuration_items`, `sd_ci_relations` (`app/models/service_desk/cmdb.py`, 102 líneas) | 13 clases base (`CIType`), 6 relaciones (`CIRelationType`: depends_on, hosts, connects_to, backed_up_by, monitored_by, part_of), `version`/`vendor` como texto libre, `attributes` JSON, deriva por `config_hash` + `baseline_attributes` |
| Clases propias y datos por clase | `sd_ci_classes`, `sd_ci_class_fields` | sin noción de software ni de componentes |
| Historial de CI, descubrimiento, agentes | `cmdb_changelog`, `cmdb_discovery_*`, `cmdb_agent_registrations` (`app/models/cmdb.py`, 280 líneas) | AWS, Azure, GCP, Kubernetes, vSphere, SNMP; agente con token SHA-256 |
| Impacto, topología, grafo | `cmdb_relation_service.py` (449), `CMDBTopologyGraph.tsx` (616) | impacto por relaciones de CI |
| API CMDB | `/sd/cmdb*` (`cmdb.py` 644 líneas + `cmdb_mercado.py` + `cmdb_3d.py`) | 42 rutas |
| Activos y licencias (ALM) | `alm_*` (`app/models/alm.py`, 785 líneas; 31 tablas ALM) | proveedores, contratos, licencias (`product_name`, `version` texto), activos con `ci_id`, `alm_software_installs` (licencia × activo × versión), uso real; 136 rutas `/alm*` |
| Inventario del agente para ALM | `alm_uso/inventario.py` (82) | `software: [{name, version, publisher}]` → `alm_software_installs` |
| Análisis de impacto de cambios | `change_impact_service/riesgo.py` | CIs directos + dependencias, criticidad, incidentes |

**Lo que faltaba**: catálogo de software normalizado (fabricante, versiones,
ciclo de vida), composición (lenguajes, frameworks, librerías: SBOM),
instancias desplegadas con su configuración, identificadores normalizados
(purl, CPE), vulnerabilidades y su correlación, y todos los análisis que salen
de ahí. `version` y `vendor` del CI y `product_name` de la licencia eran texto
libre sin nada que los uniera.

## 2. Reparto CMDB ↔ Activos (decisión)

- **Activos (ALM) = lo que se posee**: compra, proveedor, contrato, licencia,
  asientos, coste, amortización, renovación, titular, ciclo de vida del bien.
  No cambia.
- **CMDB = lo que se ejecuta y cómo se compone**: catálogo técnico de
  software (productos, versiones, fin de soporte), composición (SBOM),
  instancias desplegadas en CIs, su configuración y deriva, relaciones,
  servicios que sostienen y vulnerabilidades.
- **Vínculo explícito**, sin duplicar datos:
  - producto ↔ fabricante: `sw_products.alm_vendor_id` → `alm_vendors`;
  - producto ↔ licencias: `sw_product_licenses` (n:m con `alm_licenses`);
  - instancia ↔ licencia que la cubre: `sw_instances.license_id`;
  - instancia ↔ instalación de ALM: `sw_instances.alm_install_id`;
  - máquina física ↔ CI: lo que ya había (`alm_assets.ci_id`).
  - **Conciliación desde Activos**: `POST /cmdb/software/import/alm` convierte
    las instalaciones de ALM (licencia × activo con CI) en productos e
    instancias del catálogo, sin duplicar (mismo producto por nombre
    normalizado, misma instancia por CI + producto).

Por qué así: el coste y el contrato no tienen nada que ver con «qué PHP usa
este software»; y la vulnerabilidad no depende de quién pagó la licencia. Cada
lado conserva su pantalla y se enlaza con el otro (la ficha de software enseña
sus licencias y proveedor; la ficha de máquina enseña su activo).

## 3. Modelo de datos (migración 190)

Todas las tablas con `organization_id` (filtro de tenant y RLS automáticos).
Fichero: `app/models/cmdb_software.py`.

| Tabla | Qué es |
|---|---|
| `sw_products` | Producto del catálogo. `category` (application, runtime, language, framework, library, web_server, app_server, database, middleware, os, container_image, tool, other), `origin` (purchased, saas, open_source, in_house), fabricante (`vendor_name`, `alm_vendor_id`), identificadores (`purl_type`, `purl_namespace`, `purl_name`, `cpe_vendor`, `cpe_product`), `license_spdx`, propietario, proyecto (desarrollo propio), repositorio, servicio de negocio (`service_ci_id`), criticidad, `lifecycle_status`, `match_key` único por empresa |
| `sw_versions` | Versión de un producto: `version`, `cycle` (rama, p. ej. «8.1»), lanzamiento, **fin de soporte** (`support_end`), **fin de vida** (`eol_date`), soporte extendido, `is_latest` |
| `sw_components` | Composición (SBOM): versión de software → componente (producto + versión), `relation` (runtime, language, framework, library, bundled, base_image, driver, build_tool, plugin), `scope` (required, optional, dev, test), `direct`, `via_component_id` (árbol de transitivas), `purl`, `license_spdx`, `source` (manual, sbom, lockfile, agent, scan) e importación de origen |
| `sw_instances` | Instancia desplegada: producto + versión observada en un CI (máquina, VM, contenedor, nube) y entorno (prod, pre, dev, test, dr), nombre, rutas (instalación, configuración), puertos, estado, propietario, cliente, servicio, licencia ALM, instalación ALM, CI propio (opcional), exposición (internet, internal, isolated), **configuración enmascarada** (`config_json`), `config_hash`, línea base aprobada, deriva |
| `sw_instance_relations` | Relaciones entre instancias o hacia CIs: depends_on, runs_on, connects_to, publishes_via (detrás de un proxy), uses_database, uses_runtime, part_of, con detalle (puerto, protocolo) |
| `sw_config_snapshots` | Historial de configuración de cada instancia (enmascarado), con las claves cambiadas, origen y autor |
| `sw_baselines` | Línea base de configuración por producto: reglas (`eq`, `neq`, `contains`, `not_contains`, `regex`, `in`, `not_in`, `present`, `absent`, `min_version`) con severidad |
| `sw_sbom_imports` | Cada importación (formato, fichero, sha256, altas, cambios, bajas, estado) |
| `sw_product_licenses` | Producto ↔ licencia de ALM |
| `sw_vulnerabilities` | Aviso: id (CVE/GHSA/OSV), alias, fuente, título, severidad, CVSS (puntuación, vector, versión), EPSS (puntuación, percentil), **KEV** (explotada activamente), CWE, referencias, fechas, retirada |
| `sw_vulnerability_affects` | Qué afecta: ecosistema + paquete (purl) o CPE, rangos (`introduced`, `fixed`, `last_affected`, límites incluidos o no), versiones exactas |
| `sw_findings` | Hallazgo = vulnerabilidad × producto afectado × versión × contexto (instancia, o versión de software que lo lleva como componente). Estado, prioridad, SLA, responsable, ticket / cambio / tarea de remediación, verificación |
| `sw_vuln_exceptions` | Excepción (riesgo aceptado): motivo, controles compensatorios, caducidad, quién pide, quién aprueba, estado (pending, approved, rejected, expired, revoked), solicitud del motor de aprobaciones |
| `sw_config` | Configuración por empresa: fuentes (NVD, OSV, GitHub, EPSS, KEV, endoflife.date) con URL, credenciales **cifradas**, sincronización automática, SLA por severidad, licencias permitidas y prohibidas, ticket automático |
| `sw_sync_runs` | Cada sincronización o importación de avisos (fuente, cifras, estado, error) |

### Identificadores

- **purl** (`pkg:composer/laravel/framework@10.2.0`): `app/services/cmdb_software/identificadores.py` lo parsea y lo construye; la clave de producto es `tipo/espacio/nombre` en minúsculas (pypi normaliza `_` y `.` a `-`).
- **CPE 2.3** (`cpe:2.3:a:php:php:8.1.27:*:*:*:*:*:*:*`): `cpe_vendor` + `cpe_product`.
- Sin purl ni CPE: nombre normalizado (minúsculas, sin espacios ni signos).
- Los productos «base» (php, nginx, apache, tomcat, mysql, postgresql, node, openssl…) se reconocen por alias y reciben su CPE y su purl genérico al crearlos (`CONOCIDOS`).

### Versiones

Comparador propio (`versiones.py`): segmentos numéricos y de texto, prefijo `v`,
época `1:`, sufijos de distribución (`-1ubuntu2`), pre-versiones
(dev < alpha < beta < rc < final < post). Rangos al estilo OSV/NVD/GitHub
(`>= 1.0, < 1.2.5`). Ciclo («8.1») por prefijo.

## 4. Vulnerabilidades

### Fuentes (todas configurables, todas opcionales)

| Fuente | Cómo | Credencial |
|---|---|---|
| OSV.dev | `POST {url}/v1/querybatch` por purl con versión + `GET /v1/vulns/{id}` | ninguna |
| NVD 2.0 | `GET {url}?virtualMatchString=cpe:2.3:a:{vendor}:{product}` | `apiKey` (opcional, cifrada) |
| GitHub Advisories | `GET {url}/advisories?ecosystem=…&affects=…` | token (cifrado) |
| EPSS (FIRST) | `GET {url}?cve=…` | ninguna |
| KEV (CISA) | `GET {url}` (catálogo JSON) | ninguna |
| endoflife.date | `GET {url}/{producto}.json` → fin de soporte y de vida por rama | ninguna |
| **Fichero** (sin red) | OSV JSON (uno o lista), NVD JSON 2.0, GitHub Advisories JSON, CSV, informes de **Trivy** y **Grype** | — |

Sin red funciona entero: se importa el fichero. Con red, la sincronización
pregunta solo por lo que la empresa tiene (purl y CPE de su catálogo), no
descarga bases enteras.

### Correlación

**Versión desconocida → posible afectado.** Una ocurrencia sin versión (ver
§6) no se ignora: cada aviso de su paquete o CPE da un hallazgo con
`possible: true`, prioridad a la mitad y sin SLA (no cuenta como fuera de
plazo en el informe de cumplimiento). Se confirma o se descarta en el triaje,
y desaparece solo al conocerse la versión. Los paquetes de distribución (deb,
rpm, apk) solo casan por paquete (OSV con su distribución), nunca por CPE: las
distribuciones parchean sin cambiar la versión de origen.

Para cada aviso y cada ocurrencia (instancia desplegada o componente de una
versión de software): coincide el paquete (clave purl) **o** el CPE
(fabricante:producto), y la versión cae en un rango afectado. El resultado es
un hallazgo por (aviso, producto, versión, contexto). Si la ocurrencia
desaparece o se actualiza a una versión corregida, el hallazgo pasa a
**resuelto** y queda verificado (`verified_at`, «por la reevaluación»).

De un hallazgo se sabe **qué software** (el producto afectado y las versiones
de software que lo llevan, directa o transitivamente), **qué versiones**,
**qué máquinas** (CIs de las instancias), **qué servicios** (servicio del
producto, CI propio, relaciones de CI hacia arriba con el impacto de la CMDB)
y **qué clientes** (cliente de la instancia y de los proyectos de los CIs).

### Prioridad (0-100)

`base` = CVSS × 10 (o 90/70/50/20 por severidad si no hay CVSS);
`+15` si KEV; `+ EPSS × 20`; × criticidad (critical 1,0; high 0,9; medium 0,75;
low 0,6) del mayor entre producto, instancia y CI; × exposición (internet 1,0;
interna 0,8; aislada 0,5); × entorno (prod 1,0; pre/dr 0,8; test 0,6; dev 0,5).
Se guarda con su desglose (`score_detail`) para que el auditor vea por qué.

### SLA de remediación

Días por severidad de la empresa (`sla_days_critical` 15, `sla_days_high` 30,
`sla_days_medium` 90, `sla_days_low` 180) y `sla_days_kev` (7) si está en KEV,
desde que se detecta. El semáforo de lo que queda usa la métrica común
`vencimiento` de `app/core/umbrales.py` (los umbrales de la empresa).

### Gestión

- Estados: `open` → `triaged` → `in_progress` → `resolved` (verificado al
  reevaluar), o `mitigated`, `false_positive`, `accepted` (excepción
  aprobada). Cada cambio, auditado.
- **Remediación**: desde el hallazgo, *ticket* (incidente con el CI),
  *cambio* (petición de cambio con los CIs afectados y su análisis de impacto)
  o *tarea* (en el proyecto del software hecho en casa). El enlace queda en el
  hallazgo.
- **Excepción**: motivo, controles compensatorios y caducidad (máximo
  `exception_max_days`). La aprueba el motor de aprobaciones si la empresa
  tiene flujo `vuln_exception`; si no, un administrador (`software.aprobar`),
  nunca quien la pide. Al caducar, el hallazgo se reabre (trabajo diario).

## 5. Análisis

| Pregunta | Ruta |
|---|---|
| ¿Dónde está nginx? ¿Qué usa PHP < 8.2? | `GET /cmdb/software/where-used?q=php&op=lt&version=8.2` |
| Árbol de dependencias de un software | `GET /cmdb/software/versions/{id}/tree` |
| Impacto inverso (si cae X / CVE en Y) | `GET /cmdb/software/impact?product_id=` · `instance_id=` · `vulnerability_id=` |
| Obsoleto / fin de vida | `GET /cmdb/software/analysis/eol?days=` |
| Deriva de configuración | `GET /cmdb/software/analysis/drift` |
| Licencias de componentes (compatibilidad OSS) | `GET /cmdb/software/analysis/licenses` |
| Cuadro de mando | `GET /cmdb/software/dashboard` |
| Vista por máquina | `GET /cmdb/software/machines/{ci_id}` |
| Grafo (para el grafo de la CMDB) | `GET /cmdb/software/graph?product_id=` · `instance_id=` · `ci_id=` |
| Informe CSV | `GET /cmdb/software/export/findings.csv`, `.../export/inventory.csv` |

**Licencias**: cada SPDX se clasifica (permisiva, copyleft débil, copyleft
fuerte, copyleft de red, propietaria, desconocida). Conflictos: copyleft de red
(AGPL) en software en SaaS o distribuido; copyleft fuerte (GPL) en software
distribuido o comprado; licencia prohibida por la empresa; licencia
desconocida.

**Integraciones**:
- Análisis de impacto de un cambio: el informe añade `software_on_cis`
  (instancias, versiones, hallazgos abiertos y fin de vida de los CIs
  afectados) y el riesgo de esos hallazgos.
- Incidentes y problemas: un hallazgo abre un ticket o un problema sobre el CI;
  la vista por máquina enseña los tickets abiertos del CI.
- Nexus: herramienta `search_software_inventory` (dónde se usa, hallazgos,
  fin de vida, ficha de máquina), con la misma guarda que la API.

## 6. Descubrimiento y actualización

- **Importación de SBOM y ficheros de dependencias** sobre una versión de
  software: CycloneDX (JSON y XML), SPDX (JSON y etiqueta-valor),
  `composer.lock`, `package-lock.json` (v1, v2, v3), `yarn.lock` (v1),
  `requirements.txt`, `poetry.lock`, `Pipfile.lock`, `pom.xml`, `go.mod`,
  `go.sum`, `Gemfile.lock`, `Cargo.lock`, `packages.lock.json` (NuGet).
  Detecta el formato por nombre y contenido. Con `replace` las que ya no
  están se quitan; si no, solo se añaden y actualizan.
- **Varios ficheros a la vez, o un zip** (`files`, `formatos.leer_varios`):
  - los `pom.xml` se resuelven juntos: propiedades `${...}` del propio POM y de
    sus padres (y `${project.version}`, `${project.parent.version}`…),
    versiones de `dependencyManagement` propias, de los padres y de los BOM
    importados (`scope=import`) que vengan en el mismo lote;
  - un componente sin versión fija (`requirements.txt` con `>=`, un POM sin
    versión resoluble) toma la versión de otro fichero del lote para el mismo
    paquete: un lock (`poetry.lock`, `Pipfile.lock`…) o un `pip freeze`;
  - si nadie la da, queda **versión desconocida** (`unknown_version` en la
    respuesta) y la correlación lo avisa como **posible afectado** (ver §4);
  - lo que no se reconoce vuelve en `ignored`. El zip se abre sin rutas
    absolutas ni `..`, con un máximo de 300 ficheros y 60 MB descomprimidos.
- **CSV** de catálogo e instancias (columnas en `importacion.CSV_COLUMNAS`).
- **Agente**: el check-in del agente de la CMDB (`POST /sd/cmdb/agents/checkin`)
  admite `software_inventory: {complete, instances: [{name, version, category,
  purl, cpe, install_path, config_path, ports, config, config_text,
  config_format, components, sbom}]}`. Concilia por CI + producto + ruta; con
  `complete` marca como paradas las que ya no informa.
- **Informes de escáner**: Trivy y Grype (componentes + vulnerabilidades),
  Syft (es CycloneDX/SPDX).
- **Conexiones de escaneo** (`app/services/cmdb_software/escaneos.py`, detrás
  de la interfaz `ConectorDeEscaneo` de `escaneres.py`). Se guardan como
  proveedores de descubrimiento de la CMDB (`cmdb_discovery_providers`, tipos
  `sw_ssh`, `sw_winrm` y `sw_api`): configuración **cifrada** por empresa,
  programación (`scan_interval_minutes`, mínimo 15; la pasa
  `cmdb_discovery_run` cada 15 min) e historial (`cmdb_discovery_jobs`), sin
  tablas nuevas. Se configuran en Configuración (`software.config`) y se
  lanzan bajo demanda desde la CMDB (`software.gestionar`). API:
  `/cmdb/software/scanners` (alta, cambio, baja, `test`, `run`, `runs`,
  `fields`).
  - **SSH (Linux)**: `/etc/os-release` (el sistema como instancia con su CPE),
    paquetes dpkg/rpm/apk (por defecto solo librerías y herramientas
    relevantes —openssl, libc, sudo, curl, systemd, xz, kernel…—, todos con
    `all_packages`) con purl de distribución (`pkg:deb/ubuntu/openssl@…`),
    puertos a la escucha y su proceso (`ss`/`netstat`), versiones de nginx,
    Apache, PHP, Java, Node.js, Python, MySQL/MariaDB, PostgreSQL, Redis,
    OpenSSL, OpenSSH, HAProxy y Docker, y (`read_configs`) su configuración
    (`nginx -T`, `apache2.conf`/`httpd.conf`, el `php.ini` cargado, `my.cnf`),
    parseada y enmascarada. `sudo -n` opcional. La clave del servidor se
    comprueba contra `known_hosts`; sin él, solo se acepta si se marca
    `accept_unknown_host_keys` (menos seguro). Usuario y contraseña o clave
    privada (con frase).
  - **WinRM (Windows)**: sistema, programas instalados (registro Uninstall de
    64 y 32 bits, con fabricante y ruta), servicios en marcha, IIS (versión,
    sitios, enlaces, puertos, TLS) y puertos a la escucha. NTLM, Kerberos o
    básica; HTTPS con verificación de certificado por defecto.
  - **API (EDR/RMM)**: GET con token (cabecera configurable); la respuesta es
    el formato del inventario o se mapea con rutas de campos (`list_path`,
    `host_field`, `ip_field`, `software_field`, `name_field`,
    `version_field`, `vendor_field`, `path_field`) y paginación (`next_path`,
    `max_pages`).
  - Cada equipo se casa con su CI por nombre, FQDN o IP; si no existe y
    `create_cis` (por defecto, sí) se crea con la reconciliación de la CMDB.
    Un equipo que no responde no para el resto (`errors` en el resumen). Cada
    ejecución se audita (`sw_scan`, con las cifras y sin credenciales); los
    cambios de conexión también (`sw_scan_connection`, `secrets_changed`
    dice qué secreto cambió, nunca su valor). Librerías: `paramiko` (SSH) y
    `pywinrm` (WinRM), en `requirements.txt`; sin ellas el escaneo falla con
    `sw_dependencia_no_instalada`.
- **Configuración**: parseadores de `nginx.conf`, `httpd.conf`, `php.ini`,
  `my.cnf`/INI y `key=value`. Extraen versión, módulos, puertos, TLS, rutas y
  parámetros clave. **Los secretos nunca se guardan**: las claves con
  password, secret, token, key, credential, auth… y las cadenas de conexión con
  usuario y contraseña se enmascaran (`***`) antes de guardar.
- **Conciliación y deduplicación**: producto por `match_key` (purl → CPE →
  nombre normalizado y alias); instancia por CI + producto + ruta (o nombre);
  componente por versión de software + clave + versión + vía.
  `GET /cmdb/software/reconciliation/duplicates` propone productos duplicados
  y `POST .../merge` los funde (reapunta versiones, componentes, instancias y
  hallazgos).
- **Historial**: cada cambio de configuración deja una foto
  (`sw_config_snapshots`) y una entrada en el historial del CI anfitrión
  (`cmdb_changelog`: alta, baja o cambio de versión de software).

## 7. GRC

- **Auditoría** (`audit_logs`): alta, cambio y baja de producto, versión,
  instancia, relación, línea base; importaciones; cambios de configuración
  (claves cambiadas, sin valores secretos); cambios de estado de hallazgos;
  excepciones (pedir, aprobar, rechazar, revocar, caducar); configuración del
  módulo (sin secretos: `metadata.secretos_cambiados`).
- **Mínimo privilegio** (`app/core/capacidades.py`): `software.ver` y
  `software.gestionar` (dirección y PM, como la CMDB), `software.aprobar`
  (dirección: excepciones y líneas base) y `software.config` (dirección).
  Credenciales de fuentes cifradas (`app.core.encryption`), nunca devueltas
  (`*_set: true`). Configuración de instancias enmascarada al entrar.
- **Excepciones**: con caducidad obligatoria, segregación (no se aprueba la
  propia), caducan solas y reabren el hallazgo.
- **Informe de cumplimiento** (`informe_de_cumplimiento.py`):
  `sw_critical_vulns_sla` (críticas/altas abiertas fuera de SLA),
  `sw_eol_production` (software sin soporte en producción),
  `sw_ci_without_owner` (CIs con software sin propietario, y productos sin
  propietario), `sw_vuln_exceptions` (excepciones caducadas sin resolver y
  vigentes), `sw_vuln_feed` (antigüedad de la última sincronización).
- **Retención** (`app/db/bloqueo_legal.py`): `sw_config_snapshots` (desde la
  foto) y `sw_findings` (solo los cerrados, desde el cierre); respetan el
  bloqueo legal.
- Sin datos personales nuevos salvo el propietario (id de usuario, `SET NULL`).

## 8. Pantallas

- **CMDB → Software**: cuadro de mando (KPIs) y catálogo con filtros
  (categoría, origen, ciclo de vida, texto). La **ficha** de un producto:
  resumen e identificadores, versiones con fin de soporte, composición (árbol),
  instancias, vulnerabilidades, licencias (de ALM) y grafo (el de la CMDB).
  Importar SBOM o dependencias, CSV, Trivy/Grype y desde Activos.
- **Dónde se usa**: buscador «nginx», «php < 8.2», «pkg:npm/lodash».
- **Por máquina**: CI → software, versiones, configuración, deriva, hallazgos,
  activo y licencias.
- **Vulnerabilidades**: KPIs, lista con prioridad, SLA (semáforo) y filtros;
  detalle con impacto (software, máquinas, servicios, clientes), triaje,
  remediación (ticket, cambio, tarea) y excepción; importar avisos;
  sincronizar.
- **Configuración** (`/settings/cmdb-software`): fuentes, credenciales, SLA,
  licencias, ticket automático y conexiones de escaneo. Ningún módulo lleva
  botón «Configurar» (decisión del usuario; `configuracionUnica.test.ts`): la
  CMDB enseña avisos donde algo no funciona por falta de configuración (sin
  fuentes de avisos, sin conexiones de escaneo, conexión con error), con
  enlace a esta sección solo para quien tiene `software.config`.

**Dónde está en el código (frontend).** `pages/CMDBPage.tsx` añade las pestañas
`software`, `where`, `machine` y `vulns` (con `software.ver`, carga diferida) y
los avisos contextuales de configuración. Los componentes viven en
`components/cmdb/software/`: `SoftwareTabs.tsx` (las cuatro pestañas, la sección
de excepciones y el análisis de fin de vida, deriva y licencias),
`FichaDeSoftware.tsx` (ficha del producto y formularios de software e
instancia), `DetalleDeHallazgo.tsx` (aviso, impacto, triaje, remediación y
excepción), `ConfigSoftware.tsx` (la sección de Configuración), `Escaneos.tsx`
(conexiones de escaneo en Configuración, panel «Escaneos» con «Escanear ahora»
e historial en la pestaña Software, y el aviso contextual `AvisoDeConfiguracion`), `tablas.tsx`,
`comun.tsx` y `software.css` (clases `sw-*`). Escribir pide
`software.gestionar`; aprobar excepciones, líneas base y la configuración como
línea base, `software.aprobar`. Textos en el espacio `sw` de es/en/zh (los
códigos del servidor en `sw.v_<catálogo>`); errores en `err_srv.sw_*`. La
bandeja de aprobaciones conoce el tipo `vuln_exception`. Prueba:
`__tests__/cmdbSoftware.test.ts`.

## 9. Trabajos de fondo

| Tarea | Cuándo | Qué |
|---|---|---|
| `cmdb_software_diario` | 04:20 | Por empresa: sincroniza las fuentes activas si `auto_sync`, reevalúa (correlación + SLA + prioridad), caduca excepciones, ticket automático si está activo; y (rev. 194, `riesgo/trabajos.py`) caduca controles compensatorios, guarda la foto del índice de riesgo del día, manda avisos y poda el histórico (§11) |
| `cmdb_discovery_run` (el de la CMDB) | cada 15 min | Lanza las conexiones de escaneo `sw_*` cuya ventana venció (`run_discovery_for_provider` → `escaneos.para_el_descubrimiento`) |

## 10. Límites

- Una versión sin fijar y sin lock en el lote queda «versión desconocida» y se
  avisa como posible afectado; no se adivina la que se instalará.
- `pom.xml`: el padre o el BOM se resuelven si vienen en la misma importación
  (varios ficheros o zip); no se descargan de un repositorio Maven.
- SSH y WinRM: sin agente instalado; lo que no se puede leer sin privilegios
  (configuraciones de root) necesita `sudo -n` configurado en el equipo.
- Las rutas de GitHub y NVD tienen límites de uso; la sincronización pregunta
  como mucho `max_queries` por pasada.
- Sin probar contra NVD, OSV, GitHub, EPSS, KEV, endoflife.date, servidores
  SSH/WinRM ni un EDR reales: los tests (`tests/test_cmdb_software.py`,
  `tests/test_cmdb_software_escaneo.py`) simulan sus respuestas con los
  formatos documentados.

## 11. Índice de riesgo y gestión de vulnerabilidades

22-11-2026. Referencia: Trend Vision One (*Cyber Risk Index* y *Vulnerability
Management*). Lo que faltaba frente a ella, y cómo se cubre aquí sin duplicar
lo que ya existe (hallazgos, prioridad, SLA, excepciones, escaneos).

Servicio: `app/services/cmdb_software/riesgo/` (paquete). API:
`/cmdb/software/risk/*` (`app/api/v1/endpoints/cmdb_riesgo.py`, mismas guardas
que el resto del módulo). Migración `194_indice_de_riesgo` (tras
`193_clientes_internos`). Pantalla: pestaña **Riesgo** de la CMDB
(`components/cmdb/software/riesgo/`), configuración en la sección de
*Software y vulnerabilidades* de Configuración.

### 11.1 Modelo (migración 194)

| Tabla / columna | Qué es |
|---|---|
| `sw_config.risk_settings` (Text JSON) | Pesos y constantes de la fórmula, rangos de impacto, objetivo de la empresa, avisos, retención del histórico. Validado al guardar; cada cambio, auditado con antes y después (`sw_risk_settings`). |
| `sw_risk_snapshots` | Histórico diario: `scope_type` (`org`, `client`, `service`, `machine`, `application`), `scope_id` (vacío en `org`), `day`, `score`, `accepted_score`, `factors` (JSON con la puntuación de cada factor y sus puntos), `counts` (JSON), `computed_at`. Único por (empresa, ámbito, id, día): recalcular el mismo día sustituye. |
| `sw_compensating_controls` | Control compensatorio sobre un hallazgo: `control_type` (`waf`, `ips`, `virtual_patch`, `isolation`, `edr`, `segmentation`, `other`), descripción, evidencia (URL o texto), `reduction` (0,1-0,9; por defecto el del tipo), `expires_at` (obligatoria), `status` (`active`, `expired`, `revoked`), quién lo registra y quién lo revoca. |
| `sw_exploit_events` | Intento de explotación importado (SIEM/EDR/IPS): fuente, `vuln_id` (CVE), CI (casado por nombre/IP), `observed_at`, `action` (`blocked`, `detected`, `allowed`), `count`, `external_id` (deduplicación por empresa + fuente + id externo), `finding_id` si casa con un hallazgo. |
| `sw_saved_views` | Vistas guardadas de la lista de vulnerabilidades: superficie, agrupación (`cve`/`asset`/ninguna), filtros y columnas (JSON), propietario, compartida o no. |
| `sw_risk_alert_log` | Avisos ya mandados (`kind`, `key`, `sent_at`): no se repite el mismo aviso; queda como rastro. |
| `sw_findings.detected_by` (Text JSON) | Quién lo detecta: `correlation` y/o la fuente externa (`trendmicro`, `defender`, `qualys`, `tenable`, `rapid7`, `file`). Deduplicación de terceros. |
| `sw_findings.exploit_attempts`, `last_exploit_at` | Intentos de explotación vistos para ese hallazgo. |
| `sw_findings.risk_points` | Riesgo del hallazgo (0-100) de la última evaluación (lo que suma al índice). |
| `sw_instances.exposure_source` | De dónde sale la exposición: `manual`, `ports` (detectada por puertos públicos en IP pública), `ci` (marcada en el CI), `import`. |

La exposición del **CI** se marca en sus atributos (`attributes.exposure`:
`internet`/`internal`/`isolated`), sin columna nueva, y manda sobre la de sus
instancias. Sin migrar el CI.

### 11.2 Riesgo de un hallazgo (0-100)

    base   = CVSS × 10 (sin CVSS: critical 90, high 70, medium 50, low 20, unknown 50)
    explot = 1 + w_kev·KEV + w_epss·EPSS + w_attempts·(intentos > 0)
    r      = base × explot × exposición × criticidad × (1 + w_age·min(1, edad / age_cap_days)) × (1 − reducción de controles)
    r      = min(100, r);  posible afectado (versión desconocida) × 0,5

- `exposición`: internet 1,0 · interna 0,7 · aislada 0,4.
- `criticidad` (la mayor de producto, instancia y CI): critical 1,0 · high 0,85 · medium 0,7 · low 0,5.
- Controles compensatorios activos: se combinan como `1 − Π(1 − reducción)`, con tope 0,9.
- Prioridad (`priority_score`) y SLA no cambian de fórmula; un control activo
  multiplica también la prioridad por `(1 − reducción)` (baja la prioridad sin
  cerrar el hallazgo) y deja `score_detail.controls`.

### 11.3 Índice (0-100) de un ámbito

Seis factores, cada uno con puntos `P` y una constante de saturación `K`
(los puntos con los que el factor llega al 63 %):

    S_factor = 100 × (1 − e^(−P / K))
    Índice   = Σ peso_f × S_f      (Σ pesos = 1)

| Factor | Puntos (`P`) | `K` | Peso |
|---|---|---|---|
| `vulnerabilities` | Σ r/100 de hallazgos vivos no aceptados | 5 | 0,35 |
| `exploitation` | Σ (KEV 1 + EPSS ≥ umbral 0,5 + con intentos 1) de esos hallazgos | 2 | 0,20 |
| `exposure` | activos expuestos a Internet con algún hallazgo alto/crítico vivo | 3 | 0,15 |
| `configuration` | deriva (1 por instancia) + incumplimientos de línea base (crítica 1, alta 0,7, media 0,4, baja 0,2) | 10 | 0,10 |
| `eol` | instancias sin soporte (prod 1, resto 0,5; sistema operativo ×2) | 5 | 0,10 |
| `signals` | intentos de explotación de los últimos 30 días (permitidos 1, detectados 0,5, bloqueados 0,2) | 3 | 0,10 |

- **Riesgo aceptado**: el mismo factor `vulnerabilities` sobre los hallazgos
  con excepción aprobada (`accepted_score`), aparte; no suma al índice.
- **Ámbitos**: empresa; cliente (la instancia es del cliente, o su CI cuelga de
  un proyecto del cliente; los clientes internos son las **unidades**);
  servicio (servicio de la instancia o del producto); máquina (CI anfitrión);
  aplicación (producto, incluidos los componentes de sus versiones). Un
  componente se atribuye a las máquinas, clientes y servicios de las
  instancias de su software.
- **Nivel**: `nivel_de_riesgo` de `app/core/umbrales.py` (`RISK_LEVEL_*`).
- **Configurable** en Configuración: pesos (0-1, suman 1 con ±0,001), `K` (>0),
  multiplicadores, umbral de EPSS, rangos de impacto (`high_from` > `medium_from`),
  objetivo (0-100). Cada cambio, auditado (`sw_risk_settings`).

### 11.4 Evaluación e histórico

- `POST /risk/recalculate`: recalcula riesgo de hallazgos, índices de todos los
  ámbitos y guarda la foto del día. Lo hace también el trabajo diario
  (`cmdb_software_diario`, tras reevaluar). `GET /risk/index` devuelve el
  índice vivo de un ámbito con su desglose y `evaluated_at` (la última foto).
- Retención: `risk_settings.history_days` (por defecto 730); el trabajo diario
  borra lo anterior; registrado en `bloqueo_legal.TIPOS` (`sw_risk_snapshots`,
  `sw_exploit_events`, `sw_risk_alert_log`), respeta el bloqueo legal.

### 11.5 Plan de reducción

`GET /risk/plan?scope_type=&scope_id=&target=`: de X (actual) a Y (objetivo,
por defecto el de la empresa). Voraz: en cada paso, el hallazgo cuya
resolución más baja el índice (impacto exacto recalculando los factores sin
él), hasta llegar a Y o agotar (máximo 200). Cada paso: hallazgo, impacto
(puntos de índice), índice tras resolverlo, **pasos de remediación**
(actualizar a la versión corregida en las máquinas afectadas; sin corrección,
control compensatorio o retirada), y su ticket/cambio/tarea si lo tiene
(se crea con `/findings/{id}/remediate`).

`GET /risk/events`: todos los eventos de riesgo del ámbito (hallazgos, deriva,
incumplimientos, fin de vida, intentos de explotación) con sus puntos,
paginados y ordenados.

### 11.6 Métricas de gestión de vulnerabilidades

`GET /risk/metrics?scope_type=&scope_id=&days=90`:
`assets` (CIs con software), `% con vulnerabilidades` (todos, internos —no
expuestos a Internet— y máquinas: servidor, VM, endpoint, contenedor, nube),
**densidad** (hallazgos vivos por activo y por máquina), **MTTP** (media de
`closed_at − first_seen_at` de los resueltos en el periodo), **antigüedad
media** de lo no parcheado, equipos con **SO sin soporte** (instancia de
categoría `os` en fin de vida o sin soporte), reparto por **impacto** (rangos
configurables sobre la prioridad: alto ≥ 70, medio ≥ 40) y por **estado**
(nuevo = `open`; en curso = `triaged`/`in_progress`/`mitigated`; resuelto en
el periodo; aceptado).

### 11.7 Superficies y vistas

`GET /risk/surfaces`: cuenta por superficie —`internal`, `internet`,
`container` (CI contenedor), `cloud_vm` (VM/servidor descubierto en AWS,
Azure o GCP, o CI `cloud`), `serverless` (clase o atributo
`serverless`/`function`)—. `GET /risk/findings?surface=&group_by=cve|asset`
lista o agrupa (por CVE: activos afectados y peor riesgo; por activo:
hallazgos y peor riesgo). Vistas guardadas: `GET/POST/PATCH/DELETE
/risk/views` (filtros y columnas; propias o compartidas). Exposición:
`POST /risk/exposure/detect` (puertos públicos —80, 443, 8080, 8443, 22,
3389, 21, 25, 3306, 5432…— en IP pública → `internet`, `exposure_source =
ports`; no pisa lo manual) y `PUT /risk/exposure/ci/{ci_id}` (marca el CI).

### 11.8 Controles compensatorios e intentos de explotación

- `POST /risk/controls` (uno o varios hallazgos), `GET /risk/controls`,
  `POST /risk/controls/{id}/revoke`. Caducidad obligatoria (máximo
  `exception_max_days`); al caducar (trabajo diario) deja de restar y se
  audita (`sw_compensating_control`). No cierra el hallazgo.
- Intentos de explotación: `POST /risk/exploits/import` (CSV o JSON:
  `cve, host, ip, observed_at, action, count, id`) y conexión de tipo
  `sw_siem` (API genérica con mapeo de campos, como `sw_api`). Casan con el
  hallazgo del mismo CVE en el mismo CI y suben su riesgo.

### 11.9 Importación de terceros

Conexiones de escaneo nuevas (mismo mecanismo que §6: `cmdb_discovery_providers`,
configuración cifrada, programación e historial; se configuran en
Configuración y se lanzan desde la CMDB):

| Tipo | API | Credencial |
|---|---|---|
| `sw_vm_trendmicro` | Trend Vision One: `GET {url}/v3.0/asrm/vulnerableDevices` (paginado por `nextLink`) | token (Bearer) |
| `sw_vm_defender` | Microsoft Defender VM: token OAuth2 (cliente/secreto del inquilino), `GET {url}/api/machines` + `GET {url}/api/vulnerabilities/machinesVulnerabilities` (`@odata.nextLink`) | `client_secret` |
| `sw_vm_qualys` | Qualys VMDR: `POST {url}/api/2.0/fo/asset/host/vm/detection/?action=list` (XML) + base de conocimiento para QID → CVE | usuario y contraseña |
| `sw_vm_tenable` | Tenable.io: exportación `POST /vulns/export` → estado → trozos | `X-ApiKeys` (acceso y secreto) |
| `sw_vm_rapid7` | Rapid7 InsightVM: `GET /api/3/assets` + `/assets/{id}/vulnerabilities` + `/vulnerabilities/{id}` | usuario y contraseña |
| `sw_siem` | API genérica de eventos (intentos de explotación) | token |

Y **fichero** (`POST /risk/import/file`, `source` + fichero): exportaciones
JSON de cada uno, XML de Qualys y un CSV común (`host, ip, cve, product,
vendor, version, fixed_version, severity, cvss, status, first_seen`).

Todo se normaliza a detecciones `{host, ip, cve, título, severidad, CVSS,
producto, fabricante, versión, versión corregida, estado, fechas}` y se
aplica así: CI por nombre/FQDN/IP (o se crea si `create_cis`); producto por
la conciliación del catálogo (o «sin identificar» de esa fuente); instancia
del producto en ese CI; aviso por su id (CVE, o `QID-…`/plugin si no hay CVE)
sin pisar datos mejores; hallazgo con **la misma clave que la correlación**
(aviso × producto × versión × instancia), así que lo que detectan a la vez
nuestra correlación y el tercero es **un solo hallazgo** con
`detected_by = [correlation, defender]`. Una importación completa de una
fuente quita esa fuente de los hallazgos que ya no informa; sin ninguna
fuente viva, el hallazgo pasa a `resolved` (verificado por la fuente). La
reevaluación propia ya no cierra un hallazgo que sigue informado por un
tercero.

### 11.10 Informes programados y avisos

- Informes: los programados de siempre (`scheduled_reports`, worker horario,
  correo con PDF) con dos tipos nuevos, `cyber_risk` (índice, tendencia,
  factores, plan) y `vuln_management` (métricas, top hallazgos), y ámbito en
  `filters_json` (`scope_type`, `scope_id`). Se crean y gestionan desde la
  pestaña Riesgo (`GET/POST/PATCH/DELETE /risk/reports`, `POST
  /risk/reports/{id}/run`); el PDF lo pinta `riesgo/informes.py` dentro de
  `report_pdf_service.build_report_pdf`.
- Avisos (campana + correo), configurables en `risk_settings.alerts`:
  `kev_new` (nuevo hallazgo con CVE explotado —KEV o con intentos— que nos
  afecta), `index_above` (índice de la empresa o de un cliente por encima de
  un umbral), `sla_due_days` (hallazgos cuyo SLA vence en N días); a quién
  (roles y usuarios) y si va por correo. Sin repetir el mismo aviso
  (`sw_risk_alert_log`). Tipo de aviso `system` (el tipo de la tabla es un
  enumerado y no se migra).

### 11.11 GRC

- Auditoría: controles compensatorios (alta, revocación, caducidad),
  intentos importados (resumen por importación), importaciones de terceros,
  cambios de pesos y avisos (`sw_risk_settings`), recálculos manuales,
  vistas compartidas. Las excepciones ya se auditaban.
- Informe de cumplimiento, tres controles nuevos: `sw_risk_index`
  (índice de la empresa frente al umbral `alerts.index_above` o, sin él,
  `RISK_LEVEL_HIGH`), `sw_kev_open` (críticos/altos explotados —KEV o con
  intentos— abiertos sin excepción), `sw_mitigations_expired` (controles
  compensatorios caducados con el hallazgo aún vivo).
- Privilegios: `software.ver` ve todo; `software.gestionar` registra
  controles, importa, recalcula, guarda vistas e informes; `software.config`
  cambia pesos, avisos y conexiones; revocar un control, `software.gestionar`.
- Retención: §11.4. Sin datos personales nuevos (ids de usuario con `SET NULL`;
  los eventos de explotación guardan host e IP de equipos, no de personas).

### 11.12 Límites

- Los conectores de terceros se han escrito con los formatos públicos de cada
  API y se prueban con respuestas simuladas; **no se han probado contra
  ninguna consola real**. El de Trend Vision One es el más incierto (su API
  de ASRM cambia de versión): si su respuesta no casa, la importación de
  fichero JSON sirve igual.
- El índice no es comparable con el de Trend Micro: es nuestra fórmula,
  documentada y configurable.
- El índice se calcula en memoria sobre los hallazgos vivos de la empresa
  (sin consultas por ámbito): pensado para miles de hallazgos, no millones.
- Las columnas nuevas de `sw_findings`, `sw_instances` y `sw_config` las lee
  todo el módulo: hasta aplicar la migración 194 la CMDB de software falla
  con «no such column».

### 11.14 Código del servidor y pruebas

`app/services/cmdb_software/riesgo/`: `ajustes.py` (§11.3, validación y
auditoría), `calculo.py` (§11.2-11.5: riesgo, índice, ámbitos, histórico,
comparación, plan y eventos), `metricas.py` (§11.6-11.7), `controles.py`
(§11.8), `terceros.py` (§11.9; los tipos `sw_vm_*`/`sw_siem` se registran en
`escaneos.TIPOS`/`CAMPOS` y `escaneos.ejecutar` delega en
`terceros.ejecutar_conexion`), `informes.py` y `alertas.py` (§11.10),
`cumplimiento.py` y `trabajos.py` (§11.11 y §11.4). Ganchos en código
existente: `correlacion.reevaluar` (controles y `detected_by`),
`report_pdf_service.build_report_pdf` (tipos `cyber_risk`/`vuln_management`),
`textos_de_salida` (`riesgo.*`, `aviso.swr_*`), `informe_de_cumplimiento`,
`bloqueo_legal.TIPOS`, `trabajos.diario`. Pruebas: `tests/test_cmdb_riesgo.py`.

### 11.13 Pantallas

- **CMDB → Riesgo** (`pages/CMDBPage.tsx`, pestaña `risk`, icono `Gauge`, con
  `software.ver` y carga diferida en el mismo `Suspense` que las de software):
  `components/cmdb/software/riesgo/RiesgoTab.tsx` con sub-pestañas y el
  selector de ámbito (`SelectorDeAmbito.tsx`; las entidades salen de
  `/risk/compare`, las unidades son clientes internos):
  - `Indice.tsx`: cifra 0-100 con nivel, aceptado, objetivo, última
    evaluación, «Recalcular» (`software.gestionar`), factores, recuentos,
    tendencia (recharts con los colores del tema) y comparación.
  - `Plan.tsx`: objetivo «de X a Y», pasos con sus acciones
    (`swr.accion_<code>`), enlace o creación de ticket/cambio
    (`/findings/{id}/remediate`), detalle del hallazgo y todos los eventos.
  - `Metricas.tsx` (§11.6), `Superficies.tsx` (§11.7: tarjetas, lista
    filtrable y agrupable, columnas, vistas guardadas, detectar y marcar
    exposición, control sobre los elegidos), `Controles.tsx` (§11.8),
    `Importar.tsx` (§11.9, fichero; las API van con las conexiones de
    escaneo) e `Informes.tsx` (§11.10).
  - Comunes: `comunRiesgo.tsx` (etiquetas `swr.v_<catálogo>`, `/risk/meta`,
    nivel) y `riesgo.css` (clases `swr-*`, solo variables del tema).
- **Configuración** → Software y vulnerabilidades: `riesgo/ConfigRiesgo.tsx`
  al final de `ConfigSoftware.tsx` (pesos con la suma visible, saturaciones,
  multiplicadores, explotación, edad, impacto, objetivo, histórico, avisos y
  «Restaurar valores por defecto»; se guarda aparte). Los seis tipos de
  conexión nuevos están en `Escaneos.tsx` (`TIPOS`).
- Datos: `services/api/cmdbRiesgo.ts`. Textos: espacio `swr` de es/en/zh;
  errores `err_srv.swr_*`. Prueba: `__tests__/cmdbRiesgo.test.ts`.
