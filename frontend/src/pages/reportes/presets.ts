/**
 * Catálogo de informes predefinidos (PRESETS).
 * Troceado de ReportsPage.tsx sin cambio de comportamiento (23-11-2026).
 */


// ── Presets ───────────────────────────────────────────────────────────────────
export const PRESETS = [
  // Horas y costes
  { id: 'p1',  label: 'reportes_presets.p1', metric: 'hours_by_month',            chart: 'area',        color: 'var(--accent)', cat: 'Horas' },
  { id: 'p2',  label: 'reportes_presets.p2', metric: 'hours_by_person',            chart: 'bar',         color: 'var(--success)', cat: 'Horas' },
  { id: 'p3',  label: 'reportes_presets.p3', metric: 'hours_heatmap',              chart: 'heatmap',     color: 'var(--accent)', cat: 'Horas' },
  { id: 'p4',  label: 'reportes_presets.p4', metric: 'hours_billable_vs_internal', chart: 'bar_stacked', color: 'var(--accent)', cat: 'Horas' },
  { id: 'p24', label: 'reportes_presets.p24', metric: 'hours_by_project',           chart: 'bar',         color: 'var(--info)', cat: 'Horas' },
  { id: 'p25', label: 'reportes_presets.p25', metric: 'hours_by_week',              chart: 'line',        color: 'var(--accent)', cat: 'Horas' },
  { id: 'p26', label: 'reportes_presets.p26', metric: 'hours_by_department',        chart: 'pie',         color: 'var(--accent)', cat: 'Horas' },
  // Rentabilidad y costes
  { id: 'p5',  label: 'reportes_presets.p5', metric: 'margin_by_project',          chart: 'bar_grouped', color: 'var(--warning)', cat: 'Rentabilidad' },
  { id: 'p6',  label: 'reportes_presets.p6', metric: 'cost_vs_budget',             chart: 'bar_grouped', color: 'var(--danger)', cat: 'Rentabilidad' },
  { id: 'p7',  label: 'reportes_presets.p7', metric: 'margin_evolution',           chart: 'line',        color: 'var(--success)', cat: 'Rentabilidad' },
  { id: 'p8',  label: 'reportes_presets.p8', metric: 'budget_consumption',         chart: 'bar',         color: 'var(--warning)', cat: 'Rentabilidad' },
  { id: 'p27', label: 'reportes_presets.p27', metric: 'cost_by_project',            chart: 'bar',         color: 'var(--orange)', cat: 'Costes' },
  { id: 'p28', label: 'reportes_presets.p28', metric: 'cost_by_person',             chart: 'bar',         color: 'var(--orange)', cat: 'Costes' },
  { id: 'p29', label: 'reportes_presets.p29', metric: 'cost_by_month',              chart: 'line',        color: 'var(--danger)', cat: 'Costes' },
  // Estructura de coste (perfiles versionados, multi-país)
  { id: 'pc1', label: 'reportes_presets.pc1', metric: 'cost_per_hour_by_person',     chart: 'bar',  color: 'var(--orange)', cat: 'Costes' },
  { id: 'pc2', label: 'reportes_presets.pc2', metric: 'cost_per_hour_by_department', chart: 'bar',  color: 'var(--warning)', cat: 'Costes' },
  { id: 'pc3', label: 'reportes_presets.pc3', metric: 'cost_per_hour_by_country',    chart: 'bar',  color: 'var(--warning)', cat: 'Costes' },
  { id: 'pc4', label: 'reportes_presets.pc4', metric: 'annual_cost_by_person',    chart: 'bar',  color: 'var(--danger)', cat: 'Costes' },
  { id: 'pc5', label: 'reportes_presets.pc5', metric: 'annual_cost_by_country',      chart: 'bar',  color: 'var(--danger)', cat: 'Costes' },
  { id: 'pc6', label: 'reportes_presets.pc6', metric: 'cost_profile_coverage',       chart: 'pie',  color: 'var(--success)', cat: 'Costes' },
  { id: 'pc7', label: 'reportes_presets.pc7', metric: 'employer_cost_pct_by_country',chart: 'bar',  color: 'var(--purple)', cat: 'Costes' },
  { id: 'pc8', label: 'reportes_presets.pc8', metric: 'cost_per_hour_drift',         chart: 'line', color: 'var(--info)', cat: 'Costes' },
  // Proyectos y agilidad
  { id: 'p9',  label: 'reportes_presets.p9', metric: 'tasks_by_status',            chart: 'pie',         color: 'var(--accent)', cat: 'Proyectos' },
  { id: 'p10', label: 'reportes_presets.p10', metric: 'sprint_velocity',            chart: 'bar',         color: 'var(--purple)', cat: 'Agilidad' },
  { id: 'p11', label: 'reportes_presets.p11', metric: 'tasks_overdue',              chart: 'bar',         color: 'var(--danger)', cat: 'Agilidad' },
  { id: 'p12', label: 'reportes_presets.p12', metric: 'tasks_lead_time',            chart: 'bar',         color: 'var(--warning)', cat: 'Agilidad' },
  { id: 'p30', label: 'reportes_presets.p30', metric: 'tasks_by_project',           chart: 'bar',         color: 'var(--accent)', cat: 'Proyectos' },
  { id: 'p31', label: 'reportes_presets.p31', metric: 'projects_by_status',         chart: 'pie',         color: 'var(--chart-teal)', cat: 'Proyectos' },
  { id: 'p32', label: 'reportes_presets.p32', metric: 'projects_by_type',           chart: 'pie',         color: 'var(--chart-teal)', cat: 'Proyectos' },
  { id: 'p33', label: 'reportes_presets.p33', metric: 'deliverables_status',        chart: 'pie',         color: 'var(--purple)', cat: 'Proyectos' },
  { id: 'p34', label: 'reportes_presets.p34', metric: 'risks_by_level',             chart: 'pie',         color: 'var(--danger)', cat: 'Proyectos' },
  { id: 'p35', label: 'reportes_presets.p35', metric: 'tasks_by_assignee',          chart: 'bar_grouped', color: 'var(--chart-teal)', cat: 'Agilidad' },
  { id: 'p36', label: 'reportes_presets.p36', metric: 'tasks_blocked_by_project',   chart: 'bar',         color: 'var(--danger)', cat: 'Agilidad' },
  { id: 'p37', label: 'reportes_presets.p37', metric: 'sprint_completion_rate',     chart: 'line',        color: 'var(--success)', cat: 'Agilidad' },
  { id: 'p38', label: 'reportes_presets.p38', metric: 'change_requests_status',     chart: 'bar',         color: 'var(--warning)', cat: 'Agilidad' },
  // Service Desk
  { id: 'p13', label: 'reportes_presets.p13', metric: 'ticket_volume_trend',        chart: 'line',        color: 'var(--accent)', cat: 'Service Desk' },
  { id: 'p14', label: 'reportes_presets.p14', metric: 'ticket_sla_compliance',      chart: 'line',        color: 'var(--success)', cat: 'Service Desk' },
  { id: 'p15', label: 'reportes_presets.p15', metric: 'ticket_resolution_time',     chart: 'bar',         color: 'var(--purple)', cat: 'Service Desk' },
  { id: 'p16', label: 'reportes_presets.p16', metric: 'ticket_csat',                chart: 'bar',         color: 'var(--warning)', cat: 'Service Desk' },
  { id: 'p39', label: 'reportes_presets.p39', metric: 'tickets_by_status',          chart: 'pie',         color: 'var(--accent)', cat: 'Service Desk' },
  { id: 'p40', label: 'reportes_presets.p40', metric: 'tickets_by_type',            chart: 'bar',         color: 'var(--info)', cat: 'Service Desk' },
  { id: 'p41', label: 'reportes_presets.p41', metric: 'tickets_by_priority',        chart: 'bar',         color: 'var(--coral)', cat: 'Service Desk' },
  { id: 'p42', label: 'reportes_presets.p42', metric: 'tickets_by_agent',          chart: 'bar_grouped', color: 'var(--accent)', cat: 'Service Desk' },
  // Negocio y RRHH
  { id: 'p17', label: 'reportes_presets.p17', metric: 'pipeline_by_stage',          chart: 'bar',         color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p18', label: 'reportes_presets.p18', metric: 'win_rate_evolution',         chart: 'line',        color: 'var(--success)', cat: 'Negocio' },
  { id: 'p19', label: 'reportes_presets.p19', metric: 'revenue_by_client',          chart: 'bar',         color: 'var(--warning)', cat: 'Negocio' },
  { id: 'p20', label: 'reportes_presets.p20', metric: 'productivity_by_person',     chart: 'bar_grouped', color: 'var(--chart-lime)', cat: 'RRHH' },
  { id: 'p21', label: 'reportes_presets.p21', metric: 'absences_by_type',           chart: 'pie',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p43', label: 'reportes_presets.p43', metric: 'pipeline_evolution',         chart: 'line',        color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p44', label: 'reportes_presets.p44', metric: 'contracts_by_status',        chart: 'bar',         color: 'var(--purple)', cat: 'Negocio' },
  { id: 'p45', label: 'reportes_presets.p45', metric: 'projects_by_client',         chart: 'bar_grouped', color: 'var(--chart-teal)', cat: 'Negocio' },
  { id: 'p46', label: 'reportes_presets.p46', metric: 'absences_by_person',         chart: 'bar',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p47', label: 'reportes_presets.p47', metric: 'absences_by_month',          chart: 'line',        color: 'var(--orange)', cat: 'RRHH' },
  { id: 'p48', label: 'reportes_presets.p48', metric: 'load_by_person',             chart: 'line',        color: 'var(--chart-teal)', cat: 'Capacidad' },
  { id: 'p49', label: 'reportes_presets.p49', metric: 'load_by_week',               chart: 'line',        color: 'var(--sky-blue)', cat: 'Capacidad' },
  // ALM e IA
  { id: 'p22', label: 'reportes_presets.p22', metric: 'license_cost_by_vendor',     chart: 'bar',         color: 'var(--accent)', cat: 'ALM' },
  { id: 'p23', label: 'reportes_presets.p23', metric: 'semantic_accuracy_trend',    chart: 'line',        color: 'var(--purple)', cat: 'IA' },
  { id: 'p50', label: 'reportes_presets.p50', metric: 'license_expiry_timeline',    chart: 'bar',         color: 'var(--accent)', cat: 'ALM' },
  { id: 'p51', label: 'reportes_presets.p51', metric: 'license_utilization',        chart: 'bar',         color: 'var(--info)', cat: 'ALM' },
  { id: 'p52', label: 'reportes_presets.p52', metric: 'assets_by_type',             chart: 'pie',         color: 'var(--sky-blue)', cat: 'ALM' },
  { id: 'p53', label: 'reportes_presets.p53', metric: 'semantic_assignments_by_mode', chart: 'pie',       color: 'var(--purple)', cat: 'IA' },
  { id: 'p54', label: 'reportes_presets.p54', metric: 'forecast_revenue',           chart: 'bar_stacked', color: 'var(--success)', cat: 'Estrategia' },
  { id: 'p55', label: 'reportes_presets.p55', metric: 'burnout_index',              chart: 'bar',         color: 'var(--orange)', cat: 'Bienestar' },
  // OKR
  { id: 'p56', label: 'reportes_presets.p56', metric: 'okr_progress_by_objective',   chart: 'bar',         color: 'var(--success)', cat: 'OKR' },
  { id: 'p57', label: 'reportes_presets.p57', metric: 'okr_kr_completion_rate',       chart: 'bar',         color: 'var(--success)', cat: 'OKR' },
  // NPS
  { id: 'p58', label: 'reportes_presets.p58', metric: 'nps_by_client',                chart: 'bar',         color: 'var(--warning)', cat: 'NPS' },
  { id: 'p59', label: 'reportes_presets.p59', metric: 'nps_trend',                    chart: 'line',        color: 'var(--warning)', cat: 'NPS' },
  { id: 'p60', label: 'reportes_presets.p60', metric: 'nps_distribution',             chart: 'pie',         color: 'var(--orange)', cat: 'NPS' },
  { id: 'p61', label: 'reportes_presets.p61', metric: 'client_health_score',          chart: 'bar',         color: 'var(--danger)', cat: 'NPS' },
  // Formación
  { id: 'p62', label: 'reportes_presets.p62', metric: 'training_completion_rate',     chart: 'bar',         color: 'var(--purple)', cat: 'Formación' },
  { id: 'p63', label: 'reportes_presets.p63', metric: 'certifications_by_user',        chart: 'bar',         color: 'var(--purple)', cat: 'Formación' },
  // Git
  { id: 'p64', label: 'reportes_presets.p64', metric: 'prs_by_author',                chart: 'bar',         color: 'var(--info)', cat: 'Git' },
  { id: 'p65', label: 'reportes_presets.p65', metric: 'prs_by_project',               chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p66', label: 'reportes_presets.p66', metric: 'pr_cycle_time',                chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p67', label: 'reportes_presets.p67', metric: 'deployments_by_env',           chart: 'bar',         color: 'var(--sky-blue)', cat: 'Git' },
  { id: 'p68', label: 'reportes_presets.p68', metric: 'deployment_success_rate',      chart: 'bar',         color: 'var(--accent-dim)', cat: 'Git' },
  // Ingresos
  { id: 'p69', label: 'reportes_presets.p69', metric: 'revenue_recognized_by_month',  chart: 'line',        color: 'var(--success)', cat: 'Ingresos' },
  { id: 'p70', label: 'reportes_presets.p70', metric: 'revenue_by_contract',          chart: 'bar',         color: 'var(--success)', cat: 'Ingresos' },
  // Gastos
  { id: 'p71', label: 'reportes_presets.p71', metric: 'expenses_by_category',         chart: 'pie',         color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p72', label: 'reportes_presets.p72', metric: 'expenses_by_project',          chart: 'bar',         color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p73', label: 'reportes_presets.p73', metric: 'expenses_billable_vs_internal', chart: 'pie',        color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p74', label: 'reportes_presets.p74', metric: 'expenses_trend',               chart: 'line',        color: 'var(--danger)', cat: 'Gastos' },
  { id: 'p75', label: 'reportes_presets.p75', metric: 'expenses_pending_approval',    chart: 'bar',         color: 'var(--danger)', cat: 'Gastos' },
  // Sprints
  { id: 'p76', label: 'reportes_presets.p76', metric: 'sprint_velocity_trend',         chart: 'line',        color: 'var(--accent)', cat: 'Sprints' },
  { id: 'p77', label: 'reportes_presets.p77', metric: 'sprint_completion_rate',        chart: 'bar',         color: 'var(--purple)', cat: 'Sprints' },
  // Tareas
  { id: 'p78', label: 'reportes_presets.p78', metric: 'tasks_by_status',               chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p79', label: 'reportes_presets.p79', metric: 'tasks_by_priority',             chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p80', label: 'reportes_presets.p80', metric: 'tasks_overdue_by_assignee',     chart: 'bar',         color: 'var(--danger)', cat: 'Tareas' },
  { id: 'p81', label: 'reportes_presets.p81', metric: 'task_completion_trend',         chart: 'line',        color: 'var(--success)', cat: 'Tareas' },
  { id: 'p82', label: 'reportes_presets.p82', metric: 'tasks_by_assignee',             chart: 'bar',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p83', label: 'reportes_presets.p83', metric: 'epics_by_status',               chart: 'pie',         color: 'var(--success)', cat: 'Tareas' },
  { id: 'p84', label: 'reportes_presets.p84', metric: 'milestones_on_time_rate',       chart: 'pie',         color: 'var(--info)', cat: 'Proyectos' },
  // Portfolio
  { id: 'p85', label: 'reportes_presets.p85', metric: 'portfolio_budget_usage',        chart: 'bar_stacked', color: 'var(--purple)', cat: 'Portfolio' },
  // RRHH evaluaciones
  { id: 'p86', label: 'reportes_presets.p86', metric: 'performance_scores_by_person',  chart: 'bar',         color: 'var(--warning)', cat: 'RRHH' },
  { id: 'p87', label: 'reportes_presets.p87', metric: 'performance_cycle_completion_rate', chart: 'bar',    color: 'var(--warning)', cat: 'RRHH' },
  // Horas (timesheets)
  { id: 'p88', label: 'reportes_presets.p88', metric: 'timesheets_approval_rate',      chart: 'pie',         color: 'var(--info)', cat: 'Horas' },
  { id: 'p89', label: 'reportes_presets.p89', metric: 'timesheets_billable_hours_trend', chart: 'line',     color: 'var(--accent)', cat: 'Horas' },
  // RRHH ausencias
  { id: 'p90', label: 'reportes_presets.p90', metric: 'absences_by_type',              chart: 'pie',         color: 'var(--purple)', cat: 'RRHH' },
  { id: 'p91', label: 'reportes_presets.p91', metric: 'absences_by_person',            chart: 'bar',         color: 'var(--purple)', cat: 'RRHH' },
  // Facturación
  { id: 'p92', label: 'reportes_presets.p92', metric: 'invoices_by_status',            chart: 'bar',         color: 'var(--sky-blue)', cat: 'Facturación' },
  { id: 'p93', label: 'reportes_presets.p93', metric: 'invoice_amount_by_month',       chart: 'line',        color: 'var(--chart-teal)', cat: 'Facturación' },
  { id: 'p94', label: 'reportes_presets.p94', metric: 'invoice_amount_by_client',      chart: 'bar',         color: 'var(--sky-blue)', cat: 'Facturación' },
  { id: 'p95', label: 'reportes_presets.p95', metric: 'invoice_overdue_amount',        chart: 'bar',         color: 'var(--danger)', cat: 'Facturación' },
  // Alertas
  { id: 'p96', label: 'reportes_presets.p96', metric: 'alerts_by_severity',            chart: 'pie',         color: 'var(--orange)', cat: 'Alertas' },
  { id: 'p97', label: 'reportes_presets.p97', metric: 'alerts_by_type',                chart: 'bar',         color: 'var(--orange)', cat: 'Alertas' },
  { id: 'p98', label: 'reportes_presets.p98', metric: 'unresolved_alerts_by_project',  chart: 'bar',         color: 'var(--orange)', cat: 'Alertas' },
  // Service Desk SLA
  { id: 'p99', label: 'reportes_presets.p99', metric: 'sla_breach_trend',              chart: 'line',        color: 'var(--danger)', cat: 'Service Desk' },
  { id: 'p100', label: 'reportes_presets.p100', metric: 'sla_breach_by_type',            chart: 'bar',         color: 'var(--danger)', cat: 'Service Desk' },
  // Automatizaciones
  { id: 'p101', label: 'reportes_presets.p101', metric: 'automation_success_rate',       chart: 'pie',         color: 'var(--purple)', cat: 'Automatizaciones' },
  { id: 'p102', label: 'reportes_presets.p102', metric: 'automation_run_stats',          chart: 'bar_stacked', color: 'var(--purple)', cat: 'Automatizaciones' },
  // CMDB
  { id: 'p103', label: 'reportes_presets.p103', metric: 'cmdb_items_by_status',          chart: 'pie',         color: 'var(--accent-dim)', cat: 'CMDB' },
  { id: 'p104', label: 'reportes_presets.p104', metric: 'cmdb_items_by_environment',     chart: 'bar',         color: 'var(--accent)', cat: 'CMDB' },
  { id: 'p105', label: 'reportes_presets.p105', metric: 'cmdb_items_by_type',            chart: 'pie',         color: 'var(--accent)', cat: 'CMDB' },
  // Negocio extra
  { id: 'p106', label: 'reportes_presets.p106', metric: 'clients_by_industry',           chart: 'pie',         color: 'var(--chart-teal)', cat: 'Negocio' },
  { id: 'p107', label: 'reportes_presets.p107', metric: 'opportunity_by_owner',          chart: 'bar',         color: 'var(--chart-teal)', cat: 'Negocio' },
]

export type Preset = typeof PRESETS[number]
