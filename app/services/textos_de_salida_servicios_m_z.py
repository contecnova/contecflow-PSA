"""Textos de salida de los servicios m-z (23-11-2026).

Bloque propio de `textos_de_salida.TEXTOS` (se fusiona al importarlo, como
`textos_de_salida_itsm`). Lo que hay aqui lo escribian los servicios en
castellano o ingles fijo (avisos, titulos de alertas, motivos, descripciones de
alertas de cumplimiento, pasos del asistente de causa raiz, catalogo del
marketplace...). Operadores: es/en/zh. Lo que redacta una persona o la empresa
no esta aqui: sale como lo escribio.

`texto_para` y `aviso_de` viven en `textos_de_salida` (prueba global
23-11-2026: aqui cerraban el ciclo textos_de_salida -> este bloque ->
textos_de_salida). Este modulo solo tiene datos y no importa nada de la app.
"""
from __future__ import annotations

from typing import Optional

TEXTOS_SERVICIOS_M_Z: dict[str, dict[str, str]] = {}


def _bloque(d: dict[str, dict[str, str]]) -> None:
    TEXTOS_SERVICIOS_M_Z.update(d)


_bloque({
    "presupuestos.campana_sin_enviar.titulo": {"es": "Presupuesto «{nombre}» sin enviar", "en": "Budget «{nombre}» not submitted", "zh": "预算「{nombre}」尚未提交"},
    "presupuestos.campana_sin_enviar.cuerpo": {"es": "La campaña «{campana}» cierra el {fecha} ({dias} días).", "en": "The «{campana}» campaign closes on {fecha} ({dias} days).", "zh": "「{campana}」活动将于 {fecha} 截止（还剩 {dias} 天）。"},
    "presupuestos.rechazado_bandeja": {"es": "Rechazado en la bandeja de aprobaciones", "en": "Rejected in the approvals inbox", "zh": "已在审批收件箱中拒绝"},
    "presupuestos.traspaso.ampliacion": {"es": "Ampliación en {nombre} · {importe} {moneda}", "en": "Increase in {nombre} · {importe} {moneda}", "zh": "{nombre} 追加预算 · {importe} {moneda}"},
    "presupuestos.traspaso.traspaso": {"es": "Traspaso en {nombre} · {importe} {moneda}", "en": "Transfer in {nombre} · {importe} {moneda}", "zh": "{nombre} 预算调拨 · {importe} {moneda}"},
    "presupuestos.alerta.critica": {"es": "Presupuesto consumido al {pct} %: {nombre}", "en": "Budget {pct} % consumed: {nombre}", "zh": "预算已消耗 {pct} %：{nombre}"},
    "presupuestos.alerta.excedido": {"es": "Presupuesto al {pct} %: {nombre}", "en": "Budget at {pct} %: {nombre}", "zh": "预算已达 {pct} %：{nombre}"},
    "presupuestos.alerta.prevision": {"es": "La previsión al cierre llega al {pct} % del plan: {nombre}", "en": "The forecast at close reaches {pct} % of plan: {nombre}", "zh": "结账时预测达到计划的 {pct} %：{nombre}"},
    "presupuestos.alerta.detalle": {"es": "Plan {plan}, real {real}, comprometido {comprometido}, previsión {prevision}", "en": "Plan {plan}, actual {real}, committed {comprometido}, forecast {prevision}", "zh": "计划 {plan}，实际 {real}，已承诺 {comprometido}，预测 {prevision}"},
    "milestone.nota_factura": {"es": "Factura por milestone: {nombre}", "en": "Invoice for milestone: {nombre}", "zh": "里程碑发票：{nombre}"},
    "milestone.aprobacion.titulo": {"es": "Aprobación solicitada: {nombre}", "en": "Approval requested: {nombre}", "zh": "已请求审批：{nombre}"},
    "milestone.aprobacion.cuerpo": {"es": "{quien} solicita aprobar el milestone '{nombre}' del proyecto {proyecto}.{nota}", "en": "{quien} asks for approval of milestone '{nombre}' of project {proyecto}.{nota}", "zh": "{quien} 请求审批项目 {proyecto} 的里程碑「{nombre}」。{nota}"},
    "milestone.aprobacion.nota": {"es": " Nota: {mensaje}", "en": " Note: {mensaje}", "zh": " 备注：{mensaje}"},
    "milestone.aprobado.titulo": {"es": "Milestone aprobado: {nombre}", "en": "Milestone approved: {nombre}", "zh": "里程碑已批准：{nombre}"},
    "milestone.aprobado.cuerpo": {"es": "{quien} ha aprobado el milestone. Ya puedes generar la factura.", "en": "{quien} approved the milestone. You can now generate the invoice.", "zh": "{quien} 已批准该里程碑，现在可以生成发票。"},
    "milestone.rechazado.titulo": {"es": "Milestone rechazado: {nombre}", "en": "Milestone rejected: {nombre}", "zh": "里程碑已拒绝：{nombre}"},
    "milestone.rechazado.cuerpo": {"es": "{quien} rechazó el milestone. Motivo: {motivo}", "en": "{quien} rejected the milestone. Reason: {motivo}", "zh": "{quien} 拒绝了该里程碑。原因：{motivo}"},
    "perf.sin_cierre": {"es": "sin fecha de cierre", "en": "no closing date", "zh": "无截止日期"},
    "perf.hoy": {"es": "hoy", "en": "today", "zh": "今天"},
    "perf.en_dias": {"es": "en {dias} día(s) ({fecha})", "en": "in {dias} day(s) ({fecha})", "zh": "{dias} 天后（{fecha}）"},
    "perf.titulo_uno": {"es": "Tienes {n} evaluación pendiente — cierra {cuando}", "en": "You have {n} pending review — closes {cuando}", "zh": "您有 {n} 项待办评估——{cuando}截止"},
    "perf.titulo_varias": {"es": "Tienes {n} evaluaciones pendientes — el ciclo cierra {cuando}", "en": "You have {n} pending reviews — the cycle closes {cuando}", "zh": "您有 {n} 项待办评估——周期{cuando}截止"},
    "perf.cuerpo": {"es": "Ciclo: {ciclo}. Accede al módulo de evaluaciones para completarlas.", "en": "Cycle: {ciclo}. Open the reviews module to complete them.", "zh": "周期：{ciclo}。请进入评估模块完成评估。"},
    "proveedores.informe_nuevo.titulo": {"es": "{proveedor}: informe nuevo del proveedor ({tipo})", "en": "{proveedor}: new report from the supplier ({tipo})", "zh": "{proveedor}：供应商提交了新报告（{tipo}）"},
    "proveedores.informe_nuevo.cuerpo": {"es": "{persona} lo ha subido desde el portal del proveedor. Revísalo en su ficha.", "en": "{persona} uploaded it from the supplier portal. Review it on its record.", "zh": "{persona} 已通过供应商门户上传。请在其档案中查看。"},
})

_bloque({
    **{f"metricas.tarea.{k}": {"es": es, "en": en, "zh": zh} for k, es, en, zh in (
        ("todo", "Por hacer", "To do", "待办"), ("in_progress", "En curso", "In progress", "进行中"),
        ("in_review", "En revisión", "In review", "审核中"), ("done", "Hecho", "Done", "已完成"),
        ("blocked", "Bloqueado", "Blocked", "已阻塞"))},
    **{f"metricas.proyecto.{k}": {"es": es, "en": en, "zh": zh} for k, es, en, zh in (
        ("planning", "Planificación", "Planning", "规划中"), ("active", "Activo", "Active", "进行中"),
        ("paused", "Pausado", "Paused", "已暂停"), ("closed", "Cerrado", "Closed", "已关闭"),
        ("cancelled", "Cancelado", "Cancelled", "已取消"))},
    **{f"metricas.tipo_proyecto.{k}": {"es": es, "en": en, "zh": zh} for k, es, en, zh in (
        ("development", "Desarrollo", "Development", "开发"), ("maintenance", "Mantenimiento", "Maintenance", "维护"),
        ("rd", "I+D", "R&D", "研发"), ("internal", "Interno", "Internal", "内部"),
        ("consulting", "Consultoría", "Consulting", "咨询"), ("sin_tipo", "Sin tipo", "No type", "无类型"))},
    **{f"metricas.entregable.{k}": {"es": es, "en": en, "zh": zh} for k, es, en, zh in (
        ("planned", "Planificado", "Planned", "已计划"), ("in_progress", "En curso", "In progress", "进行中"),
        ("in_review", "En revisión", "In review", "审核中"), ("delivered", "Entregado", "Delivered", "已交付"),
        ("accepted", "Aceptado", "Accepted", "已验收"), ("rejected", "Rechazado", "Rejected", "已拒绝"))},
    **{f"metricas.riesgo.{k}": {"es": es, "en": en, "zh": zh} for k, es, en, zh in (
        ("critical", "Crítico", "Critical", "严重"), ("high", "Alto", "High", "高"),
        ("medium", "Medio", "Medium", "中"), ("low", "Bajo", "Low", "低"))},
})

_bloque({
    "psa.imputacion_rechazada.titulo": {"es": "Imputación rechazada por manager", "en": "Time entry rejected by manager", "zh": "工时记录被经理拒绝"},
    "psa.imputacion_rechazada.cuerpo": {"es": "Tu imputación ha sido rechazada y queda pendiente de corrección.", "en": "Your time entry was rejected and is pending correction.", "zh": "您的工时记录已被拒绝，等待更正。"},
    "psa.parte.decidido": {"es": "Decidido en Partes de horas por {quien}", "en": "Decided in Timesheets by {quien}", "zh": "已由 {quien} 在工时表中决定"},
    "psa.parte.abrir": {"es": "Parte de horas semana {semana} · {horas} h", "en": "Timesheet week {semana} · {horas} h", "zh": "第 {semana} 周工时表 · {horas} 小时"},
    "psa.parte.devuelto": {"es": "Devuelto para corrección por {quien}", "en": "Sent back for correction by {quien}", "zh": "已由 {quien} 退回更正"},
    "psa.parte.prefijo_devuelto": {"es": "[Devuelto para corrección]", "en": "[Sent back for correction]", "zh": "[已退回更正]"},
})

_bloque({
    "sesion.riesgo.ip_change": {"es": "Cambio de IP", "en": "IP change", "zh": "IP 地址变化"},
    "sesion.riesgo.asn_change": {"es": "Cambio de ASN", "en": "ASN change", "zh": "ASN 变化"},
    "sesion.riesgo.country_change": {"es": "Cambio de país", "en": "Country change", "zh": "国家/地区变化"},
    "sesion.riesgo.ua_change": {"es": "Cambio de agente de usuario", "en": "User agent change", "zh": "用户代理变化"},
    "sesion.riesgo.anonymizing_asn": {"es": "ASN/ISP con perfil de anonimización u hosting", "en": "ASN/ISP with an anonymisation or hosting profile", "zh": "ASN/ISP 具有匿名化或托管特征"},
    "sesion.riesgo.ip_missing": {"es": "IP ausente", "en": "IP missing", "zh": "缺少 IP"},
    "sesion.riesgo.ip_private": {"es": "IP privada/no enrutable", "en": "Private/non-routable IP", "zh": "私有/不可路由 IP"},
})

_bloque({
    "raci.r_completitud": {"es": 'Alta tasa de completitud: {completion_rate_pct}% de tareas entregadas', "en": 'High completion rate: {completion_rate_pct}% of tasks delivered', "zh": '完成率高：已交付 {completion_rate_pct}% 的任务'},
    "raci.r_predecible": {"es": 'Excelente predictibilidad — casi sin carryover', "en": 'Excellent predictability — almost no carryover', "zh": '可预测性极佳——几乎没有遗留任务'},
    "raci.r_sin_bloqueos": {"es": 'Ninguna tarea bloqueada durante el sprint', "en": 'No blocked tasks during the sprint', "zh": '迭代期间没有被阻塞的任务'},
    "raci.r_velocity": {"es": 'Velocity muy ajustada a la planificación ({velocity_ratio_pct}%)', "en": 'Velocity very close to the plan ({velocity_ratio_pct}%)', "zh": '速度与计划高度吻合（{velocity_ratio_pct}%）'},
    "raci.r_completitud_baja": {"es": 'Tasa de completitud baja ({completion_rate_pct}%) — revisar estimaciones o scope', "en": 'Low completion rate ({completion_rate_pct}%) — review estimates or scope', "zh": '完成率偏低（{completion_rate_pct}%）——请复核估算或范围'},
    "raci.a_criterios": {"es": 'Revisar criterios de aceptación antes del siguiente sprint planning', "en": 'Review acceptance criteria before the next sprint planning', "zh": '在下次迭代规划前复核验收标准'},
    "raci.r_bloqueadas": {"es": '{blocked} tarea(s) bloqueadas — identificar patrones de impedimentos', "en": '{blocked} blocked task(s) — identify impediment patterns', "zh": '{blocked} 项任务被阻塞——请找出阻碍的规律'},
    "raci.a_standup": {"es": 'Daily standup: escalar bloqueos en máximo 24h', "en": 'Daily standup: escalate blockers within 24h', "zh": '每日站会：在 24 小时内上报阻塞'},
    "raci.r_scope_creep": {"es": 'Scope creep detectado: {added_mid_sprint} tareas añadidas a mitad de sprint', "en": 'Scope creep detected: {added_mid_sprint} tasks added mid-sprint', "zh": '检测到范围蔓延：迭代中途新增了 {added_mid_sprint} 项任务'},
    "raci.a_politica": {"es": 'Reforzar la política de no añadir al sprint en curso salvo urgencias', "en": 'Reinforce the policy of not adding to the running sprint except for emergencies', "zh": '强化规定：除紧急情况外不向进行中的迭代添加任务'},
    "raci.r_carryover": {"es": '{carryover} tarea(s) con carryover — afecta a la previsibilidad', "en": '{carryover} task(s) carried over — hurts predictability', "zh": '{carryover} 项任务遗留——影响可预测性'},
    "raci.r_velocity_baja": {"es": 'Velocity {velocity_ratio_pct}% — sobreestimación habitual, calibrar story points', "en": 'Velocity {velocity_ratio_pct}% — habitual overestimation, calibrate story points', "zh": '速度 {velocity_ratio_pct}%——经常高估，请校准故事点'},
    "raci.k_optimistas": {"es": 'Estimaciones sistemáticamente optimistas → riesgo de promesas no cumplidas', "en": 'Systematically optimistic estimates → risk of unmet commitments', "zh": '估算系统性偏乐观 → 承诺无法兑现的风险'},
    "raci.a_continuar": {"es": 'Continuar con el ritmo actual; documentar las prácticas que funcionan', "en": 'Keep the current pace; document the practices that work', "zh": '保持当前节奏；记录行之有效的做法'},
    "raci.bien_defecto": {"es": 'Sprint completado — analiza métricas para detectar áreas de mejora', "en": 'Sprint completed — analyse the metrics to find areas for improvement', "zh": '迭代已完成——请分析指标以发现改进领域'},
    "raci.mejorar_defecto": {"es": 'No se detectaron problemas estructurales significativos', "en": 'No significant structural problems were detected', "zh": '未发现重大结构性问题'},
    "raci.b_actual": {"es": 'Sobrecarga actual: {current:.0f}%', "en": 'Current overload: {current:.0f}%', "zh": '当前超负荷：{current:.0f}%'},
    "raci.b_media": {"es": 'Media 4 semanas: {media_4s:.0f}%', "en": '4-week average: {media_4s:.0f}%', "zh": '4 周平均：{media_4s:.0f}%'},
    "raci.b_racha": {"es": '{racha} semanas consecutivas al 100%+', "en": '{racha} consecutive weeks at 100%+', "zh": '连续 {racha} 周达到 100% 以上'},
    "raci.b_alto": {"es": 'Riesgo alto de agotamiento sostenido', "en": 'High risk of sustained burnout', "zh": '持续倦怠风险高'},
    "raci.b_severa": {"es": 'Sobrecarga severa (>130%)', "en": 'Severe overload (>130%)', "zh": '严重超负荷（>130%）'},
    "raci.sin_tareas": {"es": 'No hay tareas completadas en el período indicado', "en": 'There are no completed tasks in the given period', "zh": '所选期间内没有已完成的任务'},
})

_bloque({
    "escenarios.recomendacion_ok": {"es": "El equipo tiene capacidad suficiente para asumir todos los proyectos del escenario.", "en": "The team has enough capacity to take on all the projects in the scenario.", "zh": "团队有足够的产能承接方案中的所有项目。"},
    "escenarios.recomendacion_sobrecarga": {"es": "Se detectan {n} semanas con sobrecarga. Considera retrasar proyectos o ampliar equipo.", "en": "{n} weeks with overload were detected. Consider delaying projects or growing the team.", "zh": "检测到 {n} 周超负荷。请考虑推迟项目或扩充团队。"},
    "escenarios.proyecto_hipotetico": {"es": "Proyecto hipotético", "en": "Hypothetical project", "zh": "假设项目"},
    "avisos.resumen.asunto": {"es": "Resumen diario: {n} aviso(s) sin leer", "en": "Daily digest: {n} unread notice(s)", "zh": "每日摘要：{n} 条未读通知"},
    "avisos.resumen.cuerpo": {"es": "Tienes {n} aviso(s) sin leer de las últimas 24 horas:", "en": "You have {n} unread notice(s) from the last 24 hours:", "zh": "您有 {n} 条过去 24 小时内的未读通知："},
    "avisos.resumen.resto": {"es": "… y {resto} más.", "en": "… and {resto} more.", "zh": "……另外还有 {resto} 条。"},
    "avisos.resumen.abrir": {"es": "Abrir la bandeja", "en": "Open the inbox", "zh": "打开收件箱"},
    "teams.sin_respuesta": {"es": "No encuentro nada sobre eso en la base de conocimiento. He apuntado la pregunta para que alguien la responda.", "en": "I cannot find anything about that in the knowledge base. I have logged the question so someone can answer it.", "zh": "我在知识库中没有找到相关内容。已记录该问题，会有人来回答。"},
    "teams.ia_no_disponible": {"es": "Ahora mismo no puedo consultar la IA. Prueba más tarde.", "en": "I cannot reach the AI right now. Please try again later.", "zh": "目前无法使用 AI，请稍后再试。"},
    "teams.fuentes": {"es": "Fuentes:", "en": "Sources:", "zh": "来源："},
    "ingresos.reversal": {"es": "Reversal de entrada {entrada}", "en": "Reversal of entry {entrada}", "zh": "冲销分录 {entrada}"},
    "ingresos.hito": {"es": "Hito completado: {nombre}", "en": "Milestone completed: {nombre}", "zh": "里程碑已完成：{nombre}"},
    "ingresos.obligacion": {"es": "Obligación satisfecha: {nombre}", "en": "Obligation satisfied: {nombre}", "zh": "履约义务已完成：{nombre}"},
    "ingresos.tm": {"es": "T&M reconocido hasta {periodo}: {horas}h × {tarifa}", "en": "T&M recognised up to {periodo}: {horas}h × {tarifa}", "zh": "截至 {periodo} 已确认的工时材料收入：{horas} 小时 × {tarifa}"},
    "ingresos.retainer": {"es": "Retainer {periodo}: {transcurridos}/{n} del contrato", "en": "Retainer {periodo}: {transcurridos}/{n} of the contract", "zh": "保留服务费 {periodo}：合同 {transcurridos}/{n}"},
    "ingresos.contrato_completado": {"es": "Contrato completado: todo el importe al cierre", "en": "Completed contract: full amount at close", "zh": "完工合同：结账时确认全部金额"},
    "ingresos.por_avance": {"es": "Por avance: {hechas}/{total} tareas ({pct} %)", "en": "By progress: {hechas}/{total} tasks ({pct} %)", "zh": "按进度：{hechas}/{total} 项任务（{pct} %）"},
})

_bloque({
    "rca.five_whys.1.label": {"es": 'Why #1', "en": 'Why #1', "zh": '为什么 #1'},
    "rca.five_whys.1.prompt": {"es": '¿Por qué ocurrió el problema? Describe el síntoma observable inicial.', "en": 'Why did the problem occur? Describe the initial observable symptom.', "zh": '问题为什么会发生？请描述最初可观察到的症状。'},
    "rca.five_whys.2.label": {"es": 'Why #2', "en": 'Why #2', "zh": '为什么 #2'},
    "rca.five_whys.2.prompt": {"es": '¿Por qué ocurrió lo que describiste en el paso anterior? Profundiza un nivel más.', "en": 'Why did what you described in the previous step happen? Go one level deeper.', "zh": '上一步所描述的情况为什么会发生？请再深入一层。'},
    "rca.five_whys.3.label": {"es": 'Why #3', "en": 'Why #3', "zh": '为什么 #3'},
    "rca.five_whys.3.prompt": {"es": '¿Por qué se produjo esa causa? Continúa explorando hacia atrás en la cadena causal.', "en": 'Why did that cause occur? Keep exploring backwards along the causal chain.', "zh": '该原因为什么会出现？请沿因果链继续向前追溯。'},
    "rca.five_whys.4.label": {"es": 'Why #4', "en": 'Why #4', "zh": '为什么 #4'},
    "rca.five_whys.4.prompt": {"es": '¿Por qué existía esa condición? Busca el factor sistémico o de proceso subyacente.', "en": 'Why did that condition exist? Look for the underlying systemic or process factor.', "zh": '该条件为什么存在？请寻找背后的系统性或流程性因素。'},
    "rca.five_whys.5.label": {"es": 'Why #5 — Causa Raíz', "en": 'Why #5 — Root cause', "zh": '为什么 #5——根本原因'},
    "rca.five_whys.5.prompt": {"es": '¿Por qué existía ese factor? Esta respuesta debería apuntar directamente a la causa raíz. Resume la causa raíz final aquí.', "en": 'Why did that factor exist? This answer should point directly to the root cause. Summarise the final root cause here.', "zh": '该因素为什么存在？此回答应直接指向根本原因。请在此总结最终的根本原因。'},
    "rca.fishbone.1.label": {"es": 'Personas', "en": 'People', "zh": '人员'},
    "rca.fishbone.1.prompt": {"es": '¿Qué factores humanos o de equipo pudieron contribuir al problema? (falta de formación, errores humanos, comunicación deficiente, etc.)', "en": 'Which human or team factors may have contributed to the problem? (lack of training, human error, poor communication, etc.)', "zh": '哪些人为或团队因素可能导致了该问题？（缺乏培训、人为失误、沟通不畅等）'},
    "rca.fishbone.2.label": {"es": 'Proceso', "en": 'Process', "zh": '流程'},
    "rca.fishbone.2.prompt": {"es": '¿Qué fallos en procesos o procedimientos contribuyeron? (procedimientos ausentes, obsoletos, no seguidos, etc.)', "en": 'Which process or procedure failures contributed? (missing, outdated or unfollowed procedures, etc.)', "zh": '哪些流程或规程缺陷起了作用？（规程缺失、过时、未被遵守等）'},
    "rca.fishbone.3.label": {"es": 'Tecnología', "en": 'Technology', "zh": '技术'},
    "rca.fishbone.3.prompt": {"es": '¿Qué factores tecnológicos o de infraestructura influyeron? (bugs de software, fallos de hardware, configuración incorrecta, etc.)', "en": 'Which technology or infrastructure factors played a part? (software bugs, hardware failures, wrong configuration, etc.)', "zh": '哪些技术或基础设施因素产生了影响？（软件缺陷、硬件故障、配置错误等）'},
    "rca.fishbone.4.label": {"es": 'Entorno', "en": 'Environment', "zh": '环境'},
    "rca.fishbone.4.prompt": {"es": '¿Qué factores del entorno o externos afectaron? (condiciones de red, proveedores externos, cambios de carga, etc.)', "en": 'Which environmental or external factors had an effect? (network conditions, external suppliers, load changes, etc.)', "zh": '哪些环境或外部因素产生了影响？（网络状况、外部供应商、负载变化等）'},
    "rca.fishbone.5.label": {"es": 'Materiales / Datos', "en": 'Materials / Data', "zh": '物料 / 数据'},
    "rca.fishbone.5.prompt": {"es": '¿Problemas con datos, configuraciones, dependencias o insumos del sistema? (datos corruptos, configuraciones incorrectas, librerías desactualizadas, etc.)', "en": 'Problems with data, configurations, dependencies or system inputs? (corrupt data, wrong configurations, outdated libraries, etc.)', "zh": '数据、配置、依赖项或系统输入是否存在问题？（数据损坏、配置错误、库版本过旧等）'},
    "rca.fishbone.6.label": {"es": 'Métricas / Monitorización', "en": 'Metrics / Monitoring', "zh": '指标 / 监控'},
    "rca.fishbone.6.prompt": {"es": '¿Existían alertas, umbrales o métricas que fallaron en detectar o prevenir el problema? (falta de alertas, umbrales mal calibrados, ausencia de observabilidad, etc.)', "en": 'Were there alerts, thresholds or metrics that failed to detect or prevent the problem? (missing alerts, badly tuned thresholds, no observability, etc.)', "zh": '是否有告警、阈值或指标未能发现或预防该问题？（缺少告警、阈值设置不当、缺乏可观测性等）'},
    "rca.itil_standard.1.label": {"es": 'Cronología', "en": 'Timeline', "zh": '时间线'},
    "rca.itil_standard.1.prompt": {"es": 'Describe la cronología del incidente: ¿cuándo comenzó, qué eventos sucedieron, cuándo fue detectado y resuelto? Incluye timestamps aproximados.', "en": 'Describe the incident timeline: when did it start, what events happened, when was it detected and resolved? Include approximate timestamps.', "zh": '描述事件时间线：何时开始、发生了哪些事件、何时被发现和解决？请包含大致时间点。'},
    "rca.itil_standard.2.label": {"es": 'Factores Contribuyentes', "en": 'Contributing factors', "zh": '促成因素'},
    "rca.itil_standard.2.prompt": {"es": 'Lista todos los factores que contribuyeron al problema. Considera: cambios recientes, carga inusual, deuda técnica, dependencias externas y cualquier condición preexistente.', "en": 'List every factor that contributed to the problem. Consider: recent changes, unusual load, technical debt, external dependencies and any pre-existing condition.', "zh": '列出所有促成该问题的因素。请考虑：近期变更、异常负载、技术债务、外部依赖以及任何既有条件。'},
    "rca.itil_standard.3.label": {"es": 'Enunciado de Causa Raíz', "en": 'Root cause statement', "zh": '根本原因陈述'},
    "rca.itil_standard.3.prompt": {"es": 'Formula un enunciado claro y conciso de la causa raíz. Debe responder a: ¿qué falló exactamente y por qué ocurrió? Evita síntomas — apunta al origen.', "en": 'Write a clear, concise root cause statement. It must answer: what exactly failed and why did it happen? Avoid symptoms — point to the origin.', "zh": '请给出清晰简洁的根本原因陈述。须回答：究竟是什么出了问题，为什么会发生？避免只写症状——要指向源头。'},
    "rca.itil_standard.4.label": {"es": 'Acciones de Prevención', "en": 'Prevention actions', "zh": '预防措施'},
    "rca.itil_standard.4.prompt": {"es": '¿Qué acciones concretas evitarán la recurrencia? Incluye: cambios de configuración, mejoras de proceso, actualizaciones de monitorización y responsables.', "en": 'Which concrete actions will prevent recurrence? Include: configuration changes, process improvements, monitoring updates and owners.', "zh": '哪些具体措施可以避免再次发生？请包括：配置变更、流程改进、监控更新及负责人。'},
    "rca.plantilla.five_whys.nombre": {"es": "5 Whys (Toyota)", "en": "5 Whys (Toyota)", "zh": "5 个为什么（丰田）"},
    "rca.plantilla.five_whys.descripcion": {"es": "Técnica iterativa de 5 preguntas '¿Por qué?' para llegar a la causa raíz. Ideal para problemas simples con cadena causal lineal.", "en": "Iterative technique of 5 'Why?' questions to reach the root cause. Ideal for simple problems with a linear causal chain.", "zh": "通过连续 5 次追问“为什么”找到根本原因的迭代技术。适合因果链单一的简单问题。"},
    "rca.plantilla.fishbone.nombre": {"es": "Diagrama de Ishikawa (Fishbone)", "en": "Ishikawa diagram (Fishbone)", "zh": "石川图（鱼骨图）"},
    "rca.plantilla.fishbone.descripcion": {"es": "Analiza 6 categorías de causas: Personas, Proceso, Tecnología, Entorno, Materiales/Datos, Métricas. Ideal para problemas multifactoriales.", "en": "Analyses 6 categories of causes: People, Process, Technology, Environment, Materials/Data, Metrics. Ideal for multi-factor problems.", "zh": "分析 6 类原因：人员、流程、技术、环境、物料/数据、指标。适合多因素问题。"},
    "rca.plantilla.itil_standard.nombre": {"es": "Análisis ITIL Estándar", "en": "Standard ITIL analysis", "zh": "标准 ITIL 分析"},
    "rca.plantilla.itil_standard.descripcion": {"es": "Proceso ITIL de 4 pasos: Cronología → Factores contribuyentes → Enunciado de causa raíz → Acciones de prevención.", "en": "4-step ITIL process: Timeline → Contributing factors → Root cause statement → Prevention actions.", "zh": "ITIL 四步流程：时间线 → 促成因素 → 根本原因陈述 → 预防措施。"},
    "rca.fishbone.titulo": {"es": "Análisis Fishbone:", "en": "Fishbone analysis:", "zh": "鱼骨图分析："},
})

_bloque({
    "slack.asignarme": {"es": "Asignarme", "en": "Assign to me", "zh": "分配给我"},
    "slack.en_curso": {"es": "En curso", "en": "In progress", "zh": "进行中"},
    "slack.abrir": {"es": "Abrir", "en": "Open", "zh": "打开"},
    "slack.uso_ticket": {"es": "Uso: ticket <asunto>", "en": "Usage: ticket <subject>", "zh": "用法：ticket <主题>"},
    "slack.ticket_creado": {"es": "Ticket creado: {numero}", "en": "Ticket created: {numero}", "zh": "工单已创建：{numero}"},
    "slack.ticket_creado_hilo": {"es": "Ticket creado: {numero}. Responde en su hilo.", "en": "Ticket created: {numero}. Reply in its thread.", "zh": "工单已创建：{numero}。请在其讨论串中回复。"},
    "slack.uso_comentar": {"es": "Uso: comentar <número> <texto>", "en": "Usage: comment <number> <text>", "zh": "用法：comment <编号> <文本>"},
    "slack.comentario_anadido": {"es": "Comentario añadido a {numero}", "en": "Comment added to {numero}", "zh": "已向 {numero} 添加评论"},
    "slack.asignado_a": {"es": "{numero} asignado a {quien}", "en": "{numero} assigned to {quien}", "zh": "{numero} 已分配给 {quien}"},
    "slack.n_en_curso": {"es": "{numero} en curso", "en": "{numero} in progress", "zh": "{numero} 进行中"},
    "slack.uso_resolver": {"es": "Uso: resolver <número> <resolución>", "en": "Usage: resolve <number> <resolution>", "zh": "用法：resolve <编号> <解决方案>"},
    "slack.n_resuelto": {"es": "{numero} resuelto", "en": "{numero} resolved", "zh": "{numero} 已解决"},
    "slack.sin_usuario": {"es": "No encuentro tu usuario de Contecflow para este Slack.", "en": "I cannot find your Contecflow user for this Slack account.", "zh": "未找到与此 Slack 账号对应的 Contecflow 用户。"},
    "slack.adjunto_no_disponible": {"es": "[adjunto no disponible: {nombre}]", "en": "[attachment not available: {nombre}]", "zh": "[附件不可用：{nombre}]"},
    "slack.adjunto_rechazado": {"es": "[adjunto rechazado (tamaño): {nombre}]", "en": "[attachment rejected (size): {nombre}]", "zh": "[附件被拒绝（大小）：{nombre}]"},
    "slack.adjunto": {"es": "[adjunto]", "en": "[attachment]", "zh": "[附件]"},
    "slack.vacio": {"es": "[vacío]", "en": "[empty]", "zh": "[空]"},
})

_bloque({
    "sla.nota_pausado": {"es": "SLA pausado", "en": "SLA paused", "zh": "SLA 已暂停"},
    "sla.nota_reanudado": {"es": "SLA reanudado — {minutos} min pausado", "en": "SLA resumed — paused for {minutos} min", "zh": "SLA 已恢复——已暂停 {minutos} 分钟"},
})

_bloque({
    'cambio_rollout.fase.1.nombre': {"es": 'Validación previa al cambio', "en": 'Pre-change validation', "zh": '变更前验证'},
    'cambio_rollout.fase.1.paso.1': {"es": 'Comprobar que todos los sistemas están en línea', "en": 'Verify all systems online', "zh": '确认所有系统在线'},
    'cambio_rollout.fase.1.paso.2': {"es": 'Comprobar el espacio en disco', "en": 'Check disk space', "zh": '检查磁盘空间'},
    'cambio_rollout.fase.1.paso.3': {"es": 'Verificar que las copias de seguridad han terminado', "en": 'Verify backups completed', "zh": '确认备份已完成'},
    'cambio_rollout.fase.1.paso.4': {"es": 'Confirmar la aprobación del CAB', "en": 'Confirm CAB approval', "zh": '确认 CAB 已批准'},
    'cambio_rollout.fase.1.check.1': {"es": 'Salud del sistema', "en": 'System health', "zh": '系统健康'},
    'cambio_rollout.fase.1.check.2': {"es": 'Conectividad', "en": 'Connectivity', "zh": '连通性'},
    'cambio_rollout.fase.1.check.3': {"es": 'Verificación de copias', "en": 'Backup verification', "zh": '备份验证'},
    'cambio_rollout.fase.2.nombre': {"es": 'Preparar la vuelta atrás', "en": 'Prepare rollback', "zh": '准备回退'},
    'cambio_rollout.fase.2.paso.1': {"es": 'Crear instantáneas del sistema', "en": 'Create system snapshots', "zh": '创建系统快照'},
    'cambio_rollout.fase.2.paso.2': {"es": 'Exportar la configuración actual', "en": 'Export current config', "zh": '导出当前配置'},
    'cambio_rollout.fase.2.paso.3': {"es": 'Documentar el estado actual', "en": 'Document current state', "zh": '记录当前状态'},
    'cambio_rollout.fase.2.paso.4': {"es": 'Probar el procedimiento de vuelta atrás', "en": 'Test rollback procedure', "zh": '测试回退流程'},
    'cambio_rollout.fase.2.check.1': {"es": 'Instantáneas creadas', "en": 'Snapshots created', "zh": '快照已创建'},
    'cambio_rollout.fase.2.check.2': {"es": 'Configuración exportada', "en": 'Config exported', "zh": '配置已导出'},
    'cambio_rollout.fase.3.nombre': {"es": 'Aplicar el cambio', "en": 'Apply change', "zh": '实施变更'},
    'cambio_rollout.fase.3.paso.1': {"es": 'Ejecutar el despliegue', "en": 'Execute deployment', "zh": '执行部署'},
    'cambio_rollout.fase.3.paso.2': {"es": 'Vigilar los recursos del sistema', "en": 'Monitor system resources', "zh": '监控系统资源'},
    'cambio_rollout.fase.3.paso.3': {"es": 'Estar atento a los errores', "en": 'Watch for errors', "zh": '留意错误'},
    'cambio_rollout.fase.3.paso.4': {"es": 'Registrar todas las actividades', "en": 'Log all activities', "zh": '记录所有操作'},
    'cambio_rollout.fase.3.check.1': {"es": 'Despliegue completado', "en": 'Deployment completed', "zh": '部署完成'},
    'cambio_rollout.fase.3.check.2': {"es": 'Sin errores críticos', "en": 'No critical errors', "zh": '无严重错误'},
    'cambio_rollout.fase.4.nombre': {"es": 'Validación posterior al cambio', "en": 'Post-change validation', "zh": '变更后验证'},
    'cambio_rollout.fase.4.paso.1': {"es": 'Verificar que todos los servicios funcionan', "en": 'Verify all services running', "zh": '确认所有服务正在运行'},
    'cambio_rollout.fase.4.paso.2': {"es": 'Ejecutar comprobaciones de salud', "en": 'Run health checks', "zh": '运行健康检查'},
    'cambio_rollout.fase.4.paso.3': {"es": 'Validar la funcionalidad', "en": 'Validate functionality', "zh": '验证功能'},
    'cambio_rollout.fase.4.paso.4': {"es": 'Revisar las métricas de rendimiento', "en": 'Check performance metrics', "zh": '检查性能指标'},
    'cambio_rollout.fase.4.check.1': {"es": 'Servicios sanos', "en": 'Services healthy', "zh": '服务正常'},
    'cambio_rollout.fase.4.check.2': {"es": 'Rendimiento aceptable', "en": 'Performance acceptable', "zh": '性能可接受'},
    'cambio_rollout.fase.5.nombre': {"es": 'Comunicación y cierre', "en": 'Communication & closeout', "zh": '沟通与收尾'},
    'cambio_rollout.fase.5.paso.1': {"es": 'Avisar a los interesados', "en": 'Notify stakeholders', "zh": '通知相关方'},
    'cambio_rollout.fase.5.paso.2': {"es": 'Actualizar la documentación', "en": 'Update documentation', "zh": '更新文档'},
    'cambio_rollout.fase.5.paso.3': {"es": 'Registrar métricas', "en": 'Record metrics', "zh": '记录指标'},
    'cambio_rollout.fase.5.paso.4': {"es": 'Cerrar el ticket del cambio', "en": 'Close change ticket', "zh": '关闭变更工单'},
    'cambio_rollout.fase.5.check.1': {"es": 'Interesados avisados', "en": 'Stakeholders notified', "zh": '相关方已通知'},
    'cambio_rollout.puerta.critico': {"es": 'Aprobación manual antes de cada fase', "en": 'Manual approval before each phase', "zh": '每个阶段前需人工批准'},
    'cambio_rollout.puerta.alto': {"es": 'Aprobación manual antes de la fase de despliegue', "en": 'Manual approval before deployment phase', "zh": '部署阶段前需人工批准'},
    'cambio_rollout.puerta.emergencia': {"es": 'Monitorización continua durante la ejecución', "en": 'Continuous monitoring during execution', "zh": '执行期间持续监控'},
    'cambio_rollout.motivo_automatizacion': {"es": 'Nivel de riesgo: {riesgo}, tipo: {tipo}', "en": 'Risk level: {riesgo}, Type: {tipo}', "zh": '风险级别：{riesgo}，类型：{tipo}'},
    'cambio_rollout.ia.no_evaluable': {"es": 'No se puede evaluar automáticamente', "en": 'Cannot assess automatically', "zh": '无法自动评估'},
    'cambio_rollout.ia.revision_manual': {"es": 'Hace falta revisión manual', "en": 'Manual review required', "zh": '需要人工审核'},
    'cambio_rollout.estado_ajuste': {"es": 'Estado de ejecución del despliegue del cambio {cambio}', "en": 'Rollout execution state for change {cambio}', "zh": '变更 {cambio} 的部署执行状态'},
    'cambio_rollout.rollback.motivo_fase': {"es": 'Fase {fase} ({nombre}) falló: {notas}', "en": 'Phase {fase} ({nombre}) failed: {notas}', "zh": '第 {fase} 阶段（{nombre}）失败：{notas}'},
    'cambio_rollout.rollback_auto.asunto': {"es": '[{producto}] Reversión automática del cambio {cambio}', "en": '[{producto}] Automatic rollback triggered for change {cambio}', "zh": '[{producto}] 变更 {cambio} 已自动回退'},
    'cambio_rollout.rollback_auto.cuerpo': {"es": '<p>Se ha activado una <strong>reversión automática</strong> del cambio <strong>{cambio}</strong>.</p><p><strong>Motivo:</strong> {motivo}</p><p><strong>Fase fallida:</strong> {fase_nombre} (fase {fase})</p><p><strong>Hora:</strong> {hora}</p>', "en": '<p>An <strong>automatic rollback</strong> has been triggered for change <strong>{cambio}</strong>.</p><p><strong>Reason:</strong> {motivo}</p><p><strong>Failed phase:</strong> {fase_nombre} (phase {fase})</p><p><strong>Time:</strong> {hora}</p>', "zh": '<p>变更 <strong>{cambio}</strong> 已触发<strong>自动回退</strong>。</p><p><strong>原因：</strong>{motivo}</p><p><strong>失败阶段：</strong>{fase_nombre}（第 {fase} 阶段）</p><p><strong>时间：</strong>{hora}</p>'},
    'cambio_rollout.rollback_manual.asunto': {"es": '[{producto}] Reversión del cambio {cambio}', "en": '[{producto}] Rollback triggered for change {cambio}', "zh": '[{producto}] 变更 {cambio} 已回退'},
    'cambio_rollout.rollback_manual.cuerpo': {"es": '<p>Se ha activado una <strong>reversión manual</strong> del cambio <strong>{cambio}</strong>.</p><p><strong>Motivo:</strong> {motivo}</p><p><strong>La activó:</strong> {quien}</p><p><strong>Hora:</strong> {hora}</p>', "en": '<p>A <strong>manual rollback</strong> has been triggered for change <strong>{cambio}</strong>.</p><p><strong>Reason:</strong> {motivo}</p><p><strong>Triggered by:</strong> {quien}</p><p><strong>Time:</strong> {hora}</p>', "zh": '<p>变更 <strong>{cambio}</strong> 已触发<strong>手动回退</strong>。</p><p><strong>原因：</strong>{motivo}</p><p><strong>触发人：</strong>{quien}</p><p><strong>时间：</strong>{hora}</p>'},
    'cambio_rollout.completado.asunto': {"es": '[{producto}] Cambio {cambio} implantado con éxito', "en": '[{producto}] Change {cambio} implemented successfully', "zh": '[{producto}] 变更 {cambio} 已成功实施'},
    'cambio_rollout.completado.cuerpo': {"es": '<p>El cambio <strong>{cambio}</strong> se ha <strong>implantado con éxito</strong>.</p><p>Todas las fases del despliegue terminaron el {hora}.</p>', "en": '<p>Change <strong>{cambio}</strong> has been <strong>successfully implemented</strong>.</p><p>All rollout phases completed at {hora}.</p>', "zh": '<p>变更 <strong>{cambio}</strong> 已<strong>成功实施</strong>。</p><p>所有部署阶段已于 {hora} 完成。</p>'},
    'cambio_rollout.fast_track': {"es": '[FAST-TRACK DEL CAB DE EMERGENCIA]', "en": '[EMERGENCY CAB FAST-TRACK]', "zh": '[紧急 CAB 快速通道]'},
})

_bloque({
    'gov.cmm.1': {"es": 'Inicial', "en": 'Initial', "zh": '初始级'},
    'gov.cmm.2': {"es": 'Repetible', "en": 'Repeatable', "zh": '可重复级'},
    'gov.cmm.3': {"es": 'Definido', "en": 'Defined', "zh": '已定义级'},
    'gov.cmm.4': {"es": 'Gestionado', "en": 'Managed', "zh": '已管理级'},
    'gov.cmm.5': {"es": 'Optimizado', "en": 'Optimized', "zh": '优化级'},
    'gov.inc.p1.titulo': {"es": 'Incidentes P1 sin registro de incidente mayor', "en": 'P1 incidents without Major Incident record', "zh": '未登记重大事件的 P1 事件'},
    'gov.inc.p1.detalle': {"es": 'El {pct}% de los incidentes P1 ({n}) no tiene declaración de incidente mayor.', "en": '{pct}% of P1 incidents ({n}) lack a Major Incident declaration.', "zh": '{pct}% 的 P1 事件（{n} 件）没有重大事件声明。'},
    'gov.inc.recurrentes.titulo': {"es": 'Incidentes recurrentes sin registro de problema', "en": 'Recurring incidents without Problem record', "zh": '反复发生但未登记问题的事件'},
    'gov.inc.recurrentes.detalle': {"es": '{n} CIs tuvieron 3 o más incidentes sin problema enlazado.', "en": '{n} CIs had 3+ incidents with no linked Problem.', "zh": '{n} 个配置项发生了 3 次以上事件且未关联问题。'},
    'gov.inc.sla.titulo': {"es": 'Tasa de incumplimiento del SLA de resolución por encima del umbral', "en": 'SLA resolution breach rate above threshold', "zh": 'SLA 解决时限违约率超过阈值'},
    'gov.inc.sla.detalle': {"es": 'El {tasa}% de los incidentes resueltos incumplió el SLA (objetivo <10%).', "en": '{tasa}% of resolved incidents breached SLA (target <10%).', "zh": '{tasa}% 的已解决事件违反了 SLA（目标 <10%）。'},
    'gov.resumen.incidentes': {"es": 'Puntuación de gestión de incidentes: {score}/100 (nivel CMM {nivel} — {etiqueta}). Analizados {n} incidentes en {dias} días.', "en": 'Incident management score: {score}/100 (CMM Level {nivel} — {etiqueta}). Analysed {n} incidents over {dias} days.', "zh": '事件管理得分：{score}/100（CMM 级别 {nivel}——{etiqueta}）。分析了 {dias} 天内的 {n} 件事件。'},
    'gov.chg.pir.titulo': {"es": 'Cambios de emergencia sin PIR (revisión posterior a la implantación)', "en": 'Emergency changes without PIR (Post-Implementation Review)', "zh": '未做 PIR（实施后评审）的紧急变更'},
    'gov.chg.pir.detalle': {"es": 'El {pct}% de los cambios de emergencia no tiene PIR. ITIL exige PIR en todos los cambios de emergencia.', "en": '{pct}% of emergency changes lack a PIR. ITIL requires PIR for all emergency changes.', "zh": '{pct}% 的紧急变更没有 PIR。ITIL 要求所有紧急变更都做 PIR。'},
    'gov.chg.cab.titulo': {"es": 'Cambios normales sin registro de aprobación del CAB', "en": 'Normal changes without CAB approval record', "zh": '没有 CAB 批准记录的常规变更'},
    'gov.chg.cab.detalle': {"es": 'El {pct}% de los cambios normales no tiene aprobador registrado.', "en": '{pct}% of normal changes have no approver recorded.', "zh": '{pct}% 的常规变更没有记录批准人。'},
    'gov.chg.fallos.titulo': {"es": 'Tasa de fallos de cambios por encima del umbral', "en": 'Change failure rate above threshold', "zh": '变更失败率超过阈值'},
    'gov.chg.fallos.detalle': {"es": 'El {tasa}% de los cambios falló (objetivo <10%).', "en": '{tasa}% of changes failed (target <10%).', "zh": '{tasa}% 的变更失败（目标 <10%）。'},
    'gov.chg.estandar.titulo': {"es": 'Cambios estándar con puntuación de riesgo automático elevada', "en": 'Standard changes with elevated auto-risk score', "zh": '自动风险评分偏高的标准变更'},
    'gov.chg.estandar.detalle': {"es": 'Estos cambios se clasificaron como estándar pero puntúan un riesgo ≥{umbral}. Valora reclasificarlos.', "en": 'These changes were classified as Standard but scored ≥{umbral} risk. Consider reclassification.', "zh": '这些变更被归类为标准变更，但风险评分 ≥{umbral}。请考虑重新分类。'},
    'gov.resumen.cambios': {"es": 'Puntuación de gestión de cambios: {score}/100 (nivel CMM {nivel} — {etiqueta}). Analizados {n} cambios implantados en {dias} días.', "en": 'Change management score: {score}/100 (CMM Level {nivel} — {etiqueta}). Analysed {n} implemented changes over {dias} days.', "zh": '变更管理得分：{score}/100（CMM 级别 {nivel}——{etiqueta}）。分析了 {dias} 天内已实施的 {n} 项变更。'},
    'gov.prob.rca.titulo': {"es": 'Problemas abiertos de más de 30 días sin análisis de causa raíz', "en": 'Open problems older than 30 days without RCA', "zh": '超过 30 天仍未做根因分析的未关闭问题'},
    'gov.prob.rca.detalle': {"es": '{n} problemas llevan tiempo abiertos sin causa raíz documentada.', "en": '{n} problems are stale with no root cause documented.', "zh": '{n} 个问题长期未处理且没有记录根本原因。'},
    'gov.prob.auto.titulo': {"es": 'Problemas detectados automáticamente pendientes de revisión humana', "en": 'Auto-detected problems awaiting human review', "zh": '等待人工审核的自动检测问题'},
    'gov.prob.auto.detalle': {"es": 'Los problemas detectados automáticamente necesitan que una persona valide el análisis de causa raíz.', "en": 'Auto-detected problems need RCA validation by a human engineer.', "zh": '自动检测到的问题需要由工程师人工验证根因分析。'},
    'gov.resumen.problemas': {"es": 'Puntuación de gestión de problemas: {score}/100 (nivel CMM {nivel} — {etiqueta}). Analizados {n} problemas en {dias} días.', "en": 'Problem management score: {score}/100 (CMM Level {nivel} — {etiqueta}). Analysed {n} problems over {dias} days.', "zh": '问题管理得分：{score}/100（CMM 级别 {nivel}——{etiqueta}）。分析了 {dias} 天内的 {n} 个问题。'},
    'gov.acc.pendientes.titulo': {"es": 'Tickets de solicitud de acceso sin resolver desde hace más de 30 días', "en": 'Access request tickets unresolved for 30+ days', "zh": '超过 30 天未解决的访问申请工单'},
    'gov.acc.pendientes.detalle': {"es": '{n} tickets de solicitud de acceso llevan abiertos más de 30 días ({pct}% de los tickets de acceso del periodo).', "en": '{n} access request tickets have been open for over 30 days ({pct}% of access tickets in period).', "zh": '{n} 个访问申请工单已开启超过 30 天（占本期访问工单的 {pct}%）。'},
    'gov.acc.inactivas.titulo': {"es": 'Cuentas activas sin inicio de sesión en más de 90 días', "en": 'Active accounts with no login in 90+ days', "zh": '超过 90 天未登录的活跃账号'},
    'gov.acc.inactivas.detalle': {"es": '{n} cuentas de usuario figuran como activas pero no han iniciado sesión en 90 días o más. Valora desactivarlas o revisarlas.', "en": '{n} user accounts are marked active but have not logged in for 90 or more days. Consider disabling or reviewing these accounts.', "zh": '{n} 个用户账号显示为活跃，但已 90 天或更久未登录。请考虑停用或复核这些账号。'},
    'gov.acc.privilegiados.titulo': {"es": 'Tickets de acceso privilegiado sin revisión a tiempo', "en": 'Privileged access tickets without timely review', "zh": '未及时复核的特权访问工单'},
    'gov.acc.privilegiados.detalle': {"es": '{n} tickets de acceso privilegiado (admin/elevado) siguen sin resolver pasada la ventana de revisión de 30 días. El acceso privilegiado debe ser temporal y revisarse.', "en": '{n} privileged access tickets (admin/elevated) remain unresolved beyond the 30-day review window. Privileged access should be time-bound and reviewed.', "zh": '{n} 个特权访问工单（管理员/提升权限）在 30 天复核窗口后仍未解决。特权访问应有时限并接受复核。'},
    'gov.resumen.accesos': {"es": 'Puntuación de revisión de accesos: {score}/100 (nivel CMM {nivel} — {etiqueta}). Analizada la gestión de accesos en {dias} días.', "en": 'Access reviews score: {score}/100 (CMM Level {nivel} — {etiqueta}). Analysed access management over {dias} days.', "zh": '访问复核得分：{score}/100（CMM 级别 {nivel}——{etiqueta}）。分析了 {dias} 天内的访问管理。'},
    'gov.rec.change_management': {"es": 'Implementar registro formal de aprobación CAB para todos los cambios normales.', "en": 'Implement formal CAB approval records for all normal changes.', "zh": '为所有常规变更建立正式的 CAB 批准记录。'},
    'gov.rec.incident_management': {"es": 'Enlazar incidentes P1 con Major Incident automáticamente al crear el ticket.', "en": 'Automatically link P1 incidents to a Major Incident when the ticket is created.', "zh": '创建工单时自动将 P1 事件关联到重大事件。'},
    'gov.rec.problem_management': {"es": 'Establecer SLA interno de 30 días para documentar RCA en problemas abiertos.', "en": 'Set an internal 30-day SLA for documenting RCA on open problems.', "zh": '为未关闭问题设定 30 天的内部 SLA 以完成根因分析文档。'},
    'gov.rec.sla_compliance': {"es": 'Revisar políticas SLA — la tasa de incumplimiento supera el umbral aceptable del 10%.', "en": 'Review SLA policies — the breach rate exceeds the acceptable 10% threshold.', "zh": '复核 SLA 策略——违约率超过可接受的 10% 阈值。'},
    'gov.rec.asset_cmdb': {"es": 'Aumentar cobertura de auto-discovery CMDB — menos del 60% de CIs están descubiertos.', "en": 'Increase CMDB auto-discovery coverage — fewer than 60% of CIs are discovered.', "zh": '提高 CMDB 自动发现覆盖率——已发现的配置项不足 60%。'},
    'gov.rec.access_reviews': {"es": 'Revisar cuentas de usuario inactivas y tickets de acceso sin resolver — implementar revisión periódica de accesos (Access Review Campaign).', "en": 'Review inactive user accounts and unresolved access tickets — implement periodic access reviews (Access Review Campaign).', "zh": '复核不活跃的用户账号和未解决的访问工单——实施定期访问复核（Access Review Campaign）。'},
    'gov.contrato_calidad': {"es": 'Contrato de calidad del Service Desk', "en": 'Service Desk quality contract', "zh": '服务台质量合同'},
})

_bloque({
    'problema.rca_manual': {"es": 'No se pudo determinar automáticamente — hace falta un análisis de causa raíz manual.', "en": 'Unable to determine automatically — manual RCA required.', "zh": '无法自动判定——需要人工进行根因分析。'},
    'problema.auto.base': {"es": 'Incidentes recurrentes', "en": 'Recurring incidents', "zh": '反复发生的事件'},
    'problema.auto.titulo': {"es": '[Detectado automáticamente] {base} — {n} incidentes enlazados', "en": '[Auto-detected] {base} — {n} linked incidents', "zh": '[自动检测] {base}——{n} 个关联事件'},
    'problema.auto.descripcion': {"es": "Problema detectado automáticamente a partir de {n} incidentes correlados de la categoría '{categoria}' con prioridad '{prioridad}'.", "en": "Problem auto-detected from {n} correlated incidents in category '{categoria}' with priority '{prioridad}'.", "zh": '根据类别“{categoria}”、优先级“{prioridad}”下 {n} 个相关事件自动检测到的问题。'},
    'problema.rfc.titulo': {"es": '[RFC] Resolver causa raíz: {titulo}', "en": '[RFC] Resolve root cause: {titulo}', "zh": '[RFC] 解决根本原因：{titulo}'},
    'problema.rfc.descripcion': {"es": 'RFC generado automáticamente a partir del problema {numero}.\n\n**Causa raíz:** {causa}\n\n**Workaround actual:** {workaround}\n\n**Incidentes relacionados:** {incidentes}\n\n**Descripción del problema:** {descripcion}', "en": 'RFC generated automatically from problem {numero}.\n\n**Root cause:** {causa}\n\n**Current workaround:** {workaround}\n\n**Related incidents:** {incidentes}\n\n**Problem description:** {descripcion}', "zh": '根据问题 {numero} 自动生成的 RFC。\n\n**根本原因：**{causa}\n\n**当前临时方案：**{workaround}\n\n**相关事件：**{incidentes}\n\n**问题描述：**{descripcion}'},
    'problema.rfc.pendiente': {"es": 'Pendiente de análisis', "en": 'Pending analysis', "zh": '待分析'},
    'problema.rfc.ninguno': {"es": 'Ninguno', "en": 'None', "zh": '无'},
    'problema.rfc.justificacion': {"es": 'Eliminar la causa raíz del problema {numero}', "en": 'Remove the root cause of problem {numero}', "zh": '消除问题 {numero} 的根本原因'},
    'problema.rfc.impacto': {"es": 'CIs afectados: {cis}', "en": 'Affected CIs: {cis}', "zh": '受影响的配置项：{cis}'},
    'problema.rfc.por_determinar': {"es": 'Por determinar', "en": 'To be determined', "zh": '待确定'},
    'problema.rfc.vuelta_atras': {"es": 'Ver el workaround del problema asociado', "en": 'See the workaround of the linked problem', "zh": '参见关联问题的临时方案'},
})

_bloque({
    'marketplace.desc.salesforce': {"es": 'Sincronización bidireccional de oportunidades, contactos y cuentas.', "en": 'Bidirectional sync of opportunities, contacts and accounts.', "zh": '双向同步商机、联系人和客户账户。'},
    'marketplace.desc.hubspot': {"es": 'Sincroniza negocios, contactos y fases del embudo con HubSpot.', "en": 'Sync deals, contacts and pipeline stages with HubSpot.', "zh": '与 HubSpot 同步交易、联系人和销售漏斗阶段。'},
    'marketplace.desc.sap_s4': {"es": 'Integración financiera: centros de coste, elementos PEP y costes reales.', "en": 'Financial integration: cost centres, WBS elements, actual costs.', "zh": '财务集成：成本中心、WBS 元素和实际成本。'},
    'marketplace.desc.netsuite': {"es": 'Sincroniza proyectos, partes de horas y facturas con NetSuite.', "en": 'Sync projects, time entries and invoices with NetSuite.', "zh": '与 NetSuite 同步项目、工时记录和发票。'},
    'marketplace.desc.workday': {"es": 'Sincroniza plantilla, organigrama y ausencias.', "en": 'Employee roster, org chart, and time-off sync.', "zh": '同步员工名册、组织架构和休假。'},
    'marketplace.desc.bamboohr': {"es": 'Sincroniza empleados, departamentos y saldos de vacaciones.', "en": 'Sync employees, departments and leave balances.', "zh": '同步员工、部门和假期余额。'},
    'marketplace.desc.greenhouse': {"es": 'Importa nuevas incorporaciones y vacantes abiertas para la planificación de recursos.', "en": 'Import new hires and open positions for resource planning.', "zh": '导入新员工和空缺职位，用于资源规划。'},
    'marketplace.desc.jira': {"es": 'Sincronización bidireccional de incidencias, importación de sprints y eventos de webhook.', "en": 'Bidirectional issue sync, sprint import and webhook events.', "zh": '双向同步问题，导入迭代，并支持 Webhook 事件。'},
    'marketplace.desc.github': {"es": 'Estado de las PR, actividad de commits y eventos de despliegue.', "en": 'PR status, commit activity and deployment events.', "zh": 'PR 状态、提交活动和部署事件。'},
    'marketplace.desc.gitlab': {"es": 'Pipelines de CI/CD, merge requests y seguimiento de incidencias.', "en": 'CI/CD pipelines, merge requests and issue tracking.', "zh": 'CI/CD 流水线、合并请求和问题跟踪。'},
    'marketplace.desc.slack': {"es": 'Creación de tareas, registro de horas y notificaciones enriquecidas con Block Kit.', "en": 'Task creation, time logging and rich Block Kit notifications.', "zh": '创建任务、记录工时和丰富的 Block Kit 通知。'},
    'marketplace.desc.teams': {"es": 'Notificaciones con tarjetas adaptativas y comandos de bot.', "en": 'Adaptive card notifications and bot commands.', "zh": '自适应卡片通知和机器人命令。'},
    'marketplace.desc.xero': {"es": 'Sincronización de facturas, reembolsos de gastos y estado de pagos.', "en": 'Invoice sync, expense reimbursements and payment status.', "zh": '发票同步、费用报销和付款状态。'},
    'marketplace.desc.quickbooks': {"es": 'Sincroniza facturas, pagos y la cuenta de resultados por proyecto.', "en": 'Sync invoices, payments and project-level P&L.', "zh": '同步发票、付款和项目级损益。'},
    'marketplace.desc.docusign': {"es": 'Lanza flujos de firma electrónica para contratos y SOW.', "en": 'Trigger e-signature workflows for contracts and SOWs.', "zh": '为合同和工作说明书触发电子签名流程。'},
    'marketplace.desc.stripe': {"es": 'Enlaces de pago, facturación por hitos y gestión de suscripciones.', "en": 'Payment links, milestone billing and subscription management.', "zh": '支付链接、里程碑计费和订阅管理。'},
    'marketplace.desc.azure_devops': {"es": 'Sincroniza elementos de trabajo, pipelines y tableros con Azure DevOps.', "en": 'Work items, pipelines and board sync with Azure DevOps.', "zh": '与 Azure DevOps 同步工作项、流水线和看板。'},
    'marketplace.desc.aws_s3': {"es": 'Guarda documentos de proyecto y copias de seguridad en buckets de S3.', "en": 'Store project documents and backups in S3 buckets.', "zh": '将项目文档和备份存储到 S3 存储桶。'},
    'marketplace.desc.google_workspace': {"es": 'Sincronización de calendario, documentos de Drive y notificaciones de Gmail.', "en": 'Calendar sync, Drive documents and Gmail notifications.', "zh": '日历同步、Drive 文档和 Gmail 通知。'},
    'marketplace.desc.zendesk': {"es": 'Sincronización de tickets entre el Service Desk de Contecflow y Zendesk.', "en": 'Ticket sync between Contecflow Service Desk and Zendesk.', "zh": '在 Contecflow 服务台与 Zendesk 之间同步工单。'},
    'marketplace.desc.servicenow': {"es": 'Integración ITSM: incidentes, cambios y elementos de la CMDB.', "en": 'ITSM integration: incidents, changes and CMDB items.', "zh": 'ITSM 集成：事件、变更和 CMDB 条目。'},
    'marketplace.desc.okta': {"es": 'SSO, aprovisionamiento de usuarios SCIM y sincronización de grupos.', "en": 'SSO, SCIM user provisioning and group sync.', "zh": 'SSO、SCIM 用户配置和组同步。'},
})


# 23-11-2026: correo de restablecimiento de contraseña (operador es/en/zh y portal en sus 8
# idiomas; `seguridad_de_cuentas/restablecimiento.py`, docs/seguridad/politicas_de_cuenta.md).
TEXTOS_SERVICIOS_M_Z.update({
    "restablecer.asunto": {"es": "{marca}: restablecer tu contraseña", "en": "{marca}: reset your password", "zh": "{marca}：重置您的密码", "fr": "{marca} : réinitialiser votre mot de passe", "de": "{marca}: Passwort zurücksetzen", "it": "{marca}: reimposta la tua password", "pt": "{marca}: redefinir a sua palavra-passe", "pl": "{marca}: zresetuj hasło"},
    "restablecer.cuerpo": {"es": "Hola:<br><br>Hemos recibido una solicitud para restablecer tu contraseña de {marca}.<br>Abre este enlace para elegir una nueva (vale {minutos} minutos y una sola vez):<br><a href=\"{url}\">{url}</a><br><br>Si no lo has pedido tú, ignora este correo: tu contraseña no cambia.", "en": "Hello,<br><br>We received a request to reset your {marca} password.<br>Open this link to choose a new one (valid for {minutos} minutes, single use):<br><a href=\"{url}\">{url}</a><br><br>If you did not request this, ignore this email: your password stays the same.", "zh": "您好：<br><br>我们收到了重置您的 {marca} 密码的请求。<br>请打开此链接设置新密码（{minutos} 分钟内有效，仅可使用一次）：<br><a href=\"{url}\">{url}</a><br><br>如果这不是您本人的操作，请忽略此邮件，您的密码不会改变。", "fr": "Bonjour,<br><br>Nous avons reçu une demande de réinitialisation de votre mot de passe {marca}.<br>Ouvrez ce lien pour en choisir un nouveau (valable {minutos} minutes, usage unique) :<br><a href=\"{url}\">{url}</a><br><br>Si vous n'êtes pas à l'origine de cette demande, ignorez ce message : votre mot de passe ne change pas.", "de": "Hallo,<br><br>wir haben eine Anfrage zum Zurücksetzen Ihres {marca}-Passworts erhalten.<br>Öffnen Sie diesen Link, um ein neues festzulegen ({minutos} Minuten gültig, nur einmal verwendbar):<br><a href=\"{url}\">{url}</a><br><br>Falls Sie das nicht angefordert haben, ignorieren Sie diese E-Mail: Ihr Passwort bleibt unverändert.", "it": "Ciao,<br><br>abbiamo ricevuto una richiesta di reimpostazione della tua password di {marca}.<br>Apri questo link per sceglierne una nuova (valido {minutos} minuti, utilizzabile una sola volta):<br><a href=\"{url}\">{url}</a><br><br>Se non l'hai richiesto tu, ignora questa e-mail: la tua password non cambia.", "pt": "Olá,<br><br>Recebemos um pedido para redefinir a sua palavra-passe de {marca}.<br>Abra esta ligação para escolher uma nova (válida durante {minutos} minutos e uma única vez):<br><a href=\"{url}\">{url}</a><br><br>Se não foi você que o pediu, ignore este e-mail: a sua palavra-passe não muda.", "pl": "Dzień dobry,<br><br>otrzymaliśmy prośbę o zresetowanie hasła do {marca}.<br>Otwórz ten link, aby ustawić nowe (ważny {minutos} minut, jednorazowy):<br><a href=\"{url}\">{url}</a><br><br>Jeśli to nie Ty, zignoruj tę wiadomość: Twoje hasło się nie zmieni."},
    "restablecer.cuerpo_forzado": {"es": "Hola:<br><br>Un administrador de {marca} ha pedido que restablezcas tu contraseña y ha cerrado tus sesiones abiertas.<br>Abre este enlace para elegir una nueva (vale {minutos} minutos y una sola vez):<br><a href=\"{url}\">{url}</a><br><br>Si el enlace caduca, usa «¿Olvidaste tu contraseña?» en la pantalla de acceso.", "en": "Hello,<br><br>A {marca} administrator has asked you to reset your password and has signed out your open sessions.<br>Open this link to choose a new one (valid for {minutos} minutes, single use):<br><a href=\"{url}\">{url}</a><br><br>If the link expires, use “Forgot your password?” on the sign-in screen.", "zh": "您好：<br><br>{marca} 的管理员要求您重置密码，并已注销您所有已打开的会话。<br>请打开此链接设置新密码（{minutos} 分钟内有效，仅可使用一次）：<br><a href=\"{url}\">{url}</a><br><br>如果链接已过期，请在登录页面使用“忘记密码？”。", "fr": "Bonjour,<br><br>Un administrateur de {marca} vous demande de réinitialiser votre mot de passe et a fermé vos sessions ouvertes.<br>Ouvrez ce lien pour en choisir un nouveau (valable {minutos} minutes, usage unique) :<br><a href=\"{url}\">{url}</a><br><br>Si le lien expire, utilisez « Mot de passe oublié ? » sur l'écran de connexion.", "de": "Hallo,<br><br>ein Administrator von {marca} hat Sie aufgefordert, Ihr Passwort zurückzusetzen, und Ihre offenen Sitzungen beendet.<br>Öffnen Sie diesen Link, um ein neues festzulegen ({minutos} Minuten gültig, nur einmal verwendbar):<br><a href=\"{url}\">{url}</a><br><br>Wenn der Link abläuft, verwenden Sie „Passwort vergessen?“ auf der Anmeldeseite.", "it": "Ciao,<br><br>un amministratore di {marca} ti ha chiesto di reimpostare la password e ha chiuso le tue sessioni aperte.<br>Apri questo link per sceglierne una nuova (valido {minutos} minuti, utilizzabile una sola volta):<br><a href=\"{url}\">{url}</a><br><br>Se il link scade, usa «Password dimenticata?» nella schermata di accesso.", "pt": "Olá,<br><br>Um administrador de {marca} pediu-lhe que redefina a sua palavra-passe e terminou as suas sessões abertas.<br>Abra esta ligação para escolher uma nova (válida durante {minutos} minutos e uma única vez):<br><a href=\"{url}\">{url}</a><br><br>Se a ligação expirar, use «Esqueceu-se da palavra-passe?» no ecrã de acesso.", "pl": "Dzień dobry,<br><br>administrator {marca} poprosił o zresetowanie hasła i zamknął Twoje otwarte sesje.<br>Otwórz ten link, aby ustawić nowe (ważny {minutos} minut, jednorazowy):<br><a href=\"{url}\">{url}</a><br><br>Jeśli link wygaśnie, użyj opcji „Nie pamiętasz hasła?” na ekranie logowania."},
})
