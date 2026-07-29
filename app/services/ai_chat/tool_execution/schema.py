"""Definiciones de esquema de herramientas del agente (AGENT_TOOLS) y
clasificación de herramientas de escritura (WRITE_ACTION_TOOLS)."""

# Tools que mutan estado del sistema. Item #55: cuando ``auto_approve=False``,
# el agente debe pedir confirmación humana antes de ejecutarlas. La lista vive
# aquí (no en el endpoint) para que SSE + worker compartan la misma clasificación.
WRITE_ACTION_TOOLS = frozenset({
    "create_task",
    "update_task",
    "create_risk",
    "update_project_status",
    "update_ticket_status",
    "reassign_tickets",
    "send_notification",
})


AGENT_TOOLS = [
    # ── Read: Projects ────────────────────────────────────────────────────────
    {
        "name": "get_project_status",
        "description": "Get current status, tasks, budget and team of a specific project",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or partial name"},
            },
            "required": []
        }
    },
    {
        "name": "search_projects",
        "description": "Search and list projects by name, client, status or risk level. Use this to find projects matching criteria.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text search on name or client"},
                "status": {"type": "string", "enum": ["active","planning","completed","on_hold","all"]},
                "risk_level": {"type": "string", "enum": ["low","medium","high","critical"]},
            }
        }
    },
    {
        "name": "get_dashboard_summary",
        "description": "Get a full operational summary: active projects, overdue tasks, open tickets, hours logged this week",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_budget_status",
        "description": "Get budget, cost and financial details for a project or all active projects. Compares budget vs hours spent vs expenses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or name. Leave empty for all active projects."},
            }
        }
    },
    # ── Read: Risks ───────────────────────────────────────────────────────────
    {
        "name": "get_project_risks",
        "description": "Get all risks for a specific project with probability, impact, score and mitigation plan",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or partial name"},
                "status": {"type": "string", "enum": ["identified","analyzing","mitigating","monitoring","closed","materialized","all"], "description": "Filter by risk status. Default: all open (not closed)"},
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "get_all_risks",
        "description": "Get all risks across ALL projects. Essential for cross-project risk reports and executive summaries. Can filter by impact severity or status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "impact": {"type": "string", "enum": ["negligible","minor","moderate","major","critical"], "description": "Filter by impact level"},
                "status": {"type": "string", "description": "Filter by risk status (e.g. identified, mitigating). Default: active risks only (not closed)."},
                "probability": {"type": "string", "enum": ["very_low","low","medium","high","very_high"]},
                "limit": {"type": "integer", "default": 50},
            }
        }
    },
    # ── Read: Tasks ──────────────────────────────────────────────────────────
    {
        "name": "get_overdue_tasks",
        "description": "Get all overdue tasks optionally filtered by project or assignee",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            }
        }
    },
    # ── Read: Tickets ─────────────────────────────────────────────────────────
    {
        "name": "get_open_tickets",
        "description": "Get open service desk tickets filtered by priority or assignee",
        "input_schema": {
            "type": "object",
            "properties": {
                "priority": {"type": "string"},
                "assignee_id": {"type": "string"},
                "limit": {"type": "integer", "default": 15},
            }
        }
    },
    # ── Read: Milestones ──────────────────────────────────────────────────────
    {
        "name": "get_milestones",
        "description": "Get milestones and their billing/completion status. Can query a single project or all projects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or partial name. Leave empty for all projects."},
                "only_pending": {"type": "boolean", "description": "If true, return only non-completed milestones"},
            }
        }
    },
    # ── Read: Expenses ────────────────────────────────────────────────────────
    {
        "name": "get_expenses",
        "description": "Get expenses for one or all projects. Useful for budget analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or name. Leave empty for all."},
                "status": {"type": "string", "enum": ["pending","approved","rejected","all"]},
                "limit": {"type": "integer", "default": 30},
            }
        }
    },
    # ── Read: OKRs ────────────────────────────────────────────────────────────
    {
        "name": "get_okrs",
        "description": "Get OKRs (objectives and key results) with their progress. Can filter by status or year.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft","active","completed","cancelled","all"]},
                "year": {"type": "integer", "description": "Filter by year (default: current year)"},
            }
        }
    },
    # ── Read: Change Requests ─────────────────────────────────────────────────
    {
        "name": "get_change_requests",
        "description": "Get change requests (CRs) for one or all projects. Shows status, impact and cost impact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or name. Leave empty for all projects."},
                "status": {"type": "string", "enum": ["draft","submitted","under_review","approved","rejected","implemented","all"]},
            }
        }
    },
    # ── Read: Contracts ───────────────────────────────────────────────────────
    {
        "name": "get_contracts",
        "description": "Get contracts info including value, status and expiry dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status (active, expired, etc.)"},
                "limit": {"type": "integer", "default": 20},
            }
        }
    },
    # ── Read: Deliverables ────────────────────────────────────────────────────
    {
        "name": "get_deliverables",
        "description": "Get deliverables and their completion status for one or all projects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or name. Leave empty for all."},
                "status": {"type": "string", "enum": ["pending","in_progress","in_review","done","rejected","all"]},
            }
        }
    },
    # ── Read: Sprints ─────────────────────────────────────────────────────────
    {
        "name": "get_sprints",
        "description": "Get sprints with their velocity and completion rate for one or all projects.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or name. Leave empty for all."},
                "only_active": {"type": "boolean", "description": "Return only active/current sprints"},
            }
        }
    },
    # ── Read: Alerts ──────────────────────────────────────────────────────────
    {
        "name": "get_alerts",
        "description": "Get active system alerts (budget exceeded, overload, overdue, etc.) optionally filtered by severity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["info","warning","critical"]},
                "project_id": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            }
        }
    },
    # ── Read: Resources ───────────────────────────────────────────────────────
    {
        "name": "get_resource_availability",
        "description": "Get availability and workload for team members this or next week",
        "input_schema": {
            "type": "object",
            "properties": {
                "week_offset": {"type": "integer", "default": 0, "description": "0=this week, 1=next week"},
            }
        }
    },
    {
        "name": "get_users_list",
        "description": "Get the full list of users with their roles, department and hourly rate",
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "Filter by role (admin, pm, developer, etc.)"},
                "active_only": {"type": "boolean", "default": True},
            }
        }
    },
    # ── Write: Tasks ──────────────────────────────────────────────────────────
    {
        "name": "create_task",
        "description": "Create a new task in a project",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "title": {"type": "string"},
                "assignee_name": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                "estimated_hours": {"type": "number"},
                "priority": {"type": "string", "enum": ["low","medium","high","critical"]},
            },
            "required": ["project_id", "title"]
        }
    },
    {
        "name": "update_task",
        "description": "Update an existing task: change status, priority, assignee or due date",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {"type": "string", "enum": ["todo","in_progress","in_review","done","blocked"]},
                "priority": {"type": "string", "enum": ["low","medium","high","critical"]},
                "assignee_name": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["task_id"]
        }
    },
    # ── Write: Risks ──────────────────────────────────────────────────────────
    {
        "name": "create_risk",
        "description": "Register a new risk on a project",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "probability": {"type": "string", "enum": ["very_low","low","medium","high","very_high"]},
                "impact": {"type": "string", "enum": ["negligible","minor","moderate","major","critical"]},
                "category": {"type": "string", "description": "technical | financial | schedule | resource | external"},
                "mitigation_plan": {"type": "string"},
            },
            "required": ["project_id", "title", "probability", "impact"]
        }
    },
    # ── Write: Project ────────────────────────────────────────────────────────
    {
        "name": "update_project_status",
        "description": "Change a project's status or risk level",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "status": {"type": "string", "enum": ["planning","active","on_hold","completed","cancelled"]},
                "risk_level": {"type": "string", "enum": ["low","medium","high","critical"]},
            },
            "required": ["project_id"]
        }
    },
    # ── Write: Tickets ────────────────────────────────────────────────────────
    {
        "name": "update_ticket_status",
        "description": "Update a service desk ticket status or assignee",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "status": {"type": "string", "enum": ["open","in_progress","resolved","closed"]},
                "assignee_name": {"type": "string"},
                "comment": {"type": "string"},
            },
            "required": ["ticket_id"]
        }
    },
    {
        "name": "reassign_tickets",
        "description": "Reassign multiple tickets from one agent to another",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_user_name": {"type": "string"},
                "to_user_name": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["from_user_name", "to_user_name"]
        }
    },
    # ── Read: Imputations ────────────────────────────────────────────────────
    {
        "name": "get_imputations",
        "description": "Get time entries (hours worked) by person, project or date range. Essential for analysing who worked on what, utilisation and cost by project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID or partial name"},
                "user_name": {"type": "string", "description": "Person name or partial"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "group_by": {"type": "string", "enum": ["user","project","day","week","month"], "description": "Aggregate hours by this dimension"},
                "limit": {"type": "integer", "default": 50},
            }
        }
    },
    # ── Read: Invoices ────────────────────────────────────────────────────────
    {
        "name": "get_invoices",
        "description": "Get client invoices with status, amounts and due dates. Useful for billing and cash-flow analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft","sent","paid","overdue","cancelled","all"]},
                "project_id": {"type": "string"},
                "client_name": {"type": "string"},
                "limit": {"type": "integer", "default": 30},
            }
        }
    },
    # ── Read: Profitability ───────────────────────────────────────────────────
    {
        "name": "get_profitability",
        "description": "Get project profitability: contract value vs cost (hours × rate) vs expenses. Gives gross margin per project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Specific project ID or name. Leave empty for all active projects."},
            }
        }
    },
    # ── Read: Pipeline / CRM ─────────────────────────────────────────────────
    {
        "name": "get_pipeline",
        "description": "Get sales pipeline opportunities with stage, probability, expected revenue and close date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "enum": ["lead","qualified","proposal","negotiation","won","lost","all"]},
                "limit": {"type": "integer", "default": 20},
            }
        }
    },
    # ── Read: Absences ────────────────────────────────────────────────────────
    {
        "name": "get_absences",
        "description": "Get team absences (vacation, sick leave, etc.) for a period. Useful for capacity planning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_name": {"type": "string"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "status": {"type": "string", "enum": ["pending","approved","rejected","all"]},
                "limit": {"type": "integer", "default": 30},
            }
        }
    },
    # ── Read: Timesheets ──────────────────────────────────────────────────────
    {
        "name": "get_timesheets",
        "description": "Get timesheet submission status by user and week. Identifies who has not submitted timesheets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["draft","submitted","approved","rejected","all"]},
                "user_name": {"type": "string"},
                "week_from": {"type": "string", "description": "Week start date YYYY-MM-DD"},
                "limit": {"type": "integer", "default": 30},
            }
        }
    },
    # ── Read: Clients ─────────────────────────────────────────────────────────
    {
        "name": "get_clients",
        "description": "Get client list with industry, status and linked projects/revenue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active","inactive","prospect","all"]},
                "query": {"type": "string", "description": "Text search on name or industry"},
                "limit": {"type": "integer", "default": 20},
            }
        }
    },
    # ── Read: Skills ──────────────────────────────────────────────────────────
    {
        "name": "get_skills",
        "description": "Get the skills matrix: who has what skill and at what level. Useful for resource allocation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {"type": "string", "description": "Search by skill name"},
                "user_name": {"type": "string", "description": "Filter by person"},
                "category": {"type": "string"},
            }
        }
    },
    # ── Read: Approvals ───────────────────────────────────────────────────────
    {
        "name": "get_approvals",
        "description": "Get pending approval requests (expenses, timesheets, documents, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending","approved","rejected","all"]},
                "limit": {"type": "integer", "default": 20},
            }
        }
    },
    # ── Universal search ──────────────────────────────────────────────────────
    {
        "name": "search_all",
        "description": "Universal cross-system search. Searches projects, tasks, tickets, risks, clients, users, invoices and opportunities simultaneously. Returns grouped results. Use this as a first step when the user asks about something and you are not sure which module it belongs to.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
                "limit_per_entity": {"type": "integer", "default": 5, "description": "Max results per entity type"},
            },
            "required": ["query"]
        }
    },
    # ── Write: Notifications ──────────────────────────────────────────────────
    {
        "name": "send_notification",
        "description": "Send an in-app notification to one or more users",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_names": {"type": "array", "items": {"type": "string"}},
                "message": {"type": "string"},
                "link": {"type": "string"},
            },
            "required": ["user_names", "message"]
        }
    },
    # ── Capacity plans ────────────────────────────────────────────────────────
    {
        "name": "get_capacity_plans",
        "description": "List capacity plans (planned hours per user per week). Use to understand planned workload distribution. Combine with get_resource_availability for utilisation vs plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_name": {"type": "string", "description": "Filter by user name (partial match)"},
                "project_id": {"type": "string"},
                "week_from": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "week_to":   {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "limit": {"type": "integer", "default": 40},
            }
        }
    },
    # ── Git activity ──────────────────────────────────────────────────────────
    {
        "name": "get_git_activity",
        "description": "Get recent pull requests and deployments linked to tasks or projects. Use to understand development activity and deployment health.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Filter by project id or name"},
                "status": {"type": "string", "enum": ["open","merged","closed","draft","all"], "default": "all"},
                "limit": {"type": "integer", "default": 20},
            }
        }
    },
]
