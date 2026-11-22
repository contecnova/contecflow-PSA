"""Textos que genera el servidor (avisos, PDF, correos), por clave y en cada idioma.

18-11-2026 (auditoria de textos fijos). Avisos de la campana, predicciones,
informes PDF y correos programados se escribian en castellano fijo. Ahora cada
texto tiene una clave y sus datos (`texto(clave, idioma, **params)`):

* Los textos de operador estan en es/en/zh (los idiomas de la interfaz); los
  que llegan al cliente, ademas en los 8 del portal.
* Lo que falte en un idioma cae al castellano (el texto de siempre: respaldo).
* El idioma lo decide quien llama con `formato_regional.idioma_de_salida`
  (el del destinatario del aviso, el del cliente, el de la empresa...).

Por que se escribe en el idioma del destinatario al crear el aviso y no se
guarda solo la clave para que lo traduzca el navegador: `notifications` no
tiene columna para clave y datos (los modelos los lleva otra tarea) y el
aviso tambien sale por WebSocket, Slack y correo. `notify_user(aviso=...)`
pinta cada aviso en el idioma de su destinatario y manda tambien la clave y
los datos en el empujon por WebSocket, para cuando el cliente quiera pintarlo.

Mismo patron que `traduccion/textos_del_sistema.py` (tickets de ALM).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

IDIOMA_DE_RESPALDO = "es"

#: clave -> idioma -> plantilla (`str.format` con los datos).
TEXTOS: dict[str, dict[str, str]] = {
    # ── Catálogo interno de equipos y licencias (19-11-2026, alm_integracion) ──
    "alm.categoria": {"es": "Equipos y licencias", "en": "Equipment and licences", "zh": "设备与许可证"},
    "alm.item.equipo": {"es": "Pedir equipo", "en": "Request equipment", "zh": "申请设备"},
    "alm.item.licencia": {"es": "Pedir licencia", "en": "Request a licence", "zh": "申请许可证"},
    # ── Copiloto de proyectos (ai_copilot_service) ──────────────────────────
    "copilot.retraso": {"es": "La tarea lleva {dias} día(s) de retraso.",
                        "en": "The task is {dias} day(s) overdue.",
                        "zh": "该任务已逾期 {dias} 天。"},
    "copilot.estancada": {"es": "{consumido}% de la duración consumida pero solo {progreso}% completada.",
                          "en": "{consumido}% of the duration used but only {progreso}% complete.",
                          "zh": "已用去 {consumido}% 的工期，但仅完成 {progreso}%。"},
    "copilot.reasignar": {"es": "Reasignar a un recurso disponible", "en": "Reassign to an available resource",
                          "zh": "重新分配给空闲的资源"},
    "copilot.dividir": {"es": "Dividir en sub-tareas para desbloquear el progreso",
                        "en": "Split into subtasks to unblock progress", "zh": "拆分为子任务以推进进度"},
    "copilot.revisar_alcance": {"es": "Revisar alcance — diferir ítems no críticos",
                                "en": "Review scope — defer non-critical items", "zh": "审查范围——推迟非关键事项"},
    "copilot.revisar_bloqueos": {"es": "Revisar bloqueos en los comentarios",
                                 "en": "Check the comments for blockers", "zh": "查看评论中的阻碍"},
    "copilot.sincronizar": {"es": "Agendar sincronización rápida con el responsable",
                            "en": "Schedule a quick sync with the owner", "zh": "与负责人安排一次简短同步"},
    "copilot.paralelo": {"es": "Considerar ejecución paralela si las dependencias lo permiten",
                         "en": "Consider running in parallel if dependencies allow", "zh": "如依赖关系允许，考虑并行执行"},

    # ── Asistente RCA ───────────────────────────────────────────────────────
    "rca.sin_ia": {"es": "No se pudo obtener sugerencia de IA. Analiza el contexto del problema manualmente.",
                   "en": "Could not get an AI suggestion. Analyse the problem context manually.",
                   "zh": "无法获取 AI 建议。请手动分析问题背景。"},

    # ── Avisos de aprobaciones (approval_engine) ────────────────────────────
    "aviso.aprobacion_requerida.titulo": {"es": "Aprobación requerida: {tipo}", "en": "Approval required: {tipo}",
                                          "zh": "需要审批：{tipo}"},
    "aviso.aprobacion_requerida.cuerpo": {"es": "{resumen} — Paso {paso_n}: {paso}",
                                          "en": "{resumen} — Step {paso_n}: {paso}",
                                          "zh": "{resumen} — 第 {paso_n} 步：{paso}"},
    "aviso.aprobacion_aprobada.titulo": {"es": "Solicitud aprobada", "en": "Request approved", "zh": "申请已批准"},
    "aviso.aprobacion_aprobada.cuerpo": {"es": "{resumen} ha sido aprobada", "en": "{resumen} has been approved",
                                         "zh": "{resumen} 已获批准"},
    "aviso.aprobacion_informar.titulo": {"es": "Para tu información: {tipo}", "en": "For your information: {tipo}",
                                         "zh": "供参考：{tipo}"},
    "aviso.aprobacion_informar.cuerpo": {"es": "{resumen} — {paso}", "en": "{resumen} — {paso}",
                                         "zh": "{resumen} — {paso}"},

    # ── Avisos de ALM (altas y bajas) ───────────────────────────────────────
    "aviso.alm_baja.titulo": {"es": "Baja de {persona}: {n} equipo(s) por devolver",
                              "en": "{persona} is leaving: {n} device(s) to return",
                              "zh": "{persona} 离职：{n} 台设备待归还"},
    "aviso.alm_baja.cuerpo": {"es": "Se ha abierto un ticket de devolución por equipo; la baja sigue abierta hasta "
                                    "el acta firmada.",
                              "en": "A return ticket has been opened for each device; the offboarding stays open "
                                    "until the return form is signed.",
                              "zh": "已为每台设备创建归还工单；在归还单签署前，离职流程保持开启。"},
    "aviso.alm_kit.titulo": {"es": "Kit de alta para {persona}", "en": "Onboarding kit for {persona}",
                             "zh": "{persona} 的入职套件"},
    "aviso.alm_kit.cuerpo": {"es": "Revisa y confirma con un clic las licencias y el equipo que le corresponden.",
                             "en": "Review and confirm the licences and equipment they need with one click.",
                             "zh": "一键查看并确认其应得的许可证和设备。"},

    # ── Avisos de politicas ─────────────────────────────────────────────────
    "aviso.politica.titulo": {"es": "Política: {politica}", "en": "Policy: {politica}", "zh": "策略：{politica}"},

    # ── Menciones ───────────────────────────────────────────────────────────
    "aviso.mencion.titulo": {"es": "{autor} te ha mencionado", "en": "{autor} mentioned you",
                             "zh": "{autor} 提到了你"},

    # ── Portal: decision del cliente sobre una factura (lo lee el equipo) ───
    "portal.factura_decidida.asunto": {"es": "Factura {numero} {decision}", "en": "Invoice {numero} {decision}",
                                       "zh": "发票 {numero} {decision}"},
    "portal.factura.aprobada": {"es": "aprobada", "en": "approved", "zh": "已批准"},
    "portal.factura.rechazada": {"es": "rechazada", "en": "rejected", "zh": "已拒绝"},

    # ── Correo al solicitante de un ticket (lo lee el cliente: 8 idiomas) ───
    "ticket.actualizacion.asunto": {"es": "Actualización ticket {numero}", "en": "Ticket {numero} update",
                                    "fr": "Mise à jour du ticket {numero}", "de": "Aktualisierung zu Ticket {numero}",
                                    "it": "Aggiornamento ticket {numero}", "pt": "Atualização do ticket {numero}",
                                    "pl": "Aktualizacja zgłoszenia {numero}", "zh": "工单 {numero} 更新"},

    # ── Predicciones de Oracle (las ve la empresa) ──────────────────────────
    "oracle.retraso.titulo": {"es": "Riesgo de retraso — {proyecto}", "en": "Delay risk — {proyecto}",
                              "zh": "延期风险 — {proyecto}"},
    "oracle.retraso.explicacion": {
        "es": "El proyecto tiene {vencidas} tareas vencidas de {total} totales ({hecho}% completado). "
              "Consumo facturable: {facturable}%, coste interno: {coste}% (método={metodo}, cobertura={cobertura}%).",
        "en": "The project has {vencidas} overdue tasks out of {total} ({hecho}% complete). "
              "Billable consumption: {facturable}%, internal cost: {coste}% (method={metodo}, coverage={cobertura}%).",
        "zh": "该项目共 {total} 项任务，其中 {vencidas} 项已逾期（完成 {hecho}%）。"
              "可计费消耗：{facturable}%，内部成本：{coste}%（方法={metodo}，覆盖率={cobertura}%）。"},
    "oracle.retraso.accion": {"es": "Revisar tareas bloqueadas con el PM. Considerar reasignación de recursos.",
                              "en": "Review blocked tasks with the PM. Consider reallocating resources.",
                              "zh": "与项目经理一起审查受阻任务。考虑重新分配资源。"},
    "oracle.sla.titulo": {"es": "Riesgo de incumplimiento SLA — Ticket {numero}",
                          "en": "SLA breach risk — Ticket {numero}", "zh": "SLA 违约风险 — 工单 {numero}"},
    "oracle.sla.explicacion": {
        "es": "Llevas {horas}h abierto. Límite SLA para prioridad «{nivel}»: {limite}h. Quedan {quedan}h.",
        "en": "Open for {horas}h. SLA limit for priority “{nivel}”: {limite}h. {quedan}h left.",
        "zh": "已开启 {horas} 小时。优先级“{nivel}”的 SLA 上限：{limite} 小时。剩余 {quedan} 小时。"},
    "oracle.sla.accion": {"es": "Asignar o escalar el ticket inmediatamente.",
                          "en": "Assign or escalate the ticket immediately.", "zh": "立即分配或升级该工单。"},
    "oracle.burnout.titulo": {"es": "Riesgo de burnout — {persona}", "en": "Burnout risk — {persona}",
                              "zh": "倦怠风险 — {persona}"},
    "oracle.burnout.explicacion": {
        "es": "Media ponderada (semanas recientes 2×): {media}h/sem. Pico: {pico}h.{tendencia} "
              "Semanas con >42h: {semanas}.",
        "en": "Weighted average (recent weeks 2×): {media}h/week. Peak: {pico}h.{tendencia} "
              "Weeks over 42h: {semanas}.",
        "zh": "加权平均（近几周 2 倍权重）：每周 {media} 小时。峰值：{pico} 小时。{tendencia}"
              "超过 42 小时的周数：{semanas}。"},
    "oracle.burnout.creciente": {"es": " Tendencia: ↑ creciente.", "en": " Trend: ↑ rising.", "zh": "趋势：↑ 上升。"},
    "oracle.burnout.estable": {"es": " Tendencia: → estable.", "en": " Trend: → stable.", "zh": "趋势：→ 稳定。"},
    "oracle.burnout.accion": {"es": "Revisar asignaciones. Redistribuir carga de trabajo.",
                              "en": "Review assignments. Rebalance the workload.", "zh": "审查分配情况。重新分配工作量。"},
    "oracle.presupuesto.titulo": {"es": "Desviación presupuestaria — {proyecto}", "en": "Budget overrun — {proyecto}",
                                  "zh": "预算超支 — {proyecto}"},
    "oracle.presupuesto.explicacion": {
        "es": "Consumo facturable: {facturable}% ({gastado}k{simbolo} de {presupuesto}k{simbolo}). "
              "Coste interno: {coste}% ({coste_k}k{simbolo}, método={metodo}, cobertura datos reales={cobertura}%).",
        "en": "Billable consumption: {facturable}% ({gastado}k{simbolo} of {presupuesto}k{simbolo}). "
              "Internal cost: {coste}% ({coste_k}k{simbolo}, method={metodo}, real data coverage={cobertura}%).",
        "zh": "可计费消耗：{facturable}%（{gastado}k{simbolo} / {presupuesto}k{simbolo}）。"
              "内部成本：{coste}%（{coste_k}k{simbolo}，方法={metodo}，真实数据覆盖率={cobertura}%）。"},
    "oracle.presupuesto.margen": {
        "es": " ⚠ Margen erosionado: coste interno {coste}% > facturación {facturable}% → posibles pérdidas reales.",
        "en": " ⚠ Eroded margin: internal cost {coste}% > billing {facturable}% → possible real losses.",
        "zh": " ⚠ 利润受侵蚀：内部成本 {coste}% > 计费 {facturable}% → 可能出现实际亏损。"},
    "oracle.presupuesto.accion": {"es": "Revisar alcance con el cliente. Preparar change order si hay trabajo extra.",
                                  "en": "Review scope with the client. Prepare a change order if there is extra work.",
                                  "zh": "与客户审查范围。如有额外工作，准备变更单。"},
    "oracle.presupuesto.accion_margen": {"es": " Auditar costes internos y replantear pricing del proyecto.",
                                         "en": " Audit internal costs and rethink the project pricing.",
                                         "zh": "审计内部成本并重新考虑项目定价。"},

    # ── Informes PDF (report_pdf, report_pdf_service, pdf_export_service) ───
    "pdf.generado_el": {"es": "Generado el {cuando}", "en": "Generated on {cuando}", "zh": "生成于 {cuando}"},
    "pdf.generado": {"es": "Generado: {cuando}", "en": "Generated: {cuando}", "zh": "生成时间：{cuando}"},
    "pdf.filtros": {"es": "Filtros", "en": "Filters", "zh": "筛选条件"},
    "pdf.desde": {"es": "Desde", "en": "From", "zh": "从"},
    "pdf.hasta": {"es": "Hasta", "en": "To", "zh": "至"},
    "pdf.proyecto": {"es": "Proyecto", "en": "Project", "zh": "项目"},
    "pdf.resumen": {"es": "Resumen", "en": "Summary", "zh": "摘要"},
    "pdf.datos": {"es": "Datos del informe", "en": "Report data", "zh": "报告数据"},
    "pdf.primeras_filas": {"es": "* Se muestran los primeros {n} de {total} registros totales.",
                           "en": "* Showing the first {n} of {total} records.",
                           "zh": "* 显示共 {total} 条记录中的前 {n} 条。"},
    "pdf.pie_informe": {"es": "{marca} · Informe generado automáticamente · {anio}",
                        "en": "{marca} · Automatically generated report · {anio}",
                        "zh": "{marca} · 自动生成的报告 · {anio}"},
    "pdf.pie_automatico": {"es": "Generado automáticamente por {marca} · {cuando}",
                           "en": "Automatically generated by {marca} · {cuando}",
                           "zh": "由 {marca} 自动生成 · {cuando}"},
    "pdf.informe_bi": {"es": "Informe BI", "en": "BI report", "zh": "BI 报告"},
    "pdf.periodo": {"es": "Periodo", "en": "Period", "zh": "期间"},
    "pdf.filas": {"es": "Filas", "en": "Rows", "zh": "行数"},
    "pdf.total": {"es": "Total", "en": "Total", "zh": "合计"},
    "pdf.exportacion": {"es": "Exportación: {tipo}", "en": "Export: {tipo}", "zh": "导出：{tipo}"},

    "informe.tipo.executive_summary": {"es": "Resumen Ejecutivo", "en": "Executive summary", "zh": "执行摘要"},
    "informe.tipo.utilization": {"es": "Informe de Utilización", "en": "Utilisation report", "zh": "利用率报告"},
    "informe.tipo.pipeline": {"es": "Informe de Pipeline Comercial", "en": "Sales pipeline report",
                              "zh": "销售管道报告"},
    "informe.tipo.portfolio": {"es": "Informe de Portfolio de Proyectos", "en": "Project portfolio report",
                               "zh": "项目组合报告"},
    "informe.tipo.custom": {"es": "Informe Personalizado", "en": "Custom report", "zh": "自定义报告"},
    "informe.tipo.otro": {"es": "Informe", "en": "Report", "zh": "报告"},
    # Índice de riesgo y gestión de vulnerabilidades (22-11-2026, cmdb_software/riesgo)
    "informe.tipo.cyber_risk": {"es": "Índice de riesgo", "en": "Cyber risk index", "zh": "网络风险指数"},
    "informe.tipo.vuln_management": {"es": "Gestión de vulnerabilidades", "en": "Vulnerability management",
                                     "zh": "漏洞管理"},
    "riesgo.ambito": {"es": "Ámbito: {ambito}", "en": "Scope: {ambito}", "zh": "范围：{ambito}"},
    "riesgo.indicador": {"es": "Indicador", "en": "Indicator", "zh": "指标"},
    "riesgo.valor": {"es": "Valor", "en": "Value", "zh": "数值"},
    "riesgo.indice": {"es": "Índice de riesgo", "en": "Risk index", "zh": "风险指数"},
    "riesgo.aceptado": {"es": "Riesgo aceptado", "en": "Accepted risk", "zh": "已接受风险"},
    "riesgo.objetivo": {"es": "Objetivo", "en": "Target", "zh": "目标"},
    "riesgo.hallazgos_vivos": {"es": "Hallazgos abiertos", "en": "Open findings", "zh": "未关闭的发现"},
    "riesgo.explotados": {"es": "Explotados (KEV o con intentos)", "en": "Exploited (KEV or attempts)",
                          "zh": "已被利用（KEV 或有尝试）"},
    "riesgo.expuestos": {"es": "Activos expuestos a Internet", "en": "Internet-exposed assets", "zh": "暴露于互联网的资产"},
    "riesgo.resumen": {"es": "Resumen", "en": "Summary", "zh": "摘要"},
    "riesgo.factor": {"es": "Factor", "en": "Factor", "zh": "因素"},
    "riesgo.factores": {"es": "Desglose por factor", "en": "Breakdown by factor", "zh": "按因素细分"},
    "riesgo.puntuacion": {"es": "Puntuación", "en": "Score", "zh": "得分"},
    "riesgo.peso": {"es": "Peso", "en": "Weight", "zh": "权重"},
    "riesgo.contribucion": {"es": "Contribución", "en": "Contribution", "zh": "贡献"},
    "riesgo.factor_vulnerabilities": {"es": "Vulnerabilidades", "en": "Vulnerabilities", "zh": "漏洞"},
    "riesgo.factor_exploitation": {"es": "Explotación", "en": "Exploitation", "zh": "利用"},
    "riesgo.factor_exposure": {"es": "Exposición a Internet", "en": "Internet exposure", "zh": "互联网暴露"},
    "riesgo.factor_configuration": {"es": "Configuración", "en": "Configuration", "zh": "配置"},
    "riesgo.factor_eol": {"es": "Software sin soporte", "en": "Unsupported software", "zh": "不受支持的软件"},
    "riesgo.factor_signals": {"es": "Señales importadas", "en": "Imported signals", "zh": "导入的信号"},
    "riesgo.dia": {"es": "Día", "en": "Day", "zh": "日期"},
    "riesgo.tendencia": {"es": "Tendencia (90 días)", "en": "Trend (90 days)", "zh": "趋势（90 天）"},
    "riesgo.aviso": {"es": "Aviso", "en": "Advisory", "zh": "公告"},
    "riesgo.software": {"es": "Software", "en": "Software", "zh": "软件"},
    "riesgo.impacto": {"es": "Impacto", "en": "Impact", "zh": "影响"},
    "riesgo.tras": {"es": "Índice tras resolverlo", "en": "Index after fixing", "zh": "修复后的指数"},
    "riesgo.plan": {"es": "Plan de reducción (de {desde} a {hasta})", "en": "Reduction plan (from {desde} to {hasta})",
                    "zh": "降低计划（从 {desde} 到 {hasta}）"},
    "riesgo.metricas": {"es": "Métricas de vulnerabilidades", "en": "Vulnerability metrics", "zh": "漏洞指标"},
    "riesgo.pct_activos": {"es": "% de activos con vulnerabilidades", "en": "% of assets with vulnerabilities",
                           "zh": "存在漏洞的资产比例"},
    "riesgo.pct_internos": {"es": "% de activos internos con vulnerabilidades",
                            "en": "% of internal assets with vulnerabilities", "zh": "存在漏洞的内部资产比例"},
    "riesgo.pct_maquinas": {"es": "% de máquinas con vulnerabilidades", "en": "% of machines with vulnerabilities",
                            "zh": "存在漏洞的机器比例"},
    "riesgo.densidad_activo": {"es": "Vulnerabilidades por activo", "en": "Vulnerabilities per asset",
                               "zh": "每个资产的漏洞数"},
    "riesgo.densidad_maquina": {"es": "Vulnerabilidades por máquina", "en": "Vulnerabilities per machine",
                                "zh": "每台机器的漏洞数"},
    "riesgo.mttp": {"es": "Días medios hasta parchear (MTTP)", "en": "Mean time to patch (days)",
                    "zh": "平均修补时间（天）"},
    "riesgo.antiguedad": {"es": "Antigüedad media de lo no parcheado (días)", "en": "Average age of unpatched (days)",
                          "zh": "未修补漏洞的平均存在时间（天）"},
    "riesgo.so_sin_soporte": {"es": "Equipos con sistema operativo sin soporte", "en": "Devices with unsupported OS",
                              "zh": "操作系统不受支持的设备"},
    "riesgo.impacto_alto": {"es": "Impacto alto", "en": "High impact", "zh": "高影响"},
    "riesgo.impacto_medio": {"es": "Impacto medio", "en": "Medium impact", "zh": "中影响"},
    "riesgo.impacto_bajo": {"es": "Impacto bajo", "en": "Low impact", "zh": "低影响"},
    "riesgo.estado_nuevo": {"es": "Nuevos", "en": "New", "zh": "新增"},
    "riesgo.estado_en_curso": {"es": "En curso", "en": "In progress", "zh": "处理中"},
    "riesgo.estado_resuelto": {"es": "Resueltos (periodo)", "en": "Resolved (period)", "zh": "已解决（期间）"},
    "riesgo.estado_aceptado": {"es": "Aceptados", "en": "Accepted", "zh": "已接受"},
    "riesgo.severidad": {"es": "Severidad", "en": "Severity", "zh": "严重程度"},
    "riesgo.maquina": {"es": "Máquina", "en": "Machine", "zh": "机器"},
    "riesgo.riesgo": {"es": "Riesgo", "en": "Risk", "zh": "风险"},
    "riesgo.top_hallazgos": {"es": "Hallazgos de más riesgo", "en": "Highest-risk findings", "zh": "风险最高的发现"},
    "aviso.swr_kev.titulo": {"es": "Vulnerabilidad explotada que nos afecta: {cve}",
                             "en": "Exploited vulnerability affecting us: {cve}", "zh": "影响我们的已被利用漏洞：{cve}"},
    "aviso.swr_kev.cuerpo": {"es": "{producto} en {maquinas} (riesgo {riesgo})", "en": "{producto} on {maquinas} (risk {riesgo})",
                             "zh": "{maquinas} 上的 {producto}（风险 {riesgo}）"},
    "aviso.swr_indice.titulo": {"es": "Índice de riesgo de {ambito}: {indice}", "en": "Risk index of {ambito}: {indice}",
                                "zh": "{ambito} 的风险指数：{indice}"},
    "aviso.swr_indice.cuerpo": {"es": "Supera el umbral de {umbral}", "en": "Above the threshold of {umbral}",
                                "zh": "超过阈值 {umbral}"},
    "aviso.swr_sla.titulo": {"es": "{n} hallazgo(s) con el plazo de remediación a punto de vencer",
                             "en": "{n} finding(s) with remediation due soon", "zh": "{n} 个发现的修复期限即将到期"},
    "aviso.swr_sla.cuerpo": {"es": "Vencen en los próximos {dias} días", "en": "Due within {dias} days",
                             "zh": "将在 {dias} 天内到期"},
    "informe.kpi": {"es": "KPI", "en": "KPI", "zh": "KPI"},
    "informe.valor": {"es": "Valor", "en": "Value", "zh": "数值"},
    "informe.kpis_del_periodo": {"es": "KPIs del período", "en": "KPIs for the period", "zh": "本期 KPI"},
    "informe.kpi.active_projects": {"es": "Proyectos activos", "en": "Active projects", "zh": "进行中的项目"},
    "informe.kpi.hours_mtd": {"es": "Horas imputadas (mes)", "en": "Hours logged (month)", "zh": "已登记工时（本月）"},
    "informe.kpi.cost_mtd": {"es": "Coste mes", "en": "Cost this month", "zh": "本月成本"},
    "informe.kpi.billability_pct": {"es": "Facturabilidad", "en": "Billability", "zh": "可计费率"},
    "informe.kpi.pipeline_weighted": {"es": "Pipeline ponderado", "en": "Weighted pipeline", "zh": "加权管道"},
    "informe.kpi.open_opps": {"es": "Oportunidades abiertas", "en": "Open opportunities", "zh": "未结商机"},
    "informe.kpi.won_revenue": {"es": "Revenue ganado (YTD)", "en": "Revenue won (YTD)", "zh": "已赢得收入（年初至今）"},
    "informe.kpi.avg_margin_pct": {"es": "Margen medio (%)", "en": "Average margin (%)", "zh": "平均利润率（%）"},
    "informe.kpi.high_risk_projects": {"es": "Proyectos riesgo alto", "en": "High-risk projects", "zh": "高风险项目"},
    "informe.sin_utilizacion": {"es": "Sin datos de utilización en OLAP.", "en": "No utilisation data in OLAP.",
                                "zh": "OLAP 中没有利用率数据。"},
    "informe.utilizacion": {"es": "Utilización por usuario", "en": "Utilisation by user", "zh": "按用户的利用率"},
    "informe.col.usuario": {"es": "Usuario", "en": "User", "zh": "用户"},
    "informe.col.departamento": {"es": "Departamento", "en": "Department", "zh": "部门"},
    "informe.col.horas": {"es": "Horas", "en": "Hours", "zh": "工时"},
    "informe.col.capacidad": {"es": "Capacidad", "en": "Capacity", "zh": "产能"},
    "informe.col.utilizacion": {"es": "Utilización %", "en": "Utilisation %", "zh": "利用率 %"},
    "informe.sin_pipeline": {"es": "Sin datos de pipeline en OLAP.", "en": "No pipeline data in OLAP.",
                             "zh": "OLAP 中没有管道数据。"},
    "informe.pipeline": {"es": "Funnel de pipeline", "en": "Pipeline funnel", "zh": "管道漏斗"},
    "informe.col.etapa": {"es": "Etapa", "en": "Stage", "zh": "阶段"},
    "informe.col.oportunidades": {"es": "Oportunidades", "en": "Opportunities", "zh": "商机"},
    "informe.col.revenue_esperado": {"es": "Revenue esperado", "en": "Expected revenue", "zh": "预期收入"},
    "informe.col.revenue_ponderado": {"es": "Revenue ponderado", "en": "Weighted revenue", "zh": "加权收入"},
    "informe.col.prob_media": {"es": "Prob. media", "en": "Avg. prob.", "zh": "平均概率"},
    "informe.col.dias_medios": {"es": "Días medios", "en": "Avg. days", "zh": "平均天数"},
    "informe.sin_portfolio": {"es": "Sin datos de portfolio en OLAP.", "en": "No portfolio data in OLAP.",
                              "zh": "OLAP 中没有项目组合数据。"},
    "informe.portfolio": {"es": "Salud del portfolio", "en": "Portfolio health", "zh": "项目组合健康度"},
    "informe.col.proyecto": {"es": "Proyecto", "en": "Project", "zh": "项目"},
    "informe.col.estado": {"es": "Estado", "en": "Status", "zh": "状态"},
    "informe.col.margen": {"es": "Margen %", "en": "Margin %", "zh": "利润率 %"},
    "informe.col.completado": {"es": "Completado %", "en": "Complete %", "zh": "完成 %"},
    "informe.col.riesgo": {"es": "Riesgo", "en": "Risk", "zh": "风险"},
    "informe.resumen_ia": {"es": "Resumen ejecutivo IA", "en": "AI executive summary", "zh": "AI 执行摘要"},

    # ── Informes programados: correo y Slack (scheduled_reports) ────────────
    "programado.asunto": {"es": "[{marca}] {nombre} — {fecha}", "en": "[{marca}] {nombre} — {fecha}",
                          "zh": "[{marca}] {nombre} — {fecha}"},
    "programado.cabecera": {"es": "{marca} — Informe programado", "en": "{marca} — Scheduled report",
                            "zh": "{marca} — 定时报告"},
    "programado.tipo": {"es": "Tipo", "en": "Type", "zh": "类型"},
    "programado.generado": {"es": "Generado el {cuando}. Se adjunta el informe en PDF.",
                            "en": "Generated on {cuando}. The report is attached as a PDF.",
                            "zh": "生成于 {cuando}。报告以 PDF 附件形式附上。"},
    "programado.frecuencia": {"es": "Frecuencia", "en": "Frequency", "zh": "频率"},
    "programado.proximo": {"es": "Próximo envío", "en": "Next delivery", "zh": "下次发送"},
    "programado.pie": {"es": "Informe generado automáticamente por {marca}. Para modificar la configuración accede "
                             "a Analytics &amp; BI → Reports.",
                       "en": "Report generated automatically by {marca}. To change its settings go to "
                             "Analytics &amp; BI → Reports.",
                       "zh": "报告由 {marca} 自动生成。如需修改设置，请前往 Analytics &amp; BI → Reports。"},
    "programado.frecuencia.daily": {"es": "diaria", "en": "daily", "zh": "每日"},
    "programado.frecuencia.weekly": {"es": "semanal", "en": "weekly", "zh": "每周"},
    "programado.frecuencia.monthly": {"es": "mensual", "en": "monthly", "zh": "每月"},
    "programado.slack.generado": {"es": "Generado: {cuando}", "en": "Generated: {cuando}", "zh": "生成时间：{cuando}"},
    "programado.slack.margen": {"es": "Margen medio", "en": "Average margin", "zh": "平均利润率"},

    # ── Envios programados del BI (bi_report_delivery_service) ──────────────
    "bi.ultimos_dias": {"es": "últimos {n} días", "en": "last {n} days", "zh": "最近 {n} 天"},
    "bi.entrega.resumen": {
        "es": "*{titulo}* — {n} registros generados el {fecha}.\nFormato: `{formato}` | Filas: `{n}`",
        "en": "*{titulo}* — {n} records generated on {fecha}.\nFormat: `{formato}` | Rows: `{n}`",
        "zh": "*{titulo}* — 于 {fecha} 生成 {n} 条记录。\n格式：`{formato}` | 行数：`{n}`"},

    # ── Exportacion PDF generica (pdf_export_service) ───────────────────────
    "pdfexp.resumen_proyecto": {"es": "Resumen del proyecto: {nombre}", "en": "Project summary: {nombre}",
                                "zh": "项目摘要：{nombre}"},
    "pdfexp.campo": {"es": "Campo", "en": "Field", "zh": "字段"},
    "pdfexp.codigo": {"es": "Código", "en": "Code", "zh": "编号"},
    "pdfexp.cliente": {"es": "Cliente", "en": "Client", "zh": "客户"},
    "pdfexp.presupuesto": {"es": "Presupuesto", "en": "Budget", "zh": "预算"},
    "pdfexp.inicio": {"es": "Inicio", "en": "Start", "zh": "开始"},
    "pdfexp.fin_previsto": {"es": "Fin previsto", "en": "Planned end", "zh": "计划结束"},
    "pdfexp.tareas": {"es": "Tareas", "en": "Tasks", "zh": "任务"},
    "pdfexp.tareas_hechas": {"es": "{hechas}/{total} completadas", "en": "{hechas}/{total} completed",
                             "zh": "已完成 {hechas}/{total}"},
    "pdfexp.generada_por": {"es": "Exportación generada por {marca}.", "en": "Export generated by {marca}.",
                            "zh": "导出由 {marca} 生成。"},
    "pdfexp.pie": {"es": "Generado por {marca} · {cuando} · Documento confidencial",
                   "en": "Generated by {marca} · {cuando} · Confidential document",
                   "zh": "由 {marca} 生成 · {cuando} · 机密文件"},

    # ── Evaluacion 360 (campaign_pdf) ───────────────────────────────────────
    "camp.titulo": {"es": "Evaluación 360° — {persona}", "en": "360° review — {persona}", "zh": "360° 评估 — {persona}"},
    "camp.grupo": {"es": "Grupo", "en": "Group", "zh": "组别"},
    "camp.respuestas": {"es": "Respuestas", "en": "Responses", "zh": "回复"},
    "camp.anonimizado": {"es": "Anonimizado", "en": "Anonymised", "zh": "已匿名"},
    "camp.si": {"es": "Sí", "en": "Yes", "zh": "是"},
    "camp.no": {"es": "No", "en": "No", "zh": "否"},
    "camp.grupo.self": {"es": "Self", "en": "Self", "zh": "自评"},
    "camp.grupo.manager": {"es": "Manager", "en": "Manager", "zh": "经理"},
    "camp.grupo.peer": {"es": "Pares", "en": "Peers", "zh": "同事"},
    "camp.grupo.upward": {"es": "Upward", "en": "Upward", "zh": "下属"},
    "camp.pregunta": {"es": "Pregunta", "en": "Question", "zh": "问题"},
    "camp.lectura": {"es": "Insight", "en": "Insight", "zh": "解读"},
    "camp.punto_ciego": {"es": "Punto ciego", "en": "Blind spot", "zh": "盲点"},
    "camp.fortaleza_oculta": {"es": "Fortaleza no percibida", "en": "Hidden strength", "zh": "未被察觉的优势"},
    "camp.alineado": {"es": "Alineado", "en": "Aligned", "zh": "一致"},
    "camp.comentarios": {"es": "Comentarios cualitativos", "en": "Qualitative comments", "zh": "定性评论"},
    "camp.oculto": {"es": "{grupo}: oculto por anonimización (n={n} &lt; {umbral})",
                    "en": "{grupo}: hidden for anonymity (n={n} &lt; {umbral})",
                    "zh": "{grupo}：因匿名而隐藏（n={n} &lt; {umbral}）"},
    "camp.umbral": {"es": "Umbral de anonimización", "en": "Anonymity threshold", "zh": "匿名阈值"},
    "camp.resumen_grupos": {"es": "Resumen por grupo de evaluadores", "en": "Summary by reviewer group",
                            "zh": "按评估者组别汇总"},
    "camp.comparativa": {"es": "Comparativa por pregunta", "en": "Comparison by question", "zh": "按问题比较"},
    "camp.confidencial": {"es": "Documento confidencial — solo para el subject, su manager y RR.HH.",
                          "en": "Confidential document — only for the subject, their manager and HR.",
                          "zh": "机密文件——仅供被评估人、其经理和人力资源部门查阅。"},

    # ── Firma electronica (signature_pdf) ───────────────────────────────────
    "firma.fecha": {"es": "Fecha", "en": "Date", "zh": "日期"},

    # ── RACI (raci_service) ─────────────────────────────────────────────────
    "raci.generado": {"es": "Generado: {cuando}", "en": "Generated: {cuando}", "zh": "生成时间：{cuando}"},
    "uat.titulo": {"es": "Plan de Pruebas UAT — {proyecto}", "en": "UAT test plan — {proyecto}",
                   "zh": "UAT 测试计划 — {proyecto}"},
    "uat.totales": {"es": "Total: {total} casos | Pendientes: {pendientes} | Pasados: {pasados} | "
                          "Fallidos: {fallidos}",
                    "en": "Total: {total} cases | Pending: {pendientes} | Passed: {pasados} | Failed: {fallidos}",
                    "zh": "总计：{total} 个用例 | 待执行：{pendientes} | 通过：{pasados} | 失败：{fallidos}"},
    "uat.prioridad": {"es": "Prioridad", "en": "Priority", "zh": "优先级"},
    "uat.tarea": {"es": "Tarea vinculada", "en": "Linked task", "zh": "关联任务"},
    "uat.pasos": {"es": "Pasos a ejecutar", "en": "Steps", "zh": "执行步骤"},
    "uat.esperado": {"es": "Resultado esperado", "en": "Expected result", "zh": "预期结果"},
    "uat.obtenido": {"es": "Resultado obtenido", "en": "Actual result", "zh": "实际结果"},
    "uat.notas": {"es": "Notas", "en": "Notes", "zh": "备注"},
}

# 19-11-2026: planes de cambio, playbooks de serie y bloqueos/cupos del sistema
# (bloque propio en otro fichero; mismo formato, mismas reglas).
from app.services.textos_de_salida_itsm import TEXTOS_ITSM as _TEXTOS_ITSM  # noqa: E402

TEXTOS.update(_TEXTOS_ITSM)


def texto(clave: str, idioma: Optional[str] = None, **params) -> str:
    """El texto `clave` en `idioma` (castellano si no lo hay) con sus datos.

    Si falta un dato en la plantilla, sale la plantilla sin sustituir (y se
    apunta en el log): mejor un texto con `{dato}` que un aviso que no sale.
    Una clave desconocida devuelve la propia clave.
    """
    from app.services.traduccion.idiomas import normalizar
    variantes = TEXTOS.get(clave)
    if not variantes:
        logger.warning("textos_de_salida: clave desconocida %r", clave)
        return clave
    plantilla = variantes.get(normalizar(idioma) or "") or variantes.get(IDIOMA_DE_RESPALDO) or clave
    try:
        return plantilla.format(**params) if params else plantilla
    except (KeyError, IndexError):
        logger.warning("textos_de_salida: faltan datos para %r: %s", clave, sorted(params))
        return plantilla


def nombre_de_marca(db=None, org_id: Optional[str] = None) -> str:
    """El nombre con el que firma la empresa (su `OrgBranding.app_name`) o el del producto.

    Sin `db` (envios a Slack/Jira desde codigo sin sesion) abre una propia.
    Nunca falla: si no se puede leer la marca, el nombre del producto.
    """
    from app.core.constantes import NOMBRE_DEL_PRODUCTO
    if not org_id:
        return NOMBRE_DEL_PRODUCTO
    from app.services._pdf_marca import marca_de_organizacion
    propia = None
    try:
        if db is None:
            from app.db.session import SessionLocal
            propia = db = SessionLocal()
        return marca_de_organizacion(db, org_id, nombre_por_defecto=NOMBRE_DEL_PRODUCTO).nombre \
            or NOMBRE_DEL_PRODUCTO
    except Exception:
        logger.debug("nombre_de_marca: marca no legible", exc_info=True)
        return NOMBRE_DEL_PRODUCTO
    finally:
        if propia is not None:
            propia.close()
