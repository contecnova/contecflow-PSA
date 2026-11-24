"""Textos de salida de Certificaciones (migración 212, docs/CERTIFICACIONES.md).

Bloque propio de `textos_de_salida.TEXTOS` (se fusiona al importarlo): avisos
(certificado que vence, auditoría próxima, evidencia que caduca, CAPA asignada y
vencida, relojes NIS2) y las plantillas de notificación a la autoridad NIS2
(alerta temprana, notificación, informe intermedio y final; art. 23 de la
Directiva (UE) 2022/2555).
"""

_AVISOS = {
    "certificado_vence": (("El certificado {ref} vence pronto", "Certificate {ref} expires soon", "证书 {ref} 即将到期"),
                          ("Válido hasta el {fecha}.", "Valid until {fecha}.", "有效期至 {fecha}。")),
    "auditoria_proxima": (("Auditoría próxima del certificado {ref}", "Upcoming audit for certificate {ref}",
                           "证书 {ref} 的审核即将到来"),
                          ("Auditoría {tipo} prevista el {fecha}.", "{tipo} audit planned on {fecha}.",
                           "{tipo} 审核计划于 {fecha}。")),
    "evidencia_caduca": (("Una evidencia caduca pronto: {ref}", "Evidence expires soon: {ref}", "证据即将过期：{ref}"),
                         ("Deja de contar el {fecha}: renuévala.", "It stops counting on {fecha}: renew it.",
                          "将于 {fecha} 失效：请更新。")),
    "capa_asignada": (("Acción correctiva asignada ({ref})", "Corrective action assigned ({ref})", "已分配纠正措施（{ref}）"),
                      ("{titulo}. Plazo: {fecha}.", "{titulo}. Due: {fecha}.", "{titulo}。期限：{fecha}。")),
    "capa_vencida": (("Acción correctiva vencida ({ref})", "Corrective action overdue ({ref})", "纠正措施已逾期（{ref}）"),
                     ("Debía terminarse el {fecha}.", "It was due on {fecha}.", "应于 {fecha} 完成。")),
    "nis2_proximo": (("NIS2 {ref}: el plazo «{reloj}» vence en menos de 6 h",
                      "NIS2 {ref}: the «{reloj}» deadline is less than 6 h away", "NIS2 {ref}：「{reloj}」期限不足 6 小时"),
                     ("Plazo: {plazo}.", "Deadline: {plazo}.", "期限：{plazo}。")),
    "nis2_vencido": (("NIS2 {ref}: plazo «{reloj}» vencido", "NIS2 {ref}: «{reloj}» deadline missed",
                      "NIS2 {ref}：「{reloj}」期限已过"),
                     ("Venció el {plazo}: registra la comunicación cuanto antes.",
                      "It was due on {plazo}: record the communication as soon as possible.",
                      "已于 {plazo} 到期：请尽快登记通报。")),
}

_NIS2 = {
    "alerta_temprana": (
        ("[NIS2] Alerta temprana – {codigo}", "[NIS2] Early warning – {codigo}", "[NIS2] 早期预警 – {codigo}"),
        ("A la atención de {autoridad}:\n\nAlerta temprana (art. 23.4.a de la Directiva (UE) 2022/2555) del incidente "
         "{codigo} «{titulo}», conocido el {detectado}.\n\n¿Se sospecha de una acción ilícita o malintencionada? "
         "[indicar]\n¿Puede tener impacto transfronterizo? {transfronterizo}\n\nImpacto inicial: {impacto}\n",
         "To {autoridad}:\n\nEarly warning (Art. 23(4)(a) of Directive (EU) 2022/2555) for incident {codigo} "
         "«{titulo}», known since {detectado}.\n\nIs unlawful or malicious action suspected? [state]\nCould it have a "
         "cross-border impact? {transfronterizo}\n\nInitial impact: {impacto}\n",
         "致 {autoridad}：\n\n事件 {codigo}「{titulo}」（知悉时间 {detectado}）的早期预警（欧盟指令 2022/2555 第 23(4)(a) 条）。\n\n"
         "是否怀疑存在非法或恶意行为？[说明]\n是否可能产生跨境影响？{transfronterizo}\n\n初步影响：{impacto}\n")),
    "notificacion": (
        ("[NIS2] Notificación del incidente – {codigo}", "[NIS2] Incident notification – {codigo}",
         "[NIS2] 事件通报 – {codigo}"),
        ("A la atención de {autoridad}:\n\nNotificación (art. 23.4.b) del incidente {codigo} «{titulo}», conocido el "
         "{detectado}. Actualiza la alerta temprana.\n\nEvaluación inicial (gravedad e impacto): {impacto}\n"
         "Indicadores de compromiso: [indicar]\nDescripción: {descripcion}\n",
         "To {autoridad}:\n\nNotification (Art. 23(4)(b)) of incident {codigo} «{titulo}», known since {detectado}. "
         "Updates the early warning.\n\nInitial assessment (severity and impact): {impacto}\nIndicators of compromise: "
         "[state]\nDescription: {descripcion}\n",
         "致 {autoridad}：\n\n事件 {codigo}「{titulo}」（知悉时间 {detectado}）的通报（第 23(4)(b) 条），更新早期预警。\n\n"
         "初步评估（严重程度和影响）：{impacto}\n入侵指标：[说明]\n描述：{descripcion}\n")),
    "informe_intermedio": (
        ("[NIS2] Informe intermedio – {codigo}", "[NIS2] Intermediate report – {codigo}", "[NIS2] 中期报告 – {codigo}"),
        ("A la atención de {autoridad}:\n\nInforme intermedio (art. 23.4.c) del incidente {codigo} «{titulo}».\n\n"
         "Situación actual: [indicar]\n",
         "To {autoridad}:\n\nIntermediate report (Art. 23(4)(c)) on incident {codigo} «{titulo}».\n\nCurrent status: "
         "[state]\n",
         "致 {autoridad}：\n\n事件 {codigo}「{titulo}」的中期报告（第 23(4)(c) 条）。\n\n当前状况：[说明]\n")),
    "informe_final": (
        ("[NIS2] Informe final – {codigo}", "[NIS2] Final report – {codigo}", "[NIS2] 最终报告 – {codigo}"),
        ("A la atención de {autoridad}:\n\nInforme final (art. 23.4.d) del incidente {codigo} «{titulo}» (plazo: "
         "{plazo}).\n\na) Descripción detallada, gravedad e impacto: {impacto}\nb) Tipo de amenaza o causa raíz: "
         "[indicar]\nc) Medidas de mitigación aplicadas y en curso: [indicar]\nd) Impacto transfronterizo: "
         "{transfronterizo}\n",
         "To {autoridad}:\n\nFinal report (Art. 23(4)(d)) on incident {codigo} «{titulo}» (deadline: {plazo}).\n\n"
         "a) Detailed description, severity and impact: {impacto}\nb) Type of threat or root cause: [state]\n"
         "c) Mitigation measures applied and ongoing: [state]\nd) Cross-border impact: {transfronterizo}\n",
         "致 {autoridad}：\n\n事件 {codigo}「{titulo}」的最终报告（第 23(4)(d) 条，期限：{plazo}）。\n\n"
         "a) 详细描述、严重程度和影响：{impacto}\nb) 威胁类型或根本原因：[说明]\nc) 已采取和正在采取的缓解措施：[说明]\n"
         "d) 跨境影响：{transfronterizo}\n")),
}

TEXTOS_CERTIFICACIONES: dict[str, dict[str, str]] = {}
for _clave, ((_t_es, _t_en, _t_zh), (_c_es, _c_en, _c_zh)) in _AVISOS.items():
    TEXTOS_CERTIFICACIONES[f"cert.aviso.{_clave}"] = {"es": _t_es, "en": _t_en, "zh": _t_zh}
    TEXTOS_CERTIFICACIONES[f"cert.aviso.{_clave}_cuerpo"] = {"es": _c_es, "en": _c_en, "zh": _c_zh}
for _clave, ((_a_es, _a_en, _a_zh), (_x_es, _x_en, _x_zh)) in _NIS2.items():
    TEXTOS_CERTIFICACIONES[f"cert.nis2.{_clave}.asunto"] = {"es": _a_es, "en": _a_en, "zh": _a_zh}
    TEXTOS_CERTIFICACIONES[f"cert.nis2.{_clave}.contenido"] = {"es": _x_es, "en": _x_en, "zh": _x_zh}

# 24-11-2026 (barrido de traducciones): lo que escribe la generación desde plantilla
# (`generacion.py`) en la descripción de cada tarea y en el alcance del programa.
# Los roles RACI de las plantillas son claves (`responsable_cumplimiento`): nunca
# se escriben crudas, se escribe su nombre en el idioma de quien genera.
_GENERACION = {
    "controles": ("Controles", "Controls", "控制措施"),
    "entregables": ("Entregables", "Deliverables", "交付物"),
    "sede": ("Sede {n}", "Site {n}", "场所 {n}"),
    "documento_plantilla": ("Plantilla {clave}", "Template {clave}", "模板 {clave}"),
    "rol.auditoria_interna": ("Auditoría interna", "Internal audit", "内部审计"),
    "rol.direccion": ("Dirección", "Management", "管理层"),
    "rol.finanzas": ("Finanzas", "Finance", "财务部门"),
    "rol.ot": ("OT", "OT", "运营技术（OT）部门"),
    "rol.propietario_proceso": ("Propietario del proceso", "Process owner", "流程负责人"),
    "rol.proveedor": ("Proveedor", "Supplier", "供应商"),
    "rol.responsable_cumplimiento": ("Responsable de cumplimiento", "Compliance Officer", "合规负责人"),
    "rol.responsable_seguridad": ("Responsable de seguridad", "Security Officer", "安全负责人"),
    "rol.rrhh": ("RR. HH.", "HR", "人力资源部门"),
    "rol.ti": ("TI", "IT", "信息技术（IT）部门"),
}
for _clave, (_g_es, _g_en, _g_zh) in _GENERACION.items():
    TEXTOS_CERTIFICACIONES[f"cert.generacion.{_clave}"] = {"es": _g_es, "en": _g_en, "zh": _g_zh}
