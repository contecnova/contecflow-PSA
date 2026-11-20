"""Textos de salida del service desk y del gobierno de la IA (19-11-2026).

Bloque propio de `textos_de_salida.TEXTOS` (se fusiona al importarlo), para no
pisar a quien edita el diccionario general a la vez. Lo que hay aqui lo
escribia el sistema en castellano (o ingles) fijo:

* `cambio.*`: planes de un cambio (vuelta atras, pruebas, comunicaciones),
  responsables, canales, ventana y resumen del informe de impacto
  (`service_desk/change_impact_service`).
* `autonomo.*`: nombres de los playbooks de serie del agente autonomo, sus
  avisos internos y el motivo de la evaluacion (`autonomous_agent_service`).
* `politica.*`, `ia.*`, `gobernanza.*`: bloqueos y cupos que escribe el
  sistema (herramientas del asistente, limite diario de un modulo de IA,
  politicas de gobernanza de entrada/salida).
* `ausencias.cupo_lleno`: el rechazo por cupo cuando la empresa no redacto
  su propio mensaje.

Los textos que redacta la empresa (nombre de la politica, mensaje de bloqueo
de un cupo, playbooks propios) no estan aqui: salen como los escribio.

Este modulo no importa nada de la app (lo importa `textos_de_salida`).
"""
from __future__ import annotations

_DIAS = {
    "es": ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "zh": ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"),
}

TEXTOS_ITSM: dict[str, dict[str, str]] = {
    # ── Cambios: piezas comunes ────────────────────────────────────────────
    **{f"cambio.dia.{i}": {idioma: dias[i] for idioma, dias in _DIAS.items()} for i in range(7)},
    "cambio.ventana": {"es": "{dia} {desde}–{hasta} UTC", "en": "{dia} {desde}–{hasta} UTC",
                       "zh": "{dia} {desde}–{hasta}（UTC）"},
    "cambio.ventana_pendiente": {"es": "pendiente de confirmar", "en": "to be confirmed", "zh": "待确认"},
    "cambio.sin_cis": {"es": "N/D", "en": "N/A", "zh": "无"},
    "cambio.riesgo.low": {"es": "bajo", "en": "low", "zh": "低"},
    "cambio.riesgo.medium": {"es": "medio", "en": "medium", "zh": "中"},
    "cambio.riesgo.high": {"es": "alto", "en": "high", "zh": "高"},
    "cambio.riesgo.critical": {"es": "crítico", "en": "critical", "zh": "严重"},
    "cambio.resumen_impacto": {
        "es": "El cambio «{titulo}» afecta a {n} CI (directos: {directos}). Riesgo: {score}/100 ({riesgo}). "
              "Ventana de mantenimiento sugerida: {ventana}.",
        "en": "Change '{titulo}' affects {n} CIs (direct: {directos}). Risk score: {score}/100 ({riesgo}). "
              "Suggested maintenance window: {ventana}.",
        "zh": "变更“{titulo}”影响 {n} 个配置项（直接：{directos}）。风险评分：{score}/100（{riesgo}）。"
              "建议的维护窗口：{ventana}。"},
    "cambio.plan_pruebas.cabecera": {
        "es": "[Generado automáticamente — riesgo {riesgo} — {n} pasos]",
        "en": "[Auto-generated — {riesgo} risk — {n} steps]",
        "zh": "[自动生成 — 风险：{riesgo} — 共 {n} 步]"},

    # ── Cambios: responsables ──────────────────────────────────────────────
    "cambio.rol.operaciones": {"es": "Ingeniero de operaciones", "en": "Operations engineer", "zh": "运维工程师"},
    "cambio.rol.cmdb": {"es": "Administrador de la CMDB", "en": "CMDB administrator", "zh": "CMDB 管理员"},
    "cambio.rol.tecnico": {"es": "Equipo técnico", "en": "Technical team", "zh": "技术团队"},
    "cambio.rol.qa_dev": {"es": "QA / Desarrollo", "en": "QA / Development", "zh": "QA / 开发"},
    "cambio.rol.qa_devops": {"es": "QA / DevOps", "en": "QA / DevOps", "zh": "QA / DevOps"},
    "cambio.rol.noc": {"es": "NOC / Operaciones", "en": "NOC / Operations", "zh": "NOC / 运维"},
    "cambio.rol.gestor": {"es": "Gestor del cambio", "en": "Change manager", "zh": "变更经理"},
    "cambio.rol.comunicacion": {"es": "Service desk / Comunicación", "en": "Service desk / Communications",
                                "zh": "服务台 / 沟通团队"},

    # ── Cambios: plan de vuelta atrás ──────────────────────────────────────
    "cambio.vuelta.1": {"es": "Detener el despliegue si está en curso",
                        "en": "Stop the deployment if it is in progress",
                        "zh": "如部署仍在进行，立即停止"},
    "cambio.vuelta.2": {"es": "Comprobar en la CMDB el estado de todos los CI afectados",
                        "en": "Check the status of every affected CI in the CMDB",
                        "zh": "在 CMDB 中核查所有受影响配置项的状态"},
    "cambio.vuelta.3": {"es": "Restaurar la versión anterior de los componentes de «{titulo}»",
                        "en": "Restore the previous version of the components of '{titulo}'",
                        "zh": "将“{titulo}”的组件恢复到上一版本"},
    "cambio.vuelta.4": {"es": "Ejecutar pruebas de humo en los sistemas restaurados",
                        "en": "Run smoke tests on the restored systems",
                        "zh": "对已恢复的系统执行冒烟测试"},
    "cambio.vuelta.5": {"es": "Confirmar que los CI afectados vuelven a estar operativos",
                        "en": "Confirm the affected CIs are operational again",
                        "zh": "确认受影响的配置项已恢复正常运行"},
    "cambio.vuelta.6": {"es": "Informar a los interesados de la vuelta atrás y del estado",
                        "en": "Inform stakeholders about the rollback and the current status",
                        "zh": "向相关方通报回滚情况及当前状态"},
    "cambio.vuelta.7": {"es": "Registrar el ticket posterior al incidente y programar la revisión (PIR)",
                        "en": "Log the post-incident ticket and schedule the PIR",
                        "zh": "登记事后工单并安排实施后评审（PIR）"},

    # ── Cambios: plan de pruebas (descripción / resultado esperado) ────────
    "cambio.prueba.pre_change.sanity.desc": {
        "es": "Comprobar en la CMDB el estado actual de los CI: {cis}",
        "en": "Check the current status of the CIs in the CMDB: {cis}",
        "zh": "在 CMDB 中核查配置项的当前状态：{cis}"},
    "cambio.prueba.pre_change.sanity.esperado": {
        "es": "Todos los CI en estado «active» y con su configuración de referencia registrada",
        "en": "All CIs in 'active' status with their baseline configuration recorded",
        "zh": "所有配置项均为“active”状态，且已记录基线配置"},
    "cambio.prueba.pre_change.backup.desc": {
        "es": "Confirmar las instantáneas o copias de configuración de los CI críticos",
        "en": "Confirm configuration snapshots/backups of the critical CIs",
        "zh": "确认关键配置项的配置快照或备份"},
    "cambio.prueba.pre_change.backup.esperado": {
        "es": "Copias completadas y verificadas (punto de restauración disponible)",
        "en": "Backups completed and verified (restore point available)",
        "zh": "备份已完成并验证（可用还原点）"},
    "cambio.prueba.pre_change.readiness.desc": {
        "es": "Confirmar que el plan de vuelta atrás y el equipo de soporte están disponibles",
        "en": "Confirm the rollback plan and the support team are available",
        "zh": "确认回滚计划和支持团队已就绪"},
    "cambio.prueba.pre_change.readiness.esperado": {
        "es": "Equipo de vuelta atrás en espera y procedimiento revisado y firmado",
        "en": "Rollback team on standby; procedure reviewed and signed off",
        "zh": "回滚团队待命，流程已审阅并签字确认"},
    "cambio.prueba.pre_change.noc_alert.desc": {
        "es": "Avisar al NOC y poner los CI en observación anticipada",
        "en": "Notify the NOC and put the CIs under early observation",
        "zh": "通知 NOC 并对配置项进行提前观察"},
    "cambio.prueba.pre_change.noc_alert.esperado": {
        "es": "El NOC confirma la monitorización activa de alertas de los CI afectados",
        "en": "The NOC confirms active alert monitoring on the affected CIs",
        "zh": "NOC 确认已对受影响配置项开启告警监控"},
    "cambio.prueba.pre_change.maintenance_mode.desc": {
        "es": "Activar el modo mantenimiento en los sistemas afectados ({cis})",
        "en": "Enable maintenance mode on the affected systems ({cis})",
        "zh": "在受影响的系统上启用维护模式（{cis}）"},
    "cambio.prueba.pre_change.maintenance_mode.esperado": {
        "es": "Sistemas en mantenimiento, sin tickets de incidente generados automáticamente",
        "en": "Systems in maintenance, with no incident tickets raised automatically",
        "zh": "系统处于维护状态，未自动生成事件工单"},
    "cambio.prueba.execution.milestone.desc": {
        "es": "Confirmar el inicio del cambio y anotar la hora real de arranque",
        "en": "Confirm the start of the change and record the actual start time",
        "zh": "确认变更开始并记录实际开始时间"},
    "cambio.prueba.execution.milestone.esperado": {
        "es": "Hora de inicio anotada en la petición de cambio (actual_start actualizado)",
        "en": "Start time recorded on the change request (actual_start updated)",
        "zh": "开始时间已记录在变更请求中（actual_start 已更新）"},
    "cambio.prueba.execution.monitoring.desc": {
        "es": "Vigilar las métricas de salud de los CI durante el cambio: {cis}",
        "en": "Monitor the health metrics of the CIs during the change: {cis}",
        "zh": "变更期间监控配置项的健康指标：{cis}"},
    "cambio.prueba.execution.monitoring.esperado": {
        "es": "CPU, memoria y latencia dentro de los umbrales normales; sin alertas críticas",
        "en": "CPU, memory and latency within normal thresholds; no critical alerts",
        "zh": "CPU、内存和延迟均在正常阈值内；无严重告警"},
    "cambio.prueba.execution.checkpoint.desc": {
        "es": "Comprobar el hito intermedio: los primeros CI afectados han completado el cambio",
        "en": "Check the intermediate milestone: the first affected CIs have completed the change",
        "zh": "检查中间里程碑：首批受影响配置项已完成变更"},
    "cambio.prueba.execution.checkpoint.esperado": {
        "es": "Al menos {mitad_de_cis} CI en estado posterior al cambio y sin errores",
        "en": "At least {mitad_de_cis} CIs in post-change status with no errors",
        "zh": "至少 {mitad_de_cis} 个配置项处于变更后状态且无错误"},
    "cambio.prueba.execution.go_nogo.desc": {
        "es": "Punto de decisión «seguir / no seguir» a mitad del cambio",
        "en": "Go/no-go decision point halfway through the change",
        "zh": "变更进行到一半时的继续/中止决策点"},
    "cambio.prueba.execution.go_nogo.esperado": {
        "es": "El equipo técnico confirma que se continúa; si hay anomalías, se inicia la vuelta atrás",
        "en": "The technical team confirms to continue; if there are anomalies, start the rollback",
        "zh": "技术团队确认继续；如有异常则启动回滚"},
    "cambio.prueba.post_change.smoke.desc": {
        "es": "Pruebas de humo de conectividad y disponibilidad de los CI: {cis}",
        "en": "Connectivity and availability smoke tests on the CIs: {cis}",
        "zh": "对配置项进行连通性和可用性冒烟测试：{cis}"},
    "cambio.prueba.post_change.smoke.esperado": {
        "es": "Todos los CI responden; los puntos críticos devuelven HTTP 200 o responden al ping",
        "en": "All CIs respond; critical endpoints return HTTP 200 / answer ping",
        "zh": "所有配置项均有响应；关键端点返回 HTTP 200 或可 ping 通"},
    "cambio.prueba.post_change.functional.desc": {
        "es": "Pruebas funcionales de los servicios afectados por el cambio",
        "en": "Functional tests of the services affected by the change",
        "zh": "对受变更影响的服务进行功能测试"},
    "cambio.prueba.post_change.functional.esperado": {
        "es": "Todos los casos de prueba funcionales pasan sin regresiones",
        "en": "All functional test cases pass with no regressions",
        "zh": "所有功能测试用例均通过，无回归"},
    "cambio.prueba.post_change.performance.desc": {
        "es": "Comparar el rendimiento con la referencia (antes y después)",
        "en": "Compare performance against the baseline (before vs after)",
        "zh": "将性能与基线进行对比（变更前后）"},
    "cambio.prueba.post_change.performance.esperado": {
        "es": "Métricas de rendimiento dentro de ±10 % de la referencia previa al cambio",
        "en": "Performance metrics within ±10% of the pre-change baseline",
        "zh": "性能指标与变更前基线相差不超过 ±10%"},
    "cambio.prueba.post_change.cmdb_update.desc": {
        "es": "Comprobar y actualizar la CMDB con el nuevo estado de la configuración",
        "en": "Check and update the CMDB with the new configuration state",
        "zh": "核查并用新的配置状态更新 CMDB"},
    "cambio.prueba.post_change.cmdb_update.esperado": {
        "es": "CI actualizados en la CMDB; relaciones y atributos reflejan la nueva configuración",
        "en": "CIs updated in the CMDB; relationships and attributes reflect the new configuration",
        "zh": "CMDB 中的配置项已更新；关系和属性反映新配置"},
    "cambio.prueba.post_change.monitoring_30min.desc": {
        "es": "Observar las métricas de producción durante 30 minutos tras el cambio",
        "en": "Watch production metrics for 30 minutes after the change",
        "zh": "变更后观察生产指标 30 分钟"},
    "cambio.prueba.post_change.monitoring_30min.esperado": {
        "es": "Sin alertas inesperadas; incidencias normales para esa franja horaria",
        "en": "No unexpected alerts; normal incident levels for the time slot",
        "zh": "无意外告警；该时段事件数量正常"},
    "cambio.prueba.post_change.maintenance_off.desc": {
        "es": "Desactivar el modo mantenimiento en todos los CI afectados",
        "en": "Disable maintenance mode on all affected CIs",
        "zh": "在所有受影响的配置项上关闭维护模式"},
    "cambio.prueba.post_change.maintenance_off.esperado": {
        "es": "Los CI vuelven a «active» y la monitorización de alertas se reactiva",
        "en": "CIs return to 'active' and alert monitoring is re-enabled",
        "zh": "配置项恢复为“active”，告警监控重新启用"},
    "cambio.prueba.rollback_validation.config_restore.desc": {
        "es": "Comprobar que la configuración anterior se ha restaurado correctamente",
        "en": "Check that the previous configuration has been restored correctly",
        "zh": "检查先前的配置已正确恢复"},
    "cambio.prueba.rollback_validation.config_restore.esperado": {
        "es": "CI con una versión de configuración idéntica a la de la instantánea previa al cambio",
        "en": "CIs with a configuration version identical to the pre-change snapshot",
        "zh": "配置项的配置版本与变更前快照完全一致"},
    "cambio.prueba.rollback_validation.smoke.desc": {
        "es": "Pruebas de humo tras la vuelta atrás en los CI afectados",
        "en": "Post-rollback smoke tests on the affected CIs",
        "zh": "回滚后对受影响配置项执行冒烟测试"},
    "cambio.prueba.rollback_validation.smoke.esperado": {
        "es": "Todos los CI responden y funcionan igual que antes del cambio",
        "en": "All CIs respond and work exactly as before the change",
        "zh": "所有配置项均有响应，运行与变更前一致"},
    "cambio.prueba.rollback_validation.cmdb_revert.desc": {
        "es": "Confirmar que la CMDB refleja el estado previo al cambio",
        "en": "Confirm the CMDB reflects the pre-change state",
        "zh": "确认 CMDB 反映变更前的状态"},
    "cambio.prueba.rollback_validation.cmdb_revert.esperado": {
        "es": "El registro de la CMDB coincide con la referencia tomada antes del cambio",
        "en": "The CMDB record matches the baseline captured before the change",
        "zh": "CMDB 记录与变更前采集的基线一致"},
    "cambio.prueba.rollback_validation.incident_check.desc": {
        "es": "Comprobar que la vuelta atrás no ha generado incidentes activos",
        "en": "Check that the rollback has not caused any active incidents",
        "zh": "检查回滚未引发任何活动事件"},
    "cambio.prueba.rollback_validation.incident_check.esperado": {
        "es": "Ningún ticket de incidente abierto atribuible al cambio o a su vuelta atrás",
        "en": "No open incident tickets attributable to the change or its rollback",
        "zh": "没有可归因于该变更或其回滚的未结事件工单"},

    # ── Cambios: canales del plan de comunicación ──────────────────────────
    "cambio.canal.ops": {"es": "correo + mensajería (Slack/Teams)", "en": "email + IM (Slack/Teams)",
                         "zh": "邮件 + 即时通讯（Slack/Teams）"},
    "cambio.canal.service_desk": {"es": "correo + aviso del sistema de tickets",
                                  "en": "email + ticketing system notification", "zh": "邮件 + 工单系统通知"},
    "cambio.canal.correo": {"es": "correo", "en": "email", "zh": "邮件"},
    "cambio.canal.usuarios": {"es": "correo + banner en el portal de servicios",
                              "en": "email + service portal banner", "zh": "邮件 + 服务门户横幅"},
    "cambio.canal.direccion": {"es": "correo + teléfono / resumen ejecutivo",
                               "en": "email + phone / executive summary", "zh": "邮件 + 电话 / 管理层摘要"},
    "cambio.canal.noc": {"es": "mensajería (Slack/Teams) + alerta de monitorización",
                         "en": "IM (Slack/Teams) + monitoring alert", "zh": "即时通讯（Slack/Teams）+ 监控告警"},
    "cambio.canal.im_operaciones": {"es": "Mensajería (Slack/Teams) — canal #operations",
                                    "en": "IM (Slack/Teams) — #operations channel",
                                    "zh": "即时通讯（Slack/Teams）— #operations 频道"},
    "cambio.canal.im_service_desk": {"es": "Mensajería (Slack/Teams) — canal #service-desk",
                                     "en": "IM (Slack/Teams) — #service-desk channel",
                                     "zh": "即时通讯（Slack/Teams）— #service-desk 频道"},
    "cambio.canal.im_operaciones_urgente": {"es": "Mensajería (Slack/Teams) — canal #operations (URGENTE)",
                                            "en": "IM (Slack/Teams) — #operations channel (URGENT)",
                                            "zh": "即时通讯（Slack/Teams）— #operations 频道（紧急）"},

    # ── Cambios: avisos del plan de comunicación (asunto / mensaje) ────────
    # Las llaves dobles `{{...}}` son huecos que rellena quien envia el aviso.
    "cambio.aviso.t7d_direccion.asunto": {
        "es": "[CAMBIO CRÍTICO] {number} — {title}", "en": "[CRITICAL CHANGE] {number} — {title}",
        "zh": "[重大变更] {number} — {title}"},
    "cambio.aviso.t7d_direccion.mensaje": {
        "es": "Se planifica un cambio crítico ({number}): «{title}».\n"
              "Ventana propuesta: {ventana}. Tiempo de inactividad estimado: {parada} min.\n"
              "Se requiere confirmación de disponibilidad y aprobación ejecutiva.",
        "en": "A critical change is being planned ({number}): '{title}'.\n"
              "Proposed window: {ventana}. Estimated downtime: {parada} min.\n"
              "Availability confirmation and executive approval are required.",
        "zh": "正在计划一项重大变更（{number}）：“{title}”。\n"
              "建议窗口：{ventana}。预计停机时间：{parada} 分钟。\n"
              "需要确认人员可用并获得管理层批准。"},
    "cambio.aviso.t72h_usuarios.asunto": {
        "es": "[Aviso de mantenimiento] {number} — {title}", "en": "[Maintenance notice] {number} — {title}",
        "zh": "[维护通知] {number} — {title}"},
    "cambio.aviso.t72h_usuarios.mensaje": {
        "es": "Estimado usuario:\nSe realizará un mantenimiento programado ({number}) el {ventana}.\n"
              "Interrupción estimada: {parada} minutos. Disculpe las molestias.",
        "en": "Dear user,\nScheduled maintenance ({number}) will take place on {ventana}.\n"
              "Estimated interruption: {parada} minutes. We apologise for the inconvenience.",
        "zh": "尊敬的用户：\n计划维护（{number}）将于 {ventana} 进行。\n"
              "预计中断 {parada} 分钟。给您带来不便，敬请谅解。"},
    "cambio.aviso.t48h_service_desk.asunto": {
        "es": "[Aviso previo] Cambio {number} — {title}", "en": "[Advance notice] Change {number} — {title}",
        "zh": "[预先通知] 变更 {number} — {title}"},
    "cambio.aviso.t48h_service_desk.mensaje": {
        "es": "Cambio programado ({number}): «{title}».\n"
              "Ventana: {ventana}. Impacto: riesgo {riesgo}.\n"
              "Prepara guiones de respuesta para las consultas de los usuarios durante la ventana.",
        "en": "Scheduled change ({number}): '{title}'.\n"
              "Window: {ventana}. Impact: {riesgo} risk.\n"
              "Prepare response scripts for user queries during the window.",
        "zh": "计划变更（{number}）：“{title}”。\n"
              "窗口：{ventana}。影响：风险{riesgo}。\n"
              "请为窗口期间的用户咨询准备应答话术。"},
    "cambio.aviso.t48h_responsable.asunto": {
        "es": "[Cambio programado] {number} — {title}", "en": "[Scheduled change] {number} — {title}",
        "zh": "[计划变更] {number} — {title}"},
    "cambio.aviso.t48h_responsable.mensaje": {
        "es": "Cambio programado ({number}): «{title}».\n"
              "Ventana: {ventana}. Riesgo: {riesgo}.\n"
              "Asegúrese de que el equipo técnico esté disponible durante la ventana.",
        "en": "Scheduled change ({number}): '{title}'.\n"
              "Window: {ventana}. Risk: {riesgo}.\n"
              "Please make sure the technical team is available during the window.",
        "zh": "计划变更（{number}）：“{title}”。\n"
              "窗口：{ventana}。风险：{riesgo}。\n"
              "请确保技术团队在窗口期间可以到岗。"},
    "cambio.aviso.t24h_operaciones.asunto": {
        "es": "[Recordatorio] Cambio mañana: {number} — {title}",
        "en": "[Reminder] Change tomorrow: {number} — {title}", "zh": "[提醒] 明日变更：{number} — {title}"},
    "cambio.aviso.t24h_operaciones.mensaje": {
        "es": "Recordatorio: mañana se ejecuta el cambio {number}: «{title}».\n"
              "Ventana: {ventana}. Los planes de pruebas y de vuelta atrás deben estar listos.\n"
              "Confirma tu disponibilidad respondiendo a este mensaje.",
        "en": "Reminder: change {number} runs tomorrow: '{title}'.\n"
              "Window: {ventana}. The test and rollback plans must be ready.\n"
              "Confirm your availability by replying to this message.",
        "zh": "提醒：变更 {number}“{title}”将于明天执行。\n"
              "窗口：{ventana}。测试计划和回滚计划必须准备就绪。\n"
              "请回复本消息确认您可以到岗。"},
    "cambio.aviso.t24h_usuarios.asunto": {
        "es": "[Recordatorio: mantenimiento mañana] {number}", "en": "[Reminder: maintenance tomorrow] {number}",
        "zh": "[提醒：明日维护] {number}"},
    "cambio.aviso.t24h_usuarios.mensaje": {
        "es": "Recordatorio: mañana, {ventana}, se realizará el mantenimiento {number}.\n"
              "Inactividad estimada: {parada} min. Guarda tu trabajo antes de la ventana.",
        "en": "Reminder: maintenance {number} will take place tomorrow, {ventana}.\n"
              "Estimated downtime: {parada} min. Save your work before the window.",
        "zh": "提醒：维护 {number} 将于明天（{ventana}）进行。\n"
              "预计停机 {parada} 分钟。请在窗口开始前保存您的工作。"},
    "cambio.aviso.t1h_operaciones.asunto": {
        "es": "🔧 1 hora para el inicio: {number}", "en": "🔧 1 hour to start: {number}",
        "zh": "🔧 距开始还有 1 小时：{number}"},
    "cambio.aviso.t1h_operaciones.mensaje": {
        "es": "Dentro de 1 hora empieza el cambio {number}: «{title}».\n"
              "Confirma tu presencia en el canal de guardia. Plan de vuelta atrás accesible.",
        "en": "Change {number} starts in 1 hour: '{title}'.\n"
              "Confirm your presence in the on-call channel. Rollback plan available.",
        "zh": "变更 {number}“{title}”将在 1 小时后开始。\n"
              "请在值班频道确认到岗。回滚计划已可查阅。"},
    "cambio.aviso.t1h_service_desk.asunto": {
        "es": "⚠️ El cambio empieza en 1 h: {number}", "en": "⚠️ Change starts in 1h: {number}",
        "zh": "⚠️ 变更将在 1 小时后开始：{number}"},
    "cambio.aviso.t1h_service_desk.mensaje": {
        "es": "Dentro de 1 hora empieza {number}. Activad el modo guardia.\n"
              "Cualquier incidente relacionado durante la ventana: escalar al gestor del cambio.",
        "en": "{number} starts in 1 hour. Switch to on-call mode.\n"
              "Any related incident during the window: escalate to the change manager.",
        "zh": "{number} 将在 1 小时后开始。请进入值班模式。\n"
              "窗口期间如有相关事件：升级给变更经理。"},
    "cambio.aviso.inicio_operaciones.asunto": {
        "es": "▶️ Cambio iniciado: {number}", "en": "▶️ Change started: {number}", "zh": "▶️ 变更已开始：{number}"},
    "cambio.aviso.inicio_operaciones.mensaje": {
        "es": "El cambio {number} ha empezado a las {{hora_inicio_utc}} UTC.\n"
              "Monitorización activa. Informad de cualquier anomalía de inmediato.",
        "en": "Change {number} started at {{hora_inicio_utc}} UTC.\n"
              "Monitoring is active. Report any anomaly immediately.",
        "zh": "变更 {number} 已于 {{hora_inicio_utc}}（UTC）开始。\n"
              "监控已开启。如有异常请立即报告。"},
    "cambio.aviso.mitad_direccion.asunto": {
        "es": "[Estado] Cambio {number} en curso", "en": "[Status update] Change {number} in progress",
        "zh": "[状态更新] 变更 {number} 进行中"},
    "cambio.aviso.mitad_direccion.mensaje": {
        "es": "El cambio crítico {number} está en curso.\n"
              "Estado: {{estado_actual}}. Sin anomalías importantes detectadas hasta el momento.",
        "en": "Critical change {number} is in progress.\n"
              "Status: {{estado_actual}}. No major anomalies detected so far.",
        "zh": "重大变更 {number} 正在进行中。\n"
              "状态：{{estado_actual}}。目前未发现重大异常。"},
    "cambio.aviso.exito_operaciones.asunto": {
        "es": "✅ Cambio completado: {number}", "en": "✅ Change completed: {number}", "zh": "✅ 变更已完成：{number}"},
    "cambio.aviso.exito_operaciones.mensaje": {
        "es": "El cambio {number}: «{title}» se ha completado con éxito.\n"
              "Todas las pruebas posteriores han pasado. Sistemas en funcionamiento normal.",
        "en": "Change {number}: '{title}' has been completed successfully.\n"
              "All post-change tests passed. Systems are operating normally.",
        "zh": "变更 {number}“{title}”已成功完成。\n"
              "所有变更后测试均已通过。系统运行正常。"},
    "cambio.aviso.exito_usuarios.asunto": {
        "es": "✅ Mantenimiento finalizado: {number}", "en": "✅ Maintenance completed: {number}",
        "zh": "✅ 维护已完成：{number}"},
    "cambio.aviso.exito_usuarios.mensaje": {
        "es": "El mantenimiento programado {number} ha concluido.\n"
              "Todos los servicios están disponibles con normalidad. Gracias por su paciencia.",
        "en": "Scheduled maintenance {number} has finished.\n"
              "All services are available as normal. Thank you for your patience.",
        "zh": "计划维护 {number} 已结束。\n"
              "所有服务均已恢复正常。感谢您的耐心等待。"},
    "cambio.aviso.vuelta_operaciones.asunto": {
        "es": "❌ VUELTA ATRÁS iniciada: {number}", "en": "❌ ROLLBACK started: {number}",
        "zh": "❌ 已启动回滚：{number}"},
    "cambio.aviso.vuelta_operaciones.mensaje": {
        "es": "El cambio {number} ha activado el plan de vuelta atrás.\n"
              "Motivo: {{motivo_rollback}}. Equipo de vuelta atrás en acción. Tiempo estimado: {{eta_minutos}} min.",
        "en": "Change {number} has triggered the rollback plan.\n"
              "Reason: {{motivo_rollback}}. Rollback team at work. ETA: {{eta_minutos}} min.",
        "zh": "变更 {number} 已触发回滚计划。\n"
              "原因：{{motivo_rollback}}。回滚团队正在处理。预计耗时：{{eta_minutos}} 分钟。"},
    "cambio.aviso.vuelta_usuarios.asunto": {
        "es": "[Mantenimiento ampliado] {number}", "en": "[Extended maintenance] {number}",
        "zh": "[维护延长] {number}"},
    "cambio.aviso.vuelta_usuarios.mensaje": {
        "es": "El mantenimiento {number} ha encontrado un inconveniente y se está resolviendo.\n"
              "Restauración prevista: {{eta_restauracion}}. Disculpe el tiempo adicional.",
        "en": "Maintenance {number} has run into an issue that is being resolved.\n"
              "Expected restoration: {{eta_restauracion}}. We apologise for the extra time.",
        "zh": "维护 {number} 遇到问题，正在处理中。\n"
              "预计恢复时间：{{eta_restauracion}}。延长的时间敬请谅解。"},
    "cambio.aviso.pir_direccion.asunto": {
        "es": "[PIR] Cambio {number} — Informe posterior a la implantación",
        "en": "[PIR] Change {number} — Post-implementation report", "zh": "[PIR] 变更 {number} — 实施后报告"},
    "cambio.aviso.pir_direccion.mensaje": {
        "es": "Se ha completado la revisión posterior a la implantación del cambio {number}.\n"
              "Resultado: {{resultado_pir}}. Se adjunta el informe completo.",
        "en": "The post-implementation review of change {number} has been completed.\n"
              "Outcome: {{resultado_pir}}. Full report attached.",
        "zh": "变更 {number} 的实施后评审已完成。\n"
              "结果：{{resultado_pir}}。完整报告见附件。"},

    # ── Agente autónomo: playbooks de serie ────────────────────────────────
    "autonomo.agente": {"es": "Agente autónomo", "en": "Autonomous agent", "zh": "自主代理"},
    "autonomo.pb.pw-reset": {"es": "Restablecer contraseña", "en": "Password reset self-service",
                             "zh": "自助重置密码"},
    "autonomo.pb.vpn-issue": {"es": "Problema de VPN", "en": "VPN connectivity issue", "zh": "VPN 连接问题"},
    "autonomo.pb.email-issue": {"es": "Problema de correo", "en": "Email / Outlook issue", "zh": "邮件 / Outlook 问题"},
    "autonomo.pb.printer-issue": {"es": "Problema de impresora", "en": "Printer / print queue issue",
                                  "zh": "打印机 / 打印队列问题"},
    "autonomo.pb.slow-pc": {"es": "Equipo lento", "en": "Slow PC / performance issue", "zh": "电脑运行缓慢 / 性能问题"},
    "autonomo.pb.pw-reset.notify": {"es": "Se ha enviado respuesta automática al solicitante.",
                                    "en": "An automatic reply has been sent to the requester.",
                                    "zh": "已向申请人发送自动回复。"},
    "autonomo.pb.pw-reset.resolve": {"es": "Resuelto automáticamente: instrucciones para restablecer la contraseña enviadas.",
                                     "en": "Resolved automatically: password reset instructions sent.",
                                     "zh": "已自动解决：已发送密码重置说明。"},
    "autonomo.pb.vpn-issue.notify": {"es": "Ticket de VPN: respuesta automática enviada y escalado a Red.",
                                     "en": "VPN ticket: automatic reply sent and escalated to Networking.",
                                     "zh": "VPN 工单：已发送自动回复并升级至网络团队。"},
    "autonomo.pb.email-issue.resolve": {"es": "Resuelto automáticamente: guía de resolución de problemas enviada.",
                                        "en": "Resolved automatically: troubleshooting guide sent.",
                                        "zh": "已自动解决：已发送故障排除指南。"},
    "autonomo.pb.printer-issue.resolve": {"es": "Resuelto automáticamente: guía de impresora enviada.",
                                          "en": "Resolved automatically: printer guide sent.",
                                          "zh": "已自动解决：已发送打印机指南。"},
    "autonomo.pb.slow-pc.notify": {"es": "Ticket de rendimiento: respuesta enviada, pendiente de revisión técnica.",
                                   "en": "Performance ticket: reply sent, pending technical review.",
                                   "zh": "性能工单：已发送回复，等待技术审核。"},
    "autonomo.motivo.p1": {"es": "Los tickets P1 siempre requieren revisión humana",
                           "en": "P1 tickets always require human review", "zh": "P1 工单始终需要人工审核"},
    "autonomo.motivo.alta": {"es": "Confianza alta ({confianza}) y playbook «{playbook}» encontrado",
                             "en": "High confidence ({confianza}) and playbook '{playbook}' matched",
                             "zh": "置信度高（{confianza}），已匹配剧本“{playbook}”"},
    "autonomo.motivo.media": {"es": "Confianza media ({confianza}): el playbook ayuda sin cerrar el ticket",
                              "en": "Medium confidence ({confianza}): playbook assist without auto-close",
                              "zh": "置信度中等（{confianza}）：由剧本辅助处理，不自动关闭工单"},
    "autonomo.motivo.baja": {"es": "Confianza demasiado baja ({confianza}) o ningún playbook encontrado",
                             "en": "Confidence too low ({confianza}) or no matching playbook",
                             "zh": "置信度过低（{confianza}）或没有匹配的剧本"},

    # ── Herramientas del asistente: bloqueos de la política de acceso ──────
    "politica.herramienta_sin_politica": {
        "es": "La herramienta '{herramienta}' no tiene política de acceso: no se ejecuta.",
        "en": "The tool '{herramienta}' has no access policy, so it will not run.",
        "zh": "工具“{herramienta}”没有访问策略，因此不会执行。"},
    "politica.herramienta_rol": {
        "es": "Acceso denegado: '{herramienta}' no está disponible para tu rol.",
        "en": "Access denied: '{herramienta}' is not available for your role.",
        "zh": "访问被拒绝：您的角色无法使用“{herramienta}”。"},
    "politica.herramienta_grc": {
        "es": "La política de gobierno de tu organización no permite '{accion}' en '{modulo}'.",
        "en": "Your organisation's governance policy does not allow '{accion}' in '{modulo}'.",
        "zh": "贵组织的治理策略不允许在“{modulo}”中执行“{accion}”。"},

    # ── Módulos de IA: cupo diario y módulo apagado ────────────────────────
    "ia.modulo_deshabilitado": {
        "es": "El módulo '{modulo}' está deshabilitado por el administrador.",
        "en": "The module '{modulo}' has been disabled by the administrator.",
        "zh": "模块“{modulo}”已被管理员停用。"},
    "ia.limite_diario": {
        "es": "Has alcanzado el límite diario de {n} acciones para '{modulo}'. "
              "Vuelve mañana o contacta con el administrador.",
        "en": "You have reached the daily limit of {n} actions for '{modulo}'. "
              "Try again tomorrow or contact the administrator.",
        "zh": "您已达到“{modulo}”每日 {n} 次操作的上限。请明天再试或联系管理员。"},

    # ── Gobernanza de la IA: bloqueos de entrada y salida ──────────────────
    # `{politica}` es el nombre que puso la empresa (sale tal cual).
    "gobernanza.mensaje_bloqueado": {
        "es": "[Mensaje bloqueado por política de gobernanza: {politica}]",
        "en": "[Message blocked by governance policy: {politica}]",
        "zh": "[消息已被治理策略拦截：{politica}]"},
    "gobernanza.respuesta_bloqueada": {
        "es": "[Respuesta bloqueada por política de gobernanza]",
        "en": "[Response blocked by governance policy]",
        "zh": "[回复已被治理策略拦截]"},

    # ── Ausencias: cupo lleno sin mensaje propio de la empresa ─────────────
    "ausencias.cupo_lleno": {"es": "No queda plaza en el cupo para esas fechas",
                             "en": "There are no places left in the quota for those dates",
                             "zh": "这些日期的名额已满"},

    # ── Historial del ticket: textos que escribe el sistema (migración 192) ─
    # Se guardan con su clave (`sd_ticket_history.new_value_key`) y se pintan
    # en el idioma de quien mira (`app/services/textos_guardados.py`).
    "historial.autorresuelto_kb": {
        "es": "[Resuelto automáticamente] Resuelto con el artículo de la base de conocimiento {numero} — {titulo}",
        "en": "[Auto-resolved] Resolved automatically via knowledge base article {numero} — {titulo}",
        "zh": "[自动解决] 已通过知识库文章 {numero} — {titulo} 自动解决"},
    "historial.posible_duplicado": {"es": "Posible duplicado de {numero}",
                                    "en": "Possible duplicate of {numero}",
                                    "zh": "可能与 {numero} 重复"},
    "historial.aprovisionado": {"es": "Aprovisionado automáticamente con el servicio «{servicio}» ({fecha})",
                                "en": "Auto-provisioned via the service '{servicio}' ({fecha})",
                                "zh": "已通过服务“{servicio}”自动开通（{fecha}）"},
    "historial.reabierto_tras_autorresolucion": {"es": "Reabierto después de la resolución automática",
                                                 "en": "Reopened after automatic resolution",
                                                 "zh": "自动解决后被重新打开"},
}
