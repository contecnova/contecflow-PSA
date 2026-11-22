"""Índice de riesgo y gestión de vulnerabilidades (22-11-2026, rev. 194).

Diseño: `docs/CMDB_SOFTWARE_Y_VULNERABILIDADES.md`, §11. API:
`/cmdb/software/risk/*` (`app/api/v1/endpoints/cmdb_riesgo.py`).

- `ajustes`: pesos, constantes, rangos, objetivo y avisos (validados y auditados).
- `calculo`: riesgo de cada hallazgo, índice por ámbito, histórico diario,
  comparación, plan de reducción y eventos de riesgo.
- `metricas`: métricas de gestión de vulnerabilidades, superficies y listas
  agrupadas por CVE o por activo; exposición (detección por puertos y marca
  del CI); vistas guardadas.
- `controles`: controles compensatorios e intentos de explotación.
- `terceros`: conectores de Trend Vision One, Defender VM, Qualys, Tenable,
  Rapid7 y SIEM genérico, e importación de ficheros.
- `informes`: informes programados de riesgo (PDF) y su gestión.
- `alertas`: avisos configurables (campana y correo).
- `cumplimiento`: controles del informe de cumplimiento.
- `trabajos`: lo que añade al trabajo diario.
"""
