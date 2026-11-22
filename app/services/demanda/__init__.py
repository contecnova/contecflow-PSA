"""Motor de flujos de demanda configurable por empresa (migración 195, docs/FLUJO_DE_DEMANDA.md).

Módulos:
- `definicion`: lectura, validación, simulador y diagrama del JSON del flujo (puro).
- `config`: tipos de solicitud, flujos (versionados) y catálogo del configurador.
- `biblioteca` / `plantillas`: plantillas instalables (piloto y genéricas), importar/exportar.
- `acceso`: actor (usuario o cliente), responsables (estáticos y dinámicos), segregación.
- `motor`: fases, pasos en serie/paralelo, quórum, decisiones, puertas, fases condicionales,
  pausas por información, plazos, log inmutable con hash encadenado, puente con la bandeja.
- `expediente`: alta, ficha (bloqueo y versionado de campos críticos), envío, retirada, comentarios.
- `documentos`: repositorio documental etiquetado por fase (antivirus, anexos, descarga auditada).
- `avisos`: flujos de información por evento y destinatario.
- `resumen_ejecutivo`: Executive Summary en PDF y PPTX con plantilla configurable.
- `ejecucion`: ejecución manual y acciones automáticas al cerrar.
- `consultas`: listas, pendientes para mí y métricas.
- `cumplimiento`: controles del informe de cumplimiento.
- `entrada`: punto de entrada común de los canales (portales de clientes, interno y de proveedor).
- `trabajos`: avisos de plazo (worker).
"""
