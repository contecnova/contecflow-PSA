"""CMDB de software, composición y vulnerabilidades (19-11-2026).

Diseño: `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`. Modelos:
`app/models/cmdb_software.py`. API: `/cmdb/software/*`
(`app/api/v1/endpoints/cmdb_software.py`).

Módulos:

- `identificadores`: purl, CPE y clave de conciliación de un producto.
- `versiones`: comparar versiones y comprobar rangos afectados.
- `configuracion`: parsear configuraciones (nginx, Apache, php.ini, INI,
  clave=valor) y enmascarar secretos.
- `formatos`: SBOM (CycloneDX, SPDX) y ficheros de dependencias.
- `escaneres`: informes de Trivy y Grype; interfaz de conectores de escaneo.
- `ajustes`: configuración del módulo por empresa (credenciales cifradas).
- `catalogo`: productos, versiones, componentes, instancias, relaciones,
  líneas base y licencias de ALM (alta, cambio, baja, auditoría).
- `importacion`: aplicar SBOM y dependencias, CSV, inventario del agente y
  conciliación desde Activos.
- `avisos`: guardar avisos y leer ficheros de avisos (OSV, NVD, GitHub, CSV).
- `fuentes`: clientes de OSV, NVD, GitHub, EPSS, KEV y endoflife.date.
- `correlacion`: hallazgos, prioridad y SLA.
- `gestion`: triaje, remediación (ticket, cambio, tarea) y excepciones.
- `licencias`: clasificación SPDX y compatibilidad.
- `analisis`: dónde se usa, árbol, impacto, fin de vida, deriva, licencias,
  cuadro de mando, vista por máquina, grafo y exportación.
- `cumplimiento`: controles del informe de cumplimiento.
- `trabajos`: el trabajo diario.
- `riesgo/` (rev. 194, 22-11-2026): índice de riesgo por ámbito, histórico,
  plan de reducción, métricas, superficies, controles compensatorios,
  intentos de explotación, importación de terceros, informes y avisos
  (`/cmdb/software/risk/*`; diseño §11).
"""
