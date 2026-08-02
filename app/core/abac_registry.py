"""
ABAC route registry.

Maps URL path prefixes to (resource_type, action) tuples that the
ABACMiddleware will enforce automatically.  The middleware performs an
opt-in check: only routes whose prefix appears in this dict are verified.
Routes NOT listed here are left to endpoint-level guards or RBAC.

Key format: path prefix (without trailing slash).
Value format: (resource_type, action)

────────────────────────────────────────────────────────────────────────────────
Cobertura (auditoría 2026-07, docs/AUDIT_2026_07_FULL.md §1.5)
────────────────────────────────────────────────────────────────────────────────
Antes este registro tenía 13 prefijos de los 127 que expone la API, así que el
guard-test `test_abac_registry_completeness` solo vigilaba una allowlist mínima.
Ahora la cobertura es completa: **todo prefijo de primer nivel de /api/v1 y /api/v2
está en este dict o en ABAC_EXEMPT_PREFIXES con su motivo**, y
`tests/test_abac_registry_completeness.py` lo verifica.

Semántica importante — esto NO cierra rutas por sorpresa:
`enforce_abac()` es **fail-open**. Si la organización no tiene ninguna política ABAC
activa que aplique al resource_type, la petición pasa y el RBAC del endpoint sigue
siendo la única autoridad. Registrar un prefijo aquí solo significa «si un admin
define una política para este resource_type, se aplicará también a estas rutas».

Sobre `action`: hoy es informativo (log + métrica). `enforce_abac()` no lo pasa a
`evaluate_access()`, así que el middleware todavía no distingue GET de DELETE. Se
deja "read" de forma uniforme para no sugerir una granularidad que no existe.
"""

ABAC_ROUTE_REGISTRY: dict[str, tuple[str, str]] = {
    # ── Entrega: proyectos, trabajo y planificación ─────────────────────────────
    "/api/v1/projects":              ("project",          "read"),
    "/api/v1/project-workflows":     ("project",          "read"),
    "/api/v1/smart-schedule":        ("project",          "read"),
    "/api/v1/raci":                  ("project",          "read"),
    "/api/v1/portfolios":            ("portfolio",        "read"),
    "/api/v1/tasks":                 ("task",             "read"),
    "/api/v1/task-dependencies":     ("task",             "read"),
    "/api/v1/issue-types":           ("task",             "read"),
    "/api/v1/epics":                 ("epic",             "read"),
    "/api/v1/epic-dependencies":     ("epic",             "read"),
    "/api/v1/sprints":               ("sprint",           "read"),
    "/api/v1/milestones":            ("milestone",        "read"),
    "/api/v1/deliverables":          ("deliverable",      "read"),
    "/api/v1/custom-fields":         ("custom_field",     "read"),
    "/api/v1/templates":             ("project_template", "read"),
    "/api/v1/advanced-config":       ("project_template", "read"),

    # ── Personas, capacidad y organización ──────────────────────────────────────
    "/api/v1/users":                 ("user",             "read"),
    "/api/v1/permissions":           ("permission",       "read"),
    "/api/v1/organizations":         ("organization",     "read"),
    "/api/v1/orgs":                  ("organization",     "read"),
    "/api/v1/settings":              ("setting",          "read"),
    "/api/v1/resources":             ("resource",         "read"),
    "/api/v1/resource-forecast":     ("resource",         "read"),
    "/api/v1/resource-demand":       ("resource",         "read"),
    "/api/v1/capacity":              ("capacity",         "read"),
    "/api/v1/absences":              ("absence",          "read"),
    "/api/v1/skills":                ("skill",            "read"),
    "/api/v1/training":              ("training",         "read"),
    "/api/v1/performance":           ("performance_review", "read"),
    "/api/v1/onboarding":            ("onboarding",       "read"),
    "/api/v1/user-costs":            ("user_cost",        "read"),

    # ── Tiempo y dinero ────────────────────────────────────────────────────────
    "/api/v1/timesheets":            ("timesheet",        "read"),
    "/api/v1/imputations":           ("imputation",       "read"),
    "/api/v1/expenses":              ("expense",          "read"),
    "/api/v1/invoices":              ("invoice",          "read"),
    "/api/v1/billing-reports":       ("invoice",          "read"),
    "/api/v1/budgets":               ("budget",           "read"),
    "/api/v1/rate-cards":            ("rate_card",        "read"),
    "/api/v1/profitability":         ("profitability",    "read"),
    "/api/v2/profitability":         ("profitability",    "read"),
    "/api/v1/revenue":               ("revenue",          "read"),
    "/api/v1/revenue-forecast":      ("revenue",          "read"),
    "/api/v1/revenue-recognition":   ("revenue",          "read"),
    "/api/v1/currency":              ("currency",         "read"),
    "/api/v1/accounting":            ("accounting",       "read"),
    "/api/v1/scenarios":             ("scenario",         "read"),
    "/api/v1/approvals":             ("approval",         "read"),
    "/api/v1/approval-workflows":    ("approval",         "read"),

    # ── CRM ────────────────────────────────────────────────────────────────────
    "/api/v1/clients":               ("client",           "read"),
    "/api/v1/customers":             ("client",           "read"),
    "/api/v1/contracts":             ("contract",         "read"),
    "/api/v1/contracts-ai":          ("contract",         "read"),
    "/api/v1/pipeline":              ("opportunity",      "read"),
    "/api/v1/nps":                   ("nps",              "read"),

    # ── Estrategia ─────────────────────────────────────────────────────────────
    "/api/v1/okrs":                  ("okr",              "read"),

    # ── Riesgo, cambio y cumplimiento ──────────────────────────────────────────
    "/api/v1/risks":                 ("risk",             "read"),
    "/api/v1/risk-scores":           ("risk",             "read"),
    "/api/v1/overrun-prediction":    ("risk",             "read"),
    "/api/v1/predictions":           ("prediction",       "read"),
    "/api/v1/changes":               ("change_request",   "read"),
    "/api/v1/cab":                   ("change_request",   "read"),
    "/api/v1/grc":                   ("grc",              "read"),
    "/api/v1/governance":            ("governance",       "read"),
    "/api/v1/gdpr":                  ("gdpr",             "read"),
    "/api/v1/security-observability": ("security_event",  "read"),
    "/api/v1/abac":                  ("abac_policy",      "read"),
    "/api/v1/ai-governance":         ("ai_governance",    "read"),
    "/api/v1/activity":              ("activity_log",     "read"),
    "/api/v1/events":                ("activity_log",     "read"),

    # ── Service Desk / ITSM ────────────────────────────────────────────────────
    "/api/v1/sd":                    ("service_desk",     "read"),
    "/api/v1/cmdb":                  ("cmdb",             "read"),
    "/api/v1/kb":                    ("kb_article",       "read"),
    "/api/v1/alm":                   ("alm",              "read"),
    "/api/v1/bpmn-processes":        ("process",          "read"),
    "/api/v1/automations":           ("automation",       "read"),
    "/api/v1/automation-workflows":  ("automation",       "read"),
    "/api/v1/enterprise":            ("enterprise",       "read"),

    # ── Documentos y comunicación ──────────────────────────────────────────────
    "/api/v1/documents":             ("document",         "read"),
    "/api/v1/pdf":                   ("document",         "read"),
    "/api/v1/esign":                 ("document",         "read"),
    "/api/v1/meetings":              ("meeting",          "read"),
    "/api/v1/bookings":              ("booking",          "read"),
    "/api/v1/notifications":         ("notification",     "read"),
    "/api/v1/email":                 ("notification",     "read"),
    "/api/v1/alerts":                ("alert",            "read"),

    # ── Analítica y BI ─────────────────────────────────────────────────────────
    "/api/v1/bi":                    ("bi",               "read"),
    "/api/v1/analytics":             ("analytics",        "read"),
    "/api/v1/dashboard":             ("dashboard",        "read"),
    "/api/v1/dashboard-widgets":     ("dashboard",        "read"),
    "/api/v1/reports":               ("report",           "read"),
    "/api/v1/fts":                   ("search",           "read"),
    "/api/v1/global-search":         ("search",           "read"),
    "/api/v1/semantic":              ("search",           "read"),

    # ── IA ─────────────────────────────────────────────────────────────────────
    "/api/v1/ai":                    ("ai",               "read"),
    "/api/v1/ai-chat":               ("ai",               "read"),
    "/api/v1/ai-modules":            ("ai",               "read"),
    "/api/v1/ai-planning":           ("ai",               "read"),
    "/api/v1/ai-providers":          ("ai",               "read"),
    "/api/v1/oracle":                ("ai",               "read"),
    "/api/v1/voice":                 ("ai",               "read"),

    # ── Integraciones ──────────────────────────────────────────────────────────
    "/api/v1/integrations":          ("integration",      "read"),
    "/api/v1/integrations-hub":      ("integration",      "read"),
    "/api/v1/marketplace":           ("integration",      "read"),
    "/api/v1/oauth-integrations":    ("integration",      "read"),
    "/api/v1/jira":                  ("integration",      "read"),
    "/api/v1/git":                   ("integration",      "read"),
    "/api/v1/slack":                 ("integration",      "read"),
    "/api/v1/m365":                  ("integration",      "read"),
    "/api/v1/salesforce-sync":       ("integration",      "read"),
    "/api/v1/developer":             ("developer_app",    "read"),
}


# Prefijos deliberadamente FUERA de ABAC, con su motivo. El guard-test exige que
# cada prefijo de la API esté aquí o en el registro de arriba, así que un dominio
# nuevo no puede quedarse sin decisión por descuido.
ABAC_EXEMPT_PREFIXES: dict[str, str] = {
    # Autenticación: ABAC evalúa a un usuario ya autenticado, no puede gobernar el
    # propio flujo de login.
    "/api/v1/auth":            "flujo de autenticación",
    "/api/v1/mfa":             "segundo factor y endpoints de BI con token propio",

    # Principal distinto: el portal de cliente autentica ClientUser, no User, y ABAC
    # se evalúa sobre atributos de User. Su aislamiento es por cliente/proyecto.
    "/api/v1/portal":          "principal ClientUser, no User",
    "/api/v1/portal-ai":       "principal ClientUser, no User",

    # Colaboración: la membresía por canal/conversación ya es la fuente de verdad.
    # enforce_abac() además hace early-return para resource_type 'collaboration_*'.
    "/api/v1/collaboration":   "membresía por canal es la autoridad",

    # Sin usuario autenticado en la request: el middleware se salta la comprobación
    # cuando request.state.user es None, así que registrarlos no aportaría nada.
    "/api/v1/webhooks":        "webhook público firmado con HMAC",
    "/api/v1/forms":           "formularios públicos por token de capacidad",
    "/api/v1/scim":            "token de máquina SCIM (RFC 7644)",
    "/api/v1/ws":              "WebSocket, autenticado por ticket en el handshake",

    # Metadatos y stubs: no hay recurso de negocio que gobernar.
    "/api/v1/ui":              "etiquetas de UI",
    "/api/v1/translations":    "catálogo i18n",
    "/api/v1/labels":          "stub 501",
    "/api/v1/collaborative":   "stub 501",
    "/api/v1/docs":            "documentación OpenAPI",
    "/api/v1/redoc":           "documentación OpenAPI",
    "/api/v1/openapi.json":    "esquema OpenAPI",
    "/api/v2/version":         "descubrimiento de versión, público",
}
