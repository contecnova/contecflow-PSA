"""Certificaciones y cumplimiento continuo (migración 212, docs/CERTIFICACIONES.md).

- `comun`: utilidades, empresa, configuración, segregación (SoD), auditoría, avisos.
- `catalogo`: carga y validación de `app/data/certificaciones/`, siembra por empresa
  idempotente, sincronización al arrancar, migración del GRC (ISO 27001 y SOC 2),
  importación del texto oficial con licencia y versiones.
- `generacion`: programa desde plantilla (§4): parámetros, `aplica_si`, proyecto con
  tareas RACI, declaración de aplicabilidad, enlaces tarea↔control y documentos.
- `programas`: programas, declaración de aplicabilidad, matriz, pruebas, eficacia y
  cumplimiento continuo (medición automática).
- `evidencias`: evidencias sobre Documentos, caducidad y evidencia del sistema.
- `auditorias`: auditorías, hallazgos y acciones correctivas (CAPA → tareas).
- `externos`: empresas colaboradoras, auditores y acceso temporal de solo lectura.
- `certificados`, `nis2`, `panel` (panel y paquete firmado), `trabajos` (avisos) y `rgpd`.
"""
