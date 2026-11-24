"""Textos de salida de la PIR (revisión posterior a la implantación, migración 206, docs/PIR.md).

Bloque propio de `textos_de_salida.TEXTOS` (se fusiona al importarlo): título
por defecto de una PIR, descripción de la tarea de una acción de mejora, avisos
(asignada, próxima a vencer, vencida, aprobada, devuelta, reabierta, acción) y
las etiquetas de los hechos que se guardan con una lección nacida de una PIR.
"""

TEXTOS_PIR: dict[str, dict[str, str]] = {
    "pir.titulo": {"es": "PIR de {ref}: {nombre}", "en": "PIR of {ref}: {nombre}", "zh": "{ref} 的实施后评审：{nombre}"},
    "pir.tarea_descripcion": {
        "es": "Acción de mejora de la revisión posterior a la implantación {codigo} ({titulo}).",
        "en": "Improvement action from post-implementation review {codigo} ({titulo}).",
        "zh": "来自实施后评审 {codigo}（{titulo}）的改进措施。"},
    "pir.aviso.asignada": {"es": "Tienes una PIR asignada: {codigo}", "en": "A PIR has been assigned to you: {codigo}",
                           "zh": "已为你分配实施后评审：{codigo}"},
    "pir.aviso.asignada_cuerpo": {"es": "{titulo}. Fecha prevista: {fecha}.", "en": "{titulo}. Due date: {fecha}.",
                                  "zh": "{titulo}。计划日期：{fecha}。"},
    "pir.aviso.proxima": {"es": "La PIR {codigo} vence pronto", "en": "PIR {codigo} is due soon",
                          "zh": "实施后评审 {codigo} 即将到期"},
    "pir.aviso.proxima_cuerpo": {"es": "{titulo}. Fecha prevista: {fecha}.", "en": "{titulo}. Due date: {fecha}.",
                                 "zh": "{titulo}。计划日期：{fecha}。"},
    "pir.aviso.vencida": {"es": "La PIR {codigo} está vencida", "en": "PIR {codigo} is overdue",
                          "zh": "实施后评审 {codigo} 已逾期"},
    "pir.aviso.vencida_cuerpo": {"es": "{titulo}. Debía hacerse el {fecha}.", "en": "{titulo}. It was due on {fecha}.",
                                 "zh": "{titulo}。应于 {fecha} 完成。"},
    "pir.aviso.aprobada": {"es": "PIR {codigo} aprobada", "en": "PIR {codigo} approved", "zh": "实施后评审 {codigo} 已批准"},
    "pir.aviso.aprobada_cuerpo": {"es": "{titulo}", "en": "{titulo}", "zh": "{titulo}"},
    "pir.aviso.devuelta": {"es": "PIR {codigo} devuelta para completar", "en": "PIR {codigo} returned for completion",
                           "zh": "实施后评审 {codigo} 已退回补充"},
    "pir.aviso.devuelta_cuerpo": {"es": "{titulo}. Motivo: {comentario}", "en": "{titulo}. Reason: {comentario}",
                                  "zh": "{titulo}。原因：{comentario}"},
    "pir.aviso.reabierta": {"es": "PIR {codigo} reabierta", "en": "PIR {codigo} reopened", "zh": "实施后评审 {codigo} 已重新打开"},
    "pir.aviso.reabierta_cuerpo": {"es": "{titulo}. Motivo: {motivo}", "en": "{titulo}. Reason: {motivo}",
                                   "zh": "{titulo}。原因：{motivo}"},
    "pir.aviso.accion": {"es": "Acción de mejora de la PIR {codigo}", "en": "Improvement action from PIR {codigo}",
                         "zh": "来自实施后评审 {codigo} 的改进措施"},
    "pir.aviso.accion_cuerpo": {"es": "{accion}", "en": "{accion}", "zh": "{accion}"},
    # Hechos de una lección con origen PIR (`servicio.hechos_para_leccion`).
    "leccion.hecho.pir_origen": {"es": "Cambio o proyecto", "en": "Change or project", "zh": "变更或项目"},
    "leccion.hecho.pir_resultado": {"es": "Resultado de la PIR", "en": "PIR outcome", "zh": "评审结果"},
    "leccion.hecho.pir_objetivos": {"es": "Objetivos cumplidos", "en": "Objectives met", "zh": "目标达成"},
    "leccion.hecho.pir_marcha_atras": {"es": "Hubo marcha atrás", "en": "Rolled back", "zh": "发生回退"},
    "leccion.hecho.pir_incidencias": {"es": "Incidencias provocadas", "en": "Incidents caused", "zh": "引发的事件"},
    "leccion.hecho.pir_criterios": {"es": "Criterios de éxito", "en": "Success criteria", "zh": "成功标准"},
    "leccion.hecho.pir_satisfaccion": {"es": "Satisfacción media (1-5)", "en": "Average satisfaction (1-5)",
                                       "zh": "平均满意度（1-5）"},
}
