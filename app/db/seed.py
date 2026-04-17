"""
Seed script – populates the DB with complete realistic data for ALL modules.
Run: python -m app.db.seed
All field names verified against actual SQLAlchemy models.
"""
import sys
import os
import random
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import date, timedelta, datetime, timezone
import bcrypt

from app.db.session import SessionLocal
from app.db.base import Base
from app.db.session import engine
from app.core.config import settings

def get_password_hash(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def _risk_score(prob, impact):
    PROB = {"very_low":0.05,"low":0.2,"medium":0.5,"high":0.7,"very_high":0.9}
    IMP  = {"negligible":1,"minor":2,"moderate":3,"major":4,"critical":5}
    pv = prob.value if hasattr(prob,'value') else prob
    iv = impact.value if hasattr(impact,'value') else impact
    return round(PROB.get(pv,0.5)*IMP.get(iv,3),2)

def seed():
    # ── Imports ────────────────────────────────────────────────────────────────
    from app.models.user import User, UserRole
    from app.models.clients import Client, ClientStatus, ClientIndustry, ClientContact, ClientContactRole, ClientPortalConfig
    from app.models.project import Project, ProjectType, ProjectStatus
    from app.models.task import Task, TaskStatus, TaskPriority
    from app.models.imputation import Imputation
    from app.models.settings import AppSetting, Department, Holiday
    from app.models.financial import ProjectMilestone
    from app.models.pipeline import (
        Opportunity, OpportunityStage,
        Contract, WorkOrder, ContractType, ContractStatus,
        Risk, RiskProbability, RiskImpact, RiskStatus
    )
    from app.models.resources import (
        Skill, UserSkill, SkillLevel, SkillCategory,
        Absence, AbsenceType, AbsenceStatus,
        ChangeRequest, ChangeRequestStatus, ChangeRequestImpact,
        Deliverable, DeliverableStatus
    )
    from app.models.advanced_config import (
        TaskType, AlertConfig, NumberingSequence, VacationPolicy,
        UserVacationBalance
    )

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    print("Seeding Clarive database...")
    today = date.today()

    # ── AppSettings ────────────────────────────────────────────────────────────
    for key, value in {
        "company_name":"Consultora Nexus SL","currency":settings.DEFAULT_CURRENCY,
        "timezone":settings.DEFAULT_TIMEZONE,"language":settings.DEFAULT_LANGUAGE,
        "work_hours_per_day":str(settings.DEFAULT_WORKING_HOURS_PER_DAY),"work_days_per_week":"5",
        "budget_alert_threshold":"85","overload_threshold":"100"
    }.items():
        if not db.query(AppSetting).filter(AppSetting.key==key).first():
            db.add(AppSetting(key=key, value=value))
    db.commit()

    # ── Departments ────────────────────────────────────────────────────────────
    for d in ["Backend","Frontend","IA / Data","Infraestructura","Diseno UX","Gestion","RRHH","Ventas"]:
        if not db.query(Department).filter(Department.name==d).first():
            db.add(Department(name=d))
    db.commit()

    # ── Holidays ───────────────────────────────────────────────────────────────
    for d_str, name in [
        ("2025-01-01","Ano Nuevo"),("2025-01-06","Reyes"),
        ("2025-04-17","Jueves Santo"),("2025-04-18","Viernes Santo"),
        ("2025-05-01","Dia del Trabajo"),("2025-08-15","Asuncion"),
        ("2025-10-12","Fiesta Nacional"),("2025-12-25","Navidad"),
        ("2026-01-01","Ano Nuevo"),("2026-01-06","Reyes"),
        ("2026-04-02","Jueves Santo"),("2026-04-03","Viernes Santo"),
        ("2026-05-01","Dia del Trabajo"),("2026-08-15","Asuncion"),
        ("2026-10-12","Fiesta Nacional"),("2026-12-25","Navidad"),
    ]:
        d = date.fromisoformat(d_str)
        if not db.query(Holiday).filter(Holiday.date==d).first():
            db.add(Holiday(date=d, name=name, type="national"))
    db.commit()

    from app.models.mfa import Organization

    # ── Default Organization ────────────────────────────────────────────────────
    org = db.query(Organization).filter(Organization.slug == "nexus-demo").first()
    if not org:
        org = Organization(
            name="Consultora Nexus SL",
            slug="nexus-demo",
            plan="enterprise",
            is_active=True,
            max_users=200,
            max_projects=500,
            admin_email="admin@company.com",
            timezone=settings.DEFAULT_TIMEZONE,
            locale=settings.DEFAULT_LANGUAGE,
        )
        db.add(org)
        db.flush()
        print(f"  Org: {org.name} (id={org.id})")
    db.commit()

    # ── Users ──────────────────────────────────────────────────────────────────
    import json, os
    users_data_path = os.getenv("SEED_USERS_DATA_PATH", "seed_users_data.json")
    if os.path.exists(users_data_path):
        with open(users_data_path, "r") as f:
            users_data = json.load(f)
    else:
        users_data = [
            dict(username="admin",    email=settings.SUPERADMIN_EMAIL,    full_name="Admin Sistema",  role=UserRole.admin,    department="Direccion",      job_title="CTO",               hourly_rate=None,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS, is_superadmin=True),
            dict(username="ana.torres",email="ana.torres@company.com",full_name="Ana Torres",   role=UserRole.pm,       department="Backend",        job_title="Tech Lead PM",      hourly_rate=85.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="luis.vega", email="luis.vega@company.com", full_name="Luis Vega",    role=UserRole.employee, department="Backend",        job_title="Senior Developer",  hourly_rate=70.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="marta.gil", email="marta.gil@company.com", full_name="Marta Gil",    role=UserRole.employee, department="IA / Data",      job_title="Data Scientist",    hourly_rate=80.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="carlos.ruiz",email="carlos.ruiz@company.com",full_name="Carlos Ruiz",role=UserRole.pm,      department="Gestion",        job_title="Project Manager",   hourly_rate=75.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="sara.lope", email="sara.lope@company.com", full_name="Sara Lopez",   role=UserRole.employee, department="Infraestructura",job_title="DevOps Engineer",   hourly_rate=72.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="diego.mora",email="diego.mora@company.com",full_name="Diego Mora",   role=UserRole.employee, department="Frontend",       job_title="Frontend Developer",hourly_rate=55.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="elena.pardo",email="elena.pardo@company.com",full_name="Elena Pardo",role=UserRole.employee,department="Diseno UX",      job_title="UX Designer",       hourly_rate=65.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="rrhh",      email="rrhh@company.com",      full_name="RRHH Manager", role=UserRole.hr,       department="RRHH",           job_title="HR Manager",        hourly_rate=None,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
        ]
    users = {}
    seed_pwd = settings.DEFAULT_USER_PASSWORD
    print(f"\n  ⚠️  Seed user password: {seed_pwd}")
    print("     Set DEFAULT_USER_PASSWORD env var to override.\n")
    for ud in users_data:
        u = db.query(User).filter(User.username==ud["username"]).first()
        if not u:
            # Superadmins span all orgs; everyone else belongs to the default org.
            org_id = None if ud.get("is_superadmin") else org.id
            u = User(**ud, hashed_password=get_password_hash(seed_pwd),
                     organization_id=org_id)
            db.add(u); db.flush()
            print(f"  User: {ud['full_name']}")
        elif not u.organization_id and not u.is_superadmin:
            # Back-fill existing users that missed the org assignment.
            u.organization_id = org.id
        users[ud["username"]] = u
    db.commit()

    # ── Skills catalog ─────────────────────────────────────────────────────────
    skills_data = [
        ("Python",SkillCategory.technical),("FastAPI",SkillCategory.technical),
        ("Django",SkillCategory.technical),("PostgreSQL",SkillCategory.technical),
        ("MongoDB",SkillCategory.technical),("Redis",SkillCategory.technical),
        ("React",SkillCategory.technical),("TypeScript",SkillCategory.technical),
        ("Vue.js",SkillCategory.technical),("Node.js",SkillCategory.technical),
        ("Docker",SkillCategory.technical),("Kubernetes",SkillCategory.technical),
        ("AWS",SkillCategory.technical),("Terraform",SkillCategory.technical),
        ("Machine Learning",SkillCategory.technical),("Data Analysis",SkillCategory.technical),
        ("Power BI",SkillCategory.technical),("Pandas",SkillCategory.technical),
        ("Figma",SkillCategory.soft),("UX Research",SkillCategory.soft),
        ("Scrum",SkillCategory.soft),("JIRA",SkillCategory.soft),
        ("Project Management",SkillCategory.soft),("Stakeholder Management",SkillCategory.soft),
        ("Git",SkillCategory.technical),("Linux",SkillCategory.technical),
        ("CI/CD",SkillCategory.technical),("Testing",SkillCategory.technical),
    ]
    skills = {}
    for name, cat in skills_data:
        s = db.query(Skill).filter(Skill.name==name).first()
        if not s:
            s = Skill(name=name, category=cat, is_active=True)
            db.add(s); db.flush()
        skills[name] = s
    db.commit()

    # ── User skills ────────────────────────────────────────────────────────────
    # Fields: user_id, skill_id, level, years_experience, certified
    user_skill_map = {
        "luis.vega":   [("Python",SkillLevel.expert),("FastAPI",SkillLevel.expert),("PostgreSQL",SkillLevel.advanced),("Docker",SkillLevel.intermediate),("Git",SkillLevel.expert),("Testing",SkillLevel.advanced)],
        "marta.gil":   [("Python",SkillLevel.expert),("Machine Learning",SkillLevel.expert),("Data Analysis",SkillLevel.expert),("Pandas",SkillLevel.expert),("Power BI",SkillLevel.advanced),("PostgreSQL",SkillLevel.intermediate)],
        "sara.lope":   [("Docker",SkillLevel.expert),("Kubernetes",SkillLevel.advanced),("AWS",SkillLevel.advanced),("Terraform",SkillLevel.intermediate),("Linux",SkillLevel.expert),("CI/CD",SkillLevel.expert)],
        "diego.mora":  [("React",SkillLevel.expert),("TypeScript",SkillLevel.advanced),("Node.js",SkillLevel.intermediate),("Git",SkillLevel.advanced),("Testing",SkillLevel.intermediate)],
        "elena.pardo": [("Figma",SkillLevel.expert),("UX Research",SkillLevel.expert),("React",SkillLevel.intermediate),("TypeScript",SkillLevel.basic)],
        "ana.torres":  [("Python",SkillLevel.advanced),("Scrum",SkillLevel.expert),("Project Management",SkillLevel.expert),("JIRA",SkillLevel.expert),("Stakeholder Management",SkillLevel.expert),("FastAPI",SkillLevel.intermediate)],
        "carlos.ruiz": [("Project Management",SkillLevel.expert),("Scrum",SkillLevel.advanced),("JIRA",SkillLevel.advanced),("Stakeholder Management",SkillLevel.expert)],
    }
    for uname, skill_list in user_skill_map.items():
        u = users.get(uname)
        if not u: continue
        for sname, level in skill_list:
            s = skills.get(sname)
            if not s: continue
            if not db.query(UserSkill).filter(UserSkill.user_id==u.id, UserSkill.skill_id==s.id).first():
                db.add(UserSkill(user_id=u.id, skill_id=s.id, level=level,
                                 years_experience=random.randint(1,8),
                                 certified=random.choice([True,False,False])))
    db.commit()

    # ── Numbering sequences ────────────────────────────────────────────────────
    # Fields: entity, prefix, padding, current_value
    NUMBERING_SEQUENCES = settings.NUMBERING_SEQUENCES if hasattr(settings, "NUMBERING_SEQUENCES") else [
        ("project","PRJ",4),("task","TSK",4),("contract","CNT",4),
        ("opportunity","OPP",4),("risk","RSK",4),
        ("change_request","CR",4),("deliverable","DEL",4)
    ]
    for entity, prefix, padding in NUMBERING_SEQUENCES:
        if not db.query(NumberingSequence).filter(NumberingSequence.entity==entity).first():
            db.add(NumberingSequence(entity=entity, prefix=prefix, padding=padding, current_value=0))
    db.commit()

    # ── Task types ─────────────────────────────────────────────────────────────
    # Fields: name, value, color, icon, is_active
    TASK_TYPES = settings.TASK_TYPES if hasattr(settings, "TASK_TYPES") else [
        ("Feature","#7c3aed","✦"),("Bug","#ff4757","⚠"),
        ("Improvement","#00d4ff","↑"),("Documentation","#ffb800","📄"),
        ("Research","#00c896","🔍"),("DevOps","#ff6b35","⚙")
    ]
    for tname, color, icon in TASK_TYPES:
        if not db.query(TaskType).filter(TaskType.name==tname).first():
            db.add(TaskType(name=tname, value=tname.lower(), color=color, icon=icon, is_active=True))
    db.commit()

    # ── Alert configs ──────────────────────────────────────────────────────────
    # Fields: alert_type, label, is_enabled, threshold_value, notify_admin, notify_pm
    ALERT_CONFIGS = settings.ALERT_CONFIGS if hasattr(settings, "ALERT_CONFIGS") else [
        ("budget_alert","Alerta presupuesto >85%",85.0),
        ("overload_alert","Sobrecarga equipo >100%",100.0),
        ("deadline_alert","Proyecto vence en 7 dias",7.0)
    ]
    for alert_type, label, threshold in ALERT_CONFIGS:
        if not db.query(AlertConfig).filter(AlertConfig.alert_type==alert_type).first():
            db.add(AlertConfig(alert_type=alert_type, label=label, is_enabled=True,
                               threshold_value=threshold, notify_admin=True, notify_pm=True))
    db.commit()

    # ── Vacation policy ────────────────────────────────────────────────────────
    # Fields: name, days_per_year, carries_over, max_carryover_days, is_default, is_active
    if not db.query(VacationPolicy).first():
        db.add(VacationPolicy(name="Politica estandar", days_per_year=settings.DEFAULT_VACATION_DAYS_PER_YEAR,
                              carries_over=True, max_carryover_days=5,
                              is_default=True, is_active=True))
        db.commit()
    vp = db.query(VacationPolicy).first()

    # Fields: user_id, year, policy_id, days_entitled, days_taken, days_pending
    for uname in getattr(settings, "VACATION_USERS", ["ana.torres","luis.vega","marta.gil","carlos.ruiz","sara.lope","diego.mora","elena.pardo"]):
        u = users.get(uname)
        if u and not db.query(UserVacationBalance).filter(UserVacationBalance.user_id==u.id).first():
            days_taken_val = random.choice([0,2,3,5])
            db.add(UserVacationBalance(user_id=u.id, policy_id=vp.id, year=2026,
                                       days_entitled=settings.DEFAULT_VACATION_DAYS_PER_YEAR,
                                       days_taken=days_taken_val,
                                       days_pending=settings.DEFAULT_VACATION_DAYS_PER_YEAR - days_taken_val))
    db.commit()

    # ── Clients ────────────────────────────────────────────────────────────────
    # Fields: name, short_name, industry, status, contact_name, contact_email,
    #         contact_phone, contact_role, city, country, payment_terms,
    #         currency, account_manager_id, created_by
        clients_data_path = os.getenv("SEED_CLIENTS_DATA_PATH", "seed_clients_data.json")
        if os.path.exists(clients_data_path):
            with open(clients_data_path, "r") as f:
                clients_data = json.load(f)
            # Map usernames to user IDs for account_manager_id
            for c in clients_data:
                if "account_manager_username" in c:
                    c["account_manager_id"] = users.get(c["account_manager_username"]).id if users.get(c["account_manager_username"]) else None
        else:
            clients_data = getattr(settings, "CLIENTS_DATA", [
               dict(name="Acme Industries SA",  short_name="Acme",       industry=ClientIndustry.technology,    status=ClientStatus.active,
                   contact_name="Pedro Garcia",    contact_email="pedro.garcia@acme.com",   contact_phone="+34 91 100 2000",
                   contact_role="Director de Tecnologia",  city="Madrid",    country="ES",
                   payment_terms="30 dias",  currency=settings.DEFAULT_CURRENCY,
                   account_manager_id=users["carlos.ruiz"].id),
               dict(name="TechStart SL",        short_name="TechStart",  industry=ClientIndustry.technology,    status=ClientStatus.active,
                   contact_name="Laura Mora",      contact_email="laura@techstart.io",      contact_phone="+34 93 200 3000",
                   contact_role="CEO",             city="Barcelona",  country="ES",
                   payment_terms="15 dias",  currency=settings.DEFAULT_CURRENCY,
                   account_manager_id=users["carlos.ruiz"].id),
            ])
        dict(name="RetailCorp SA",       short_name="RetailCorp", industry=ClientIndustry.retail,        status=ClientStatus.active,
             contact_name="Maria Blanco",    contact_email="m.blanco@retailcorp.es",  contact_phone="+34 95 300 4000",
             contact_role="Directora de Compras",    city="Sevilla",   country="ES",
             payment_terms="45 dias",  currency=settings.DEFAULT_CURRENCY,
             account_manager_id=users["ana.torres"].id),
        dict(name="Hospital X",          short_name="HospX",      industry=ClientIndustry.healthcare,    status=ClientStatus.active,
             contact_name="Dr. Javier Sanz", contact_email="javier.sanz@hospitalx.es", contact_phone="+34 96 400 5000",
             contact_role="Director TI",    city="Valencia",  country="ES",
             payment_terms="60 dias",  currency=settings.DEFAULT_CURRENCY,
             account_manager_id=users["carlos.ruiz"].id),
        dict(name="FinanceCo SA",        short_name="FinanceCo",  industry=ClientIndustry.finance,       status=ClientStatus.prospect,
             contact_name="Isabel Navarro",  contact_email="i.navarro@financeco.es",  contact_phone="+34 91 500 6000",
             contact_role="CFO",             city="Madrid",    country="ES",
             payment_terms="30 dias",  currency=settings.DEFAULT_CURRENCY,
             account_manager_id=users["ana.torres"].id),
        dict(name="FabriTech SL",        short_name="FabriTech",  industry=ClientIndustry.manufacturing, status=ClientStatus.prospect,
             contact_name="Ramon Ferrer",    contact_email="r.ferrer@fabritech.es",   contact_phone="+34 93 600 7000",
             contact_role="Director de Operaciones", city="Barcelona", country="ES",
             payment_terms="30 dias",  currency=settings.DEFAULT_CURRENCY,
             account_manager_id=users["carlos.ruiz"].id),
        dict(name="StartupX",            short_name="StartupX",   industry=ClientIndustry.technology,    status=ClientStatus.active,
             contact_name="Pablo Vidal",     contact_email="pablo@startupx.io",       contact_phone="+34 91 700 8000",
             contact_role="CTO",             city="Madrid",    country="ES",
             payment_terms="inmediato",  currency=settings.DEFAULT_CURRENCY,
             account_manager_id=users["ana.torres"].id),
        dict(name="PymesGroup",          short_name="PymesGroup", industry=ClientIndustry.consulting,    status=ClientStatus.churned,
             contact_name="Teresa Gil",      contact_email="teresa.gil@pymesgroup.es", contact_phone="+34 91 800 9000",
             contact_role="Gerente",         city="Madrid",    country="ES",
             payment_terms="30 dias",  currency=settings.DEFAULT_CURRENCY,
             account_manager_id=users["carlos.ruiz"].id),
    ]
    clients = {}
    for cd in clients_data:
        c = db.query(Client).filter(Client.name == cd["name"]).first()
        if not c:
            c = Client(**cd, created_by=users["admin"].id)
            db.add(c)
            db.flush()
            print(f"  Client: {cd['name']}")
        clients[cd["name"]] = c
    db.commit()
    print(f"  {len(clients)} clientes disponibles")

    # ── Projects ───────────────────────────────────────────────────────────────
    # Fields: code, name, description, project_type, status, client_name,
    #         is_billable, billing_type, budget_hours, budget_amount,
    #         start_date, end_date_planned, pm_id
    if db.query(Project).count() == 0:
        projs_data = [
            dict(code="PRJ-0001",name="Portal Gestion Interno",description="Desarrollo del portal de gestion interna para RRHH y direccion.",project_type=ProjectType.internal,status=ProjectStatus.active,start_date=today-timedelta(days=60),end_date_planned=today+timedelta(days=90),budget_amount=95000,budget_hours=800,pm_id=users["ana.torres"].id,is_billable=False),
            dict(code="PRJ-0002",name="ERP Acme Industries",description="Implantacion de modulo ERP de contabilidad para cliente Acme Industries.",project_type=ProjectType.consulting,status=ProjectStatus.active,start_date=today-timedelta(days=30),end_date_planned=today+timedelta(days=120),budget_amount=95000,budget_hours=700,pm_id=users["carlos.ruiz"].id,client_name="Acme Industries SA",client_id=clients["Acme Industries SA"].id,is_billable=True,billing_type="fixed_price"),
            dict(code="PRJ-0003",name="Dashboard Analytics BI",description="Cuadro de mando ejecutivo con Power BI para direccion.",project_type=ProjectType.internal,status=ProjectStatus.active,start_date=today-timedelta(days=20),end_date_planned=today+timedelta(days=40),budget_amount=28000,budget_hours=220,pm_id=users["ana.torres"].id,is_billable=False),
            dict(code="PRJ-0004",name="App Movil TechStart",description="App React Native para startup TechStart.",project_type=ProjectType.consulting,status=ProjectStatus.paused,start_date=today-timedelta(days=90),end_date_planned=today+timedelta(days=30),budget_amount=55000,budget_hours=500,pm_id=users["carlos.ruiz"].id,client_name="TechStart SL",client_id=clients["TechStart SL"].id,is_billable=True,billing_type="time_material"),
            dict(code="PRJ-0005",name="Migracion Cloud AWS",description="Migracion de infraestructura on-premise a AWS.",project_type=ProjectType.internal,status=ProjectStatus.planning,start_date=today+timedelta(days=15),end_date_planned=today+timedelta(days=180),budget_amount=70000,budget_hours=600,pm_id=users["ana.torres"].id,is_billable=False),
        ]
        projects = {}
        for pd in projs_data:
            p = Project(**pd, organization_id=org.id)
            db.add(p); db.flush()
            projects[pd["code"]] = p
        db.commit()
        print(f"  {len(projects)} proyectos creados")
    else:
        projects = {p.code: p for p in db.query(Project).all()}
        # Back-fill projects missing organization_id.
        for p in projects.values():
            if not p.organization_id:
                p.organization_id = org.id
        db.commit()

    # ── Tasks ──────────────────────────────────────────────────────────────────
    # Fields: code, title, project_id, status, priority, estimated_hours, assignee_id
    if db.query(Task).count() == 0:
        tasks_data = [
            dict(code="TSK-0001",title="Diseno arquitectura microservicios",project_id=projects["PRJ-0001"].id,status=TaskStatus.done,priority=TaskPriority.high,estimated_hours=24,assignee_id=users["luis.vega"].id),
            dict(code="TSK-0002",title="Implementar autenticacion JWT",project_id=projects["PRJ-0001"].id,status=TaskStatus.done,priority=TaskPriority.high,estimated_hours=16,assignee_id=users["luis.vega"].id),
            dict(code="TSK-0003",title="Modulo de reportes con filtros",project_id=projects["PRJ-0001"].id,status=TaskStatus.in_progress,priority=TaskPriority.medium,estimated_hours=32,assignee_id=users["marta.gil"].id),
            dict(code="TSK-0004",title="Diseno UX portal empleados",project_id=projects["PRJ-0001"].id,status=TaskStatus.in_progress,priority=TaskPriority.medium,estimated_hours=20,assignee_id=users["elena.pardo"].id),
            dict(code="TSK-0005",title="API modulo contabilidad ERP",project_id=projects["PRJ-0002"].id,status=TaskStatus.in_progress,priority=TaskPriority.high,estimated_hours=40,assignee_id=users["luis.vega"].id),
            dict(code="TSK-0006",title="Integracion ERP con BBDD legacy",project_id=projects["PRJ-0002"].id,status=TaskStatus.todo,priority=TaskPriority.high,estimated_hours=24,assignee_id=users["sara.lope"].id),
            dict(code="TSK-0007",title="Frontend React modulos ERP",project_id=projects["PRJ-0002"].id,status=TaskStatus.in_progress,priority=TaskPriority.medium,estimated_hours=60,assignee_id=users["diego.mora"].id),
            dict(code="TSK-0008",title="Pipeline datos Power BI",project_id=projects["PRJ-0003"].id,status=TaskStatus.in_progress,priority=TaskPriority.high,estimated_hours=28,assignee_id=users["marta.gil"].id),
            dict(code="TSK-0009",title="Dashboard ejecutivo ventas",project_id=projects["PRJ-0003"].id,status=TaskStatus.todo,priority=TaskPriority.medium,estimated_hours=20,assignee_id=users["marta.gil"].id),
            dict(code="TSK-0010",title="Setup infraestructura CI/CD",project_id=projects["PRJ-0005"].id,status=TaskStatus.todo,priority=TaskPriority.high,estimated_hours=32,assignee_id=users["sara.lope"].id),
            dict(code="TSK-0011",title="Analisis coste migracion cloud",project_id=projects["PRJ-0005"].id,status=TaskStatus.todo,priority=TaskPriority.low,estimated_hours=16,assignee_id=users["ana.torres"].id),
            dict(code="TSK-0012",title="Pantalla login y onboarding app",project_id=projects["PRJ-0004"].id,status=TaskStatus.done,priority=TaskPriority.high,estimated_hours=24,assignee_id=users["diego.mora"].id),
        ]
        for td in tasks_data:
            db.add(Task(**td))
        db.commit()
        print(f"  {len(tasks_data)} tareas creadas")

    # ── Imputations ────────────────────────────────────────────────────────────
    if db.query(Imputation).count() == 0:
        worker_proj = [
            (users["luis.vega"],   projects["PRJ-0001"], 6.0),
            (users["luis.vega"],   projects["PRJ-0002"], 6.0),
            (users["marta.gil"],   projects["PRJ-0001"], 4.0),
            (users["marta.gil"],   projects["PRJ-0003"], 5.0),
            (users["sara.lope"],   projects["PRJ-0002"], 5.0),
            (users["diego.mora"],  projects["PRJ-0002"], 7.0),
            (users["elena.pardo"], projects["PRJ-0001"], 5.0),
            (users["ana.torres"],  projects["PRJ-0001"], 3.0),
            (users["ana.torres"],  projects["PRJ-0002"], 3.0),
        ]
        for d_offset in range(45, 0, -1):
            d = today - timedelta(days=d_offset)
            if d.weekday() >= 5: continue
            for u, p, hrs in worker_proj:
                if random.random() < 0.8:
                    actual_hours = round(hrs * random.uniform(0.7,1.0), 1)
                    db.add(Imputation(
                        user_id=u.id, project_id=p.id,
                        date=d, hours=actual_hours,
                        description="Desarrollo",
                        is_billable=p.is_billable,
                        hourly_rate_snapshot=u.hourly_rate or 0,
                        cost_amount=round((u.hourly_rate or 0)*actual_hours, 2)
                    ))
        db.commit()
        print("  Imputaciones creadas")

    # ── Absences ───────────────────────────────────────────────────────────────
    # Fields: user_id, type, status, start_date, end_date, reason
    if db.query(Absence).count() == 0:
        db.add(Absence(user_id=users["luis.vega"].id,  type=AbsenceType.vacation, start_date=today+timedelta(days=14), end_date=today+timedelta(days=21), status=AbsenceStatus.approved, reason="Vacaciones verano"))
        db.add(Absence(user_id=users["marta.gil"].id,  type=AbsenceType.sick,     start_date=today-timedelta(days=5),  end_date=today-timedelta(days=3),  status=AbsenceStatus.approved, reason="Baja medica"))
        db.add(Absence(user_id=users["diego.mora"].id, type=AbsenceType.vacation, start_date=today+timedelta(days=30), end_date=today+timedelta(days=37), status=AbsenceStatus.pending))
        db.add(Absence(user_id=users["elena.pardo"].id,type=AbsenceType.personal, start_date=today+timedelta(days=7),  end_date=today+timedelta(days=7),  status=AbsenceStatus.approved))
        db.add(Absence(user_id=users["sara.lope"].id,  type=AbsenceType.vacation, start_date=today+timedelta(days=60), end_date=today+timedelta(days=74), status=AbsenceStatus.pending))
        db.commit()
        print("  Ausencias creadas")

    # ── Pipeline – Opportunities ───────────────────────────────────────────────
    # Fields: code, name, client_name, expected_revenue, stage, probability,
    #         expected_close_date, owner_id, description
    if db.query(Opportunity).count() == 0:
        opps = [
            dict(code="OPP-0001",name="Portal B2B RetailCorp",    client_name="RetailCorp SA",  client_id=clients["RetailCorp SA"].id,  expected_revenue=180000,stage=OpportunityStage.proposal,    probability=60, expected_close_date=today+timedelta(days=30), owner_id=users["carlos.ruiz"].id,description="Portal de gestion de proveedores B2B"),
            dict(code="OPP-0002",name="Sistema RRHH HospitalX",   client_name="Hospital X",     client_id=clients["Hospital X"].id,     expected_revenue=95000, stage=OpportunityStage.negotiation,  probability=80, expected_close_date=today+timedelta(days=15), owner_id=users["carlos.ruiz"].id),
            dict(code="OPP-0003",name="App Analytics FinanceCo",  client_name="FinanceCo SA",   client_id=clients["FinanceCo SA"].id,   expected_revenue=220000,stage=OpportunityStage.qualification, probability=35, expected_close_date=today+timedelta(days=60), owner_id=users["ana.torres"].id),
            dict(code="OPP-0004",name="Plataforma IoT Fab",       client_name="FabriTech SL",   client_id=clients["FabriTech SL"].id,   expected_revenue=310000,stage=OpportunityStage.lead,          probability=20, expected_close_date=today+timedelta(days=90), owner_id=users["carlos.ruiz"].id),
            dict(code="OPP-0005",name="Migracion cloud StartupX", client_name="StartupX",       client_id=clients["StartupX"].id,       expected_revenue=45000, stage=OpportunityStage.won,           probability=100,expected_close_date=today-timedelta(days=5),  owner_id=users["ana.torres"].id),
            dict(code="OPP-0006",name="CRM PymesGroup",           client_name="PymesGroup",     client_id=clients["PymesGroup"].id,     expected_revenue=78000, stage=OpportunityStage.lost,          probability=0,  expected_close_date=today-timedelta(days=20), owner_id=users["carlos.ruiz"].id),
        ]
        for od in opps:
            db.add(Opportunity(**od))
        db.commit()
        print("  Oportunidades creadas")

    # ── Contracts ──────────────────────────────────────────────────────────────
    # Fields: code, name, project_id, client_name, contract_type, status,
    #         total_amount, monthly_retainer, start_date, end_date, signed_date
    # WorkOrder fields: code, contract_id, name, amount, hours, start_date, end_date
    if db.query(Contract).count() == 0:
        c1 = Contract(code="CNT-0001",name="Contrato ERP Acme Industries",project_id=projects["PRJ-0002"].id,client_name="Acme Industries SA",client_id=clients["Acme Industries SA"].id,contract_type=ContractType.fixed_price,status=ContractStatus.active,start_date=today-timedelta(days=30),end_date=today+timedelta(days=120),total_amount=95000,signed_date=today-timedelta(days=35))
        c2 = Contract(code="CNT-0002",name="Soporte y mantenimiento TechStart",project_id=projects["PRJ-0004"].id,client_name="TechStart SL",client_id=clients["TechStart SL"].id,contract_type=ContractType.time_material,status=ContractStatus.active,start_date=today-timedelta(days=90),end_date=today+timedelta(days=90),total_amount=36000,monthly_retainer=3000,signed_date=today-timedelta(days=92))
        c3 = Contract(code="CNT-0003",name="Proyecto Data Analytics RetailCorp",project_id=projects["PRJ-0003"].id,client_name="RetailCorp SA",client_id=clients["RetailCorp SA"].id,contract_type=ContractType.fixed_price,status=ContractStatus.draft,start_date=today+timedelta(days=15),end_date=today+timedelta(days=150),total_amount=180000)
        db.add_all([c1,c2,c3]); db.flush()
        db.add(WorkOrder(code="OT-0001",contract_id=c1.id,name="Fase 1 - Analisis y diseno",  amount=23750,hours=190,start_date=today-timedelta(days=30),end_date=today-timedelta(days=10)))
        db.add(WorkOrder(code="OT-0002",contract_id=c1.id,name="Fase 2 - Desarrollo API",     amount=33250,hours=270,start_date=today-timedelta(days=10),end_date=today+timedelta(days=40)))
        db.add(WorkOrder(code="OT-0003",contract_id=c2.id,name="Soporte Mensual Marzo",        amount=3000, hours=40, start_date=today,                   end_date=today+timedelta(days=31)))
        db.commit()
        print("  Contratos creados")

    # ── Risks ──────────────────────────────────────────────────────────────────
    # Fields: code, project_id, title, description, probability, impact,
    #         risk_score, status, mitigation_plan, owner_id
    if db.query(Risk).count() == 0:
        risks = [
            dict(code="RSK-0001",title="Retraso entrega API legacy",    description="La integracion con el sistema legacy puede causar retrasos.", project_id=projects["PRJ-0002"].id,probability=RiskProbability.high,    impact=RiskImpact.major,    status=RiskStatus.identified,owner_id=users["luis.vega"].id,  mitigation_plan="Plan de contingencia con API mock"),
            dict(code="RSK-0002",title="Rotacion de personal clave",    description="Riesgo de baja del Tech Lead en proyecto critico.",           project_id=projects["PRJ-0002"].id,probability=RiskProbability.medium,  impact=RiskImpact.critical, status=RiskStatus.mitigating, owner_id=users["ana.torres"].id, mitigation_plan="Documentacion tecnica completa y pair programming"),
            dict(code="RSK-0003",title="Cambio de requisitos cliente",  description="El cliente puede solicitar cambios mayores en alcance.",       project_id=projects["PRJ-0001"].id,probability=RiskProbability.medium,  impact=RiskImpact.moderate, status=RiskStatus.identified,owner_id=users["carlos.ruiz"].id,mitigation_plan="Change control process establecido"),
            dict(code="RSK-0004",title="Deuda tecnica acumulada",       description="La velocidad del desarrollo puede generar deuda tecnica.",     project_id=projects["PRJ-0001"].id,probability=RiskProbability.low,     impact=RiskImpact.minor,    status=RiskStatus.monitoring,owner_id=users["luis.vega"].id),
            dict(code="RSK-0005",title="Caida proveedores cloud",       description="AWS puede tener incidencias que afecten produccion.",          project_id=projects["PRJ-0005"].id,probability=RiskProbability.very_low,impact=RiskImpact.critical, status=RiskStatus.identified,owner_id=users["sara.lope"].id,  mitigation_plan="Multi-region deployment y backup automatico"),
        ]
        for rd in risks:
            rd["risk_score"] = _risk_score(rd["probability"], rd["impact"])
            db.add(Risk(**rd))
        db.commit()
        print("  Riesgos creados")

    # ── Change Requests ────────────────────────────────────────────────────────
    # Fields: code, project_id, title, description, status, impact,
    #         cost_impact, requested_by, approved_by
    if db.query(ChangeRequest).count() == 0:
        db.add(ChangeRequest(code="CR-0001",title="Anadir modulo facturacion automatica",description="Integrar generacion automatica de facturas con el ERP.",project_id=projects["PRJ-0002"].id,status=ChangeRequestStatus.approved,impact=ChangeRequestImpact.medium,cost_impact=1680,requested_by=users["carlos.ruiz"].id,approved_by=users["admin"].id))
        db.add(ChangeRequest(code="CR-0002",title="Cambio diseno dashboard principal",  description="El cliente solicita rediseno completo del dashboard.",          project_id=projects["PRJ-0001"].id,status=ChangeRequestStatus.submitted,impact=ChangeRequestImpact.high,  cost_impact=2600,requested_by=users["ana.torres"].id))
        db.commit()
        print("  Change requests creados")

    # ── Deliverables ───────────────────────────────────────────────────────────
    # Fields: code, project_id, name, description, status,
    #         planned_date, delivered_date, accepted_date
    if db.query(Deliverable).count() == 0:
        deliverables = [
            dict(code="DEL-0001",name="Documento de Analisis Funcional",project_id=projects["PRJ-0002"].id,status=DeliverableStatus.accepted,   planned_date=today-timedelta(days=25),delivered_date=today-timedelta(days=27),accepted_date=today-timedelta(days=20),description="Documento completo de requisitos funcionales"),
            dict(code="DEL-0002",name="API Backend v1.0",               project_id=projects["PRJ-0002"].id,status=DeliverableStatus.in_progress, planned_date=today+timedelta(days=20),description="Endpoints REST completos con documentacion Swagger"),
            dict(code="DEL-0003",name="Portal Frontend v1.0",           project_id=projects["PRJ-0002"].id,status=DeliverableStatus.planned,      planned_date=today+timedelta(days=55),description="Interfaz React completa con todos los modulos"),
            dict(code="DEL-0004",name="Dashboard BI Ejecutivo",         project_id=projects["PRJ-0003"].id,status=DeliverableStatus.in_progress, planned_date=today+timedelta(days=35),description="Dashboard interactivo con KPIs de negocio"),
            dict(code="DEL-0005",name="Diseno UX Portal Empleados",     project_id=projects["PRJ-0001"].id,status=DeliverableStatus.delivered,   planned_date=today-timedelta(days=5), delivered_date=today-timedelta(days=3),description="Prototipos Figma de alta fidelidad"),
            dict(code="DEL-0006",name="Wireframes App Movil",           project_id=projects["PRJ-0004"].id,status=DeliverableStatus.accepted,    planned_date=today-timedelta(days=60),delivered_date=today-timedelta(days=65),accepted_date=today-timedelta(days=58),description="Wireframes completos iOS y Android"),
            dict(code="DEL-0007",name="Plan de Migracion Cloud",        project_id=projects["PRJ-0005"].id,status=DeliverableStatus.planned,      planned_date=today+timedelta(days=30),description="Plan detallado de migracion a AWS con costes"),
        ]
        for dd in deliverables:
            db.add(Deliverable(**dd))
        db.commit()
        print("  Entregables creados")

    # ── Project Milestones ─────────────────────────────────────────────────────
    # Fields: project_id, name, due_date, billing_amount, billing_pct,
    #         is_completed, is_billed, billed_at, sort_order
    if db.query(ProjectMilestone).count() == 0:
        p2 = projects.get("PRJ-0002")
        if p2:
            for i,(name,pct,amount,due,completed) in enumerate([
                ("Entrega arquitectura",25,23750,today-timedelta(days=20),True),
                ("Entrega API v1",      35,33250,today+timedelta(days=20),False),
                ("Entrega portal",      40,38000,today+timedelta(days=55),False)
            ]):
                db.add(ProjectMilestone(
                    project_id=p2.id, name=name, billing_pct=pct,
                    billing_amount=amount, due_date=due,
                    is_completed=completed, is_billed=completed,
                    billed_at=today-timedelta(days=15) if completed else None,
                    sort_order=i
                ))
        db.commit()

    # ── Backfill client_id on already-seeded records ───────────────────────────
    # Handles DBs seeded before this fix was applied (client_id = NULL).
    name_to_client = {c.name: c for c in db.query(Client).all()}

    for p in db.query(Project).filter(Project.client_id == None, Project.client_name != None).all():
        c = name_to_client.get(p.client_name)
        if c:
            p.client_id = c.id

    for o in db.query(Opportunity).filter(Opportunity.client_id == None, Opportunity.client_name != None).all():
        c = name_to_client.get(o.client_name)
        if c:
            o.client_id = c.id

    for ct in db.query(Contract).filter(Contract.client_id == None, Contract.client_name != None).all():
        c = name_to_client.get(ct.client_name)
        if c:
            ct.client_id = c.id

    db.commit()
    print("  Backfill client_id completado")

    db.close()
    print("\nSeed completado!")
    print(f"  admin / {seed_pwd}")
    print(f"  ana.torres / {seed_pwd}")
    print(f"  luis.vega / {seed_pwd}")
    print(f"  rrhh / {seed_pwd}")


def seed_service_desk():
    """Seed Service Desk with realistic demo data."""
    from app.db.session import SessionLocal
    from app.models.service_desk import (
        ServiceCategory, ServiceItem, SLAPolicy,
        ConfigurationItem, CIType, CIStatus,
        AgentGroup, AgentGroupMember,
        Ticket, TicketType, TicketStatus, TicketPriority,
        TicketUrgency, TicketImpact, SupportLevel,
        KBArticle, KBStatus, Announcement
    )
    from app.models.user import User
    from sqlalchemy import text

    from app.db.base import Base as _Base
    from app.db.session import engine as _eng
    _Base.metadata.create_all(bind=_eng)
    db = SessionLocal()

    if db.query(ServiceCategory).count() > 0:
        db.close()
        return

    users = {u.username: u for u in db.query(User).all()}
    admin = users.get('admin')
    ana   = users.get('ana.torres')
    luis  = users.get('luis.vega')
    sara  = users.get('sara.lope')

    # SLA policy
    sla = SLAPolicy(name="Politica estandar", is_default=True,
                    p1_response_hours=settings.SLA_P1_RESPONSE_HOURS,  p1_resolution_hours=settings.SLA_P1_RESOLUTION_HOURS,
                    p2_response_hours=settings.SLA_P2_RESPONSE_HOURS,  p2_resolution_hours=settings.SLA_P2_RESOLUTION_HOURS,
                    p3_response_hours=settings.SLA_P3_RESPONSE_HOURS,  p3_resolution_hours=settings.SLA_P3_RESOLUTION_HOURS,
                    p4_response_hours=settings.SLA_P4_RESPONSE_HOURS, p4_resolution_hours=settings.SLA_P4_RESOLUTION_HOURS)
    db.add(sla); db.flush()

    # Agent groups
    l1 = AgentGroup(name="L1 Helpdesk",   support_level=SupportLevel.l1)
    l2 = AgentGroup(name="L2 Tecnico",    support_level=SupportLevel.l2)
    l3 = AgentGroup(name="L3 Desarrollo", support_level=SupportLevel.l3)
    db.add_all([l1,l2,l3]); db.flush()
    if luis: db.add(AgentGroupMember(group_id=l1.id, user_id=luis.id, is_lead=True))
    if sara: db.add(AgentGroupMember(group_id=l2.id, user_id=sara.id, is_lead=True))
    if ana:  db.add(AgentGroupMember(group_id=l3.id, user_id=ana.id,  is_lead=True))
    db.flush()

    # Service catalog
    cat_inc  = ServiceCategory(name="Incidencias",              icon="🔥", color="#ff4757", sort_order=0)
    cat_req  = ServiceCategory(name="Solicitudes de servicio",  icon="📋", color="#00d4ff", sort_order=1)
    cat_acc  = ServiceCategory(name="Accesos y usuarios",       icon="🔑", color="#7c3aed", sort_order=2)
    cat_inf  = ServiceCategory(name="Infraestructura",          icon="🖥️", color="#ffb800", sort_order=3)
    db.add_all([cat_inc,cat_req,cat_acc,cat_inf]); db.flush()

    services = [
        ServiceItem(category_id=cat_inc.id, name="Aplicacion no responde",        ticket_type=TicketType.incident,        default_priority=TicketPriority.p2_high,     sla_response_hours=4,  sla_resolution_hours=8,  default_support_level=SupportLevel.l1, sort_order=0),
        ServiceItem(category_id=cat_inc.id, name="Error en produccion",           ticket_type=TicketType.incident,        default_priority=TicketPriority.p1_critical, sla_response_hours=1,  sla_resolution_hours=4,  default_support_level=SupportLevel.l2, sort_order=1),
        ServiceItem(category_id=cat_inc.id, name="Perdida de datos",              ticket_type=TicketType.incident,        default_priority=TicketPriority.p1_critical, sla_response_hours=1,  sla_resolution_hours=4,  default_support_level=SupportLevel.l3, sort_order=2),
        ServiceItem(category_id=cat_req.id, name="Nueva funcionalidad menor",     ticket_type=TicketType.service_request, default_priority=TicketPriority.p4_low,      sla_response_hours=24, sla_resolution_hours=72, default_support_level=SupportLevel.l3, sort_order=0),
        ServiceItem(category_id=cat_req.id, name="Consulta sobre uso",            ticket_type=TicketType.question,        default_priority=TicketPriority.p4_low,      sla_response_hours=8,  sla_resolution_hours=24, default_support_level=SupportLevel.l1, sort_order=1),
        ServiceItem(category_id=cat_req.id, name="Exportacion de datos",          ticket_type=TicketType.service_request, default_priority=TicketPriority.p3_medium,   sla_response_hours=8,  sla_resolution_hours=24, default_support_level=SupportLevel.l1, sort_order=2),
        ServiceItem(category_id=cat_acc.id, name="Alta de usuario",               ticket_type=TicketType.service_request, default_priority=TicketPriority.p3_medium,   sla_response_hours=8,  sla_resolution_hours=24, default_support_level=SupportLevel.l1, sort_order=0),
        ServiceItem(category_id=cat_acc.id, name="Restablecimiento de contrasena",ticket_type=TicketType.service_request, default_priority=TicketPriority.p3_medium,   sla_response_hours=4,  sla_resolution_hours=8,  default_support_level=SupportLevel.l1, sort_order=1),
        ServiceItem(category_id=cat_inf.id, name="Caida del servidor",            ticket_type=TicketType.incident,        default_priority=TicketPriority.p1_critical, sla_response_hours=1,  sla_resolution_hours=4,  default_support_level=SupportLevel.l2, sort_order=0),
        ServiceItem(category_id=cat_inf.id, name="Lentitud del sistema",          ticket_type=TicketType.incident,        default_priority=TicketPriority.p2_high,     sla_response_hours=4,  sla_resolution_hours=8,  default_support_level=SupportLevel.l2, sort_order=1),
    ]
    db.add_all(services); db.flush()

    # CMDB
    ci1 = ConfigurationItem(code="CI-0001",name="Portal Cliente Acme",    ci_type=CIType.application,status=CIStatus.operational,criticality="high",    environment="prod",version="v1.2")
    ci2 = ConfigurationItem(code="CI-0002",name="API Backend Clarive",    ci_type=CIType.application,status=CIStatus.operational,criticality="critical",environment="prod",version="v8.0")
    ci3 = ConfigurationItem(code="CI-0003",name="Base de Datos Principal", ci_type=CIType.database,   status=CIStatus.operational,criticality="critical",environment="prod")
    ci4 = ConfigurationItem(code="CI-0004",name="Infraestructura AWS",     ci_type=CIType.server,     status=CIStatus.operational,criticality="high",    environment="prod")
    db.add_all([ci1,ci2,ci3,ci4]); db.flush()

    # Demo tickets
    now = datetime.now(timezone.utc)
    tickets_data = [
        dict(number="INC-0001",ticket_type=TicketType.incident,       title="El portal no carga en IE11",             description="Varios usuarios reportan que el portal cliente no carga en Internet Explorer 11.", status=TicketStatus.resolved,      priority=TicketPriority.p3_medium,   urgency=TicketUrgency.medium,   impact=TicketImpact.department, support_level=SupportLevel.l1, assigned_to_user_id=luis.id if luis else None, sla_policy_id=sla.id, sla_response_due=now-timedelta(hours=5),  sla_resolution_due=now-timedelta(hours=2),  first_response_at=now-timedelta(hours=7), resolved_at=now-timedelta(hours=1), resolution="IE11 no soporta ES2020. Se aniadio polyfill.", csat_score=5, requester_name="Maria Lopez",   source="portal",   _h=8),
        dict(number="INC-0002",ticket_type=TicketType.incident,       title="Error 500 al exportar informe mensual",  description="Al pulsar Exportar PDF aparece un error 500. Reproducible al 100%.",               status=TicketStatus.in_progress,   priority=TicketPriority.p2_high,     urgency=TicketUrgency.high,     impact=TicketImpact.department, support_level=SupportLevel.l2, assigned_to_user_id=luis.id if luis else None, sla_policy_id=sla.id, sla_response_due=now+timedelta(hours=2),  sla_resolution_due=now+timedelta(hours=6),  first_response_at=now-timedelta(hours=1),                                                     requester_name="Carlos Perez",  source="portal",   _h=2),
        dict(number="REQ-0001",ticket_type=TicketType.service_request,title="Anadir campo Centro de coste",           description="Necesitamos poder asignar un centro de coste a cada proyecto para el ERP.",          status=TicketStatus.pending_client,priority=TicketPriority.p3_medium,   urgency=TicketUrgency.low,      impact=TicketImpact.department, support_level=SupportLevel.l3, assigned_to_user_id=ana.id  if ana  else None, sla_policy_id=sla.id, sla_response_due=now-timedelta(hours=1),  sla_resolution_due=now+timedelta(hours=48), first_response_at=now-timedelta(hours=3),                                                     requester_name="Ana Martin",    source="portal",   _h=5),
        dict(number="INC-0003",ticket_type=TicketType.incident,       title="Caida del servidor de staging",          description="El entorno de staging no responde desde las 14:00h.",                               status=TicketStatus.assigned,      priority=TicketPriority.p1_critical, urgency=TicketUrgency.critical, impact=TicketImpact.department, support_level=SupportLevel.l2, assigned_to_user_id=sara.id if sara else None, sla_policy_id=sla.id, sla_response_due=now+timedelta(minutes=30),sla_resolution_due=now+timedelta(hours=3),                                                            requester_name="Equipo Proyecto",source="internal", _h=1),
        dict(number="QST-0001",ticket_type=TicketType.question,       title="Como configurar notificaciones de alerta",description="Donde puedo activar las notificaciones por email cuando se supera el presupuesto?", status=TicketStatus.closed,        priority=TicketPriority.p4_low,      urgency=TicketUrgency.low,      impact=TicketImpact.user,       support_level=SupportLevel.l1, assigned_to_user_id=luis.id if luis else None, sla_policy_id=sla.id, sla_response_due=now-timedelta(hours=20), sla_resolution_due=now-timedelta(hours=10), first_response_at=now-timedelta(hours=22),resolved_at=now-timedelta(hours=18), resolution="Las notificaciones se configuran en Configuracion > Alertas.", csat_score=4, requester_name="Pedro Sanchez", source="phone",    _h=24),
    ]
    for td in tickets_data:
        hours_ago = td.pop('_h', 0)
        t = Ticket(**td, created_by_user_id=admin.id if admin else None)
        db.add(t); db.flush()
        db.execute(text("UPDATE sd_tickets SET created_at = :ts WHERE id = :id"),
                   {"ts": (now - timedelta(hours=hours_ago)).isoformat(), "id": t.id})
    db.flush()

    # KB articles
    db.add(KBArticle(number="KB-0001",title="Como restablecer tu contrasena",   body="## Sintoma\nNo puedes acceder.\n\n## Solucion\n1. Clic en Olvidaste la contrasena\n2. Introduce tu email\n3. Sigue el enlace en menos de 30 min",             summary="Pasos para recuperar acceso",             status=KBStatus.published,is_public=True,tags="contrasena,acceso,login",view_count=124,helpful_count=98, author_id=admin.id if admin else None,published_at=now-timedelta(days=30)))
    db.add(KBArticle(number="KB-0002",title="Como exportar datos a Excel",       body="## Descripcion\nDesde Exportaciones puedes descargar en Excel o CSV.\n\n## Pasos\n1. Ve a Exportar\n2. Selecciona el tipo\n3. Filtra por fecha\n4. Pulsa Exportar", summary="Descargar datos en Excel o CSV",           status=KBStatus.published,is_public=True,tags="excel,export,csv",      view_count=87, helpful_count=72, author_id=admin.id if admin else None,published_at=now-timedelta(days=15)))
    db.add(KBArticle(number="KB-0003",title="Solucion: Error 500 al exportar",   body="## Sintoma\nAl exportar aparece error 500.\n\n## Causa\nRango de fechas supera 12 meses.\n\n## Solucion\n1. Reduce el rango a max 6 meses\n2. Exporta en intervalos", summary="Que hacer ante error 500 al exportar",   status=KBStatus.published,is_public=True,tags="error,export,500",      view_count=45, helpful_count=38, author_id=luis.id  if luis  else None,published_at=now-timedelta(days=5)))

    # Announcement
    db.add(Announcement(
        title="Mantenimiento programado - Sabado 22 de marzo 02:00-06:00h",
        body="Se realizara mantenimiento en servidores de produccion. El servicio puede no estar disponible.",
        type="maintenance", show_to_clients=True,
        starts_at=now+timedelta(days=6), ends_at=now+timedelta(days=6,hours=4),
        created_by=admin.id if admin else None
    ))

    db.commit()
    db.close()
    print("  Service Desk seed completado")



def seed_v10():
    """Seed demo data for v10 modules: Sprints, Expenses, Automations."""
    from app.db.session import SessionLocal
    import json
    from app.models.user import User
    from app.models.project import Project, ProjectStatus as PS
    from app.models.task import Task
    from app.models.sprints import Sprint, SprintTask, SprintStatus
    from app.models.expenses import Expense, ExpenseCategory, ExpenseStatus
    from app.models.automations import AutomationRule, TriggerType
    from app.db.base import Base
    from app.db.session import engine as _eng_v10
    Base.metadata.create_all(bind=_eng_v10)

    db = SessionLocal()
    print("  Seeding v10 modules: Sprints, Expenses, Automations...")

    admin = db.query(User).filter(User.username == "admin").first()
    ana   = db.query(User).filter(User.username == "ana.torres").first()
    luis  = db.query(User).filter(User.username == "luis.vega").first()
    sara  = db.query(User).filter(User.username == "sara.lope").first()

    # Fetch the first active project
    project = db.query(Project).filter(Project.status == PS.active).first()

    if project:
        tasks = db.query(Task).filter(Task.project_id == project.id).limit(12).all()

        # ── SPRINTS ────────────────────────────────────────────────────────
        # Sprint 1 — Completed
        s1 = Sprint(
            project_id=project.id, number=1,
            name="Sprint 1 — Setup y arquitectura",
            goal="Establecer la base técnica del proyecto y arquitectura inicial",
            status=SprintStatus.completed,
            start_date=date.today() - timedelta(days=28),
            end_date=date.today() - timedelta(days=14),
            planned_points=34, completed_points=28, velocity=2.0,
            went_well="Buena coordinación del equipo. Arquitectura aprobada en primera revisión.",
            to_improve="Las estimaciones fueron optimistas. Daily demasiado largas.",
            action_items="Reducir daily a 15min. Usar poker planning para próximo sprint.",
            created_by=ana.id if ana else None,
        )
        db.add(s1); db.flush()

        # Assign first 4 tasks to sprint 1 as done
        for i, task in enumerate(tasks[:4]):
            db.add(SprintTask(sprint_id=s1.id, task_id=task.id, backlog_order=i))

        # Sprint 2 — Active
        s2 = Sprint(
            project_id=project.id, number=2,
            name="Sprint 2 — Módulo de usuarios",
            goal="Completar CRUD de usuarios, permisos y autenticación JWT",
            status=SprintStatus.active,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=7),
            planned_points=26,
            created_by=ana.id if ana else None,
        )
        db.add(s2); db.flush()

        # Assign next 4 tasks to sprint 2
        for i, task in enumerate(tasks[4:8]):
            db.add(SprintTask(sprint_id=s2.id, task_id=task.id, backlog_order=i))

        # Sprint 3 — Planning (not started)
        s3 = Sprint(
            project_id=project.id, number=3,
            name="Sprint 3 — Integración y reporting",
            goal="Conectar con APIs externas e implementar dashboard de métricas",
            status=SprintStatus.planning,
            start_date=date.today() + timedelta(days=8),
            end_date=date.today() + timedelta(days=22),
            created_by=ana.id if ana else None,
        )
        db.add(s3); db.flush()
        db.flush()
        print("    ✓ 3 sprints creados")

    # ── EXPENSES ───────────────────────────────────────────────────────────
    if project and luis and ana and sara:
        expenses_data = [
            Expense(code="EXP-0001", user_id=luis.id, project_id=project.id,
                category=ExpenseCategory.travel, description="Vuelo Madrid-Barcelona cliente Acme",
                amount=187.50, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=20),
                is_billable=True, status=ExpenseStatus.reimbursed,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=18),
                reviewed_by=ana.id, reviewed_at=datetime.now(timezone.utc)-timedelta(days=16),
                reimbursed_at=datetime.now(timezone.utc)-timedelta(days=10),
                notes="Reunión de kick-off con el cliente"),
            Expense(code="EXP-0002", user_id=sara.id, project_id=project.id,
                category=ExpenseCategory.accommodation, description="Hotel 2 noches Barcelona",
                amount=298.00, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=19),
                is_billable=True, status=ExpenseStatus.approved,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=17),
                reviewed_by=ana.id, reviewed_at=datetime.now(timezone.utc)-timedelta(days=15)),
            Expense(code="EXP-0003", user_id=luis.id, project_id=project.id,
                category=ExpenseCategory.meals, description="Comida de trabajo con el cliente",
                amount=64.30, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=19),
                is_billable=True, status=ExpenseStatus.submitted,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=1)),
            Expense(code="EXP-0004", user_id=ana.id, project_id=project.id,
                category=ExpenseCategory.software, description="Licencia Figma Pro anual",
                amount=144.00, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=5),
                is_billable=False, status=ExpenseStatus.submitted,
                submitted_at=datetime.now(timezone.utc)-timedelta(hours=8),
                notes="Herramienta de diseño para mockups del cliente"),
            Expense(code="EXP-0005", user_id=sara.id, project_id=project.id,
                category=ExpenseCategory.training, description="Curso Docker Avanzado (Udemy)",
                amount=29.99, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=3),
                is_billable=False, status=ExpenseStatus.draft),
            Expense(code="EXP-0006", user_id=luis.id, project_id=project.id,
                category=ExpenseCategory.travel, description="Tren AVE Valencia reunión técnica",
                amount=112.00, currency=settings.DEFAULT_CURRENCY, expense_date=date.today() - timedelta(days=10),
                is_billable=True, status=ExpenseStatus.rejected,
                submitted_at=datetime.now(timezone.utc)-timedelta(days=9),
                reviewed_by=ana.id, reviewed_at=datetime.now(timezone.utc)-timedelta(days=8),
                rejection_reason="Falta adjuntar el billete como justificante"),
        ]
        db.add_all(expenses_data); db.flush()
        print("    ✓ 6 gastos de ejemplo creados")

    # ── AUTOMATIONS ────────────────────────────────────────────────────────
    rules = [
        AutomationRule(
            name="Alerta presupuesto al 85%",
            description="Crea una alerta cuando el gasto supera el 85% del presupuesto del proyecto",
            is_global=True, is_active=True,
            trigger_type=TriggerType.budget_threshold,
            trigger_conditions=json.dumps({"field": "budget_pct", "operator": "greater_than", "value": "85"}),
            actions=json.dumps([{"type": "create_alert", "params": {"alert_type": "budget_warning", "message": "⚠ Presupuesto superado al 85% — revisar consumo", "severity": "warning"}}]),
            run_count=3, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Notificar equipo al iniciar sprint",
            description="Avisa a todos los empleados cuando se inicia un nuevo sprint",
            is_global=True, is_active=True,
            trigger_type=TriggerType.sprint_started,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "employee", "message": "🚀 Nuevo sprint iniciado — revisa el backlog y tus tareas asignadas", "severity": "info"}}]),
            run_count=2, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Recordatorio timesheet viernes",
            description="Recuerda enviar el timesheet cada viernes al equipo",
            is_global=True, is_active=True,
            trigger_type=TriggerType.timesheet_not_submitted,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "employee", "message": "📋 Viernes: recuerda enviar tu timesheet semanal antes de las 18h", "severity": "info"}}]),
            run_count=8, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Escalar ticket P1 a L2",
            description="Escala automáticamente los tickets P1 al nivel L2 cuando se crean",
            is_global=True, is_active=True,
            trigger_type=TriggerType.ticket_created,
            trigger_conditions=json.dumps({"field": "priority", "operator": "equals", "value": "p1_critical"}),
            actions=json.dumps([
                {"type": "escalate_ticket", "params": {"to_level": "l2"}},
                {"type": "notify_role", "params": {"role": "admin", "message": "🚨 Ticket P1 creado — requiere atención inmediata", "severity": "critical"}},
            ]),
            run_count=1, created_by=admin.id if admin else None,
        ),
        AutomationRule(
            name="Alertar tarea vencida (pausada)",
            description="PAUSADA — Notificar al PM cuando una tarea vence sin completar",
            is_global=True, is_active=False,
            trigger_type=TriggerType.task_overdue,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "pm", "message": "⏰ Tarea vencida sin completar en el proyecto", "severity": "warning"}}]),
            run_count=0, created_by=ana.id if ana else None,
        ),
        AutomationRule(
            name="Notificar gasto pendiente de aprobación",
            description="Avisa al PM cuando un empleado envía un gasto para aprobar",
            is_global=True, is_active=True,
            trigger_type=TriggerType.expense_submitted,
            trigger_conditions=None,
            actions=json.dumps([{"type": "notify_role", "params": {"role": "pm", "message": "💸 Gasto enviado pendiente de aprobación — revísalo en Gastos > Pendientes", "severity": "info"}}]),
            run_count=4, created_by=admin.id if admin else None,
        ),
    ]
    db.add_all(rules); db.flush()
    print("    ✓ 6 reglas de automatización creadas")

    db.commit()
    db.close()
    print("  ✓ v10 seed completado")



def seed_enterprise():
    """Seed enterprise demo data: webhooks, SSO config, subcontractors, revenue forecast."""
    from app.db.session import SessionLocal
    import json
    from datetime import date, timedelta
    from app.models.user import User
    from app.models.project import Project
    from app.models.enterprise import (
        Webhook, SSOConfig, SSOProvider,
        Subcontractor, SubcontractorRate, SubcontractorAssignment,
        RevenueForecast, ProjectPermission, ProjectPermissionLevel,
    )

    from app.db.base import Base as _Base
    from app.db.session import engine as _eng
    _Base.metadata.create_all(bind=_eng)
    db = SessionLocal()
    print("  Seeding enterprise modules...")

    admin = db.query(User).filter(User.username == "admin").first()
    ana   = db.query(User).filter(User.username == "ana.torres").first()
    luis  = db.query(User).filter(User.username == "luis.vega").first()

    # Only seed if empty
    if db.query(Webhook).count() > 0:
        db.close()
        return

    # ── Webhooks demo ──────────────────────────────────────────────────────────
    hooks = [
        Webhook(
            name="Slack — Alertas de proyecto",
            url="https://hooks.slack.com/services/DEMO/WEBHOOK/clarive",
            events=json.dumps(["project.created","project.closed","risk.created","expense.approved"]),
            is_active=True,
            total_deliveries=47, failed_deliveries=2,
            created_by=admin.id if admin else None,
        ),
        Webhook(
            name="Microsoft Teams — Notificaciones SD",
            url="https://outlook.office.com/webhook/demo/clarive",
            events=json.dumps(["ticket.created","ticket.resolved"]),
            is_active=True,
            total_deliveries=128, failed_deliveries=0,
            created_by=admin.id if admin else None,
        ),
        Webhook(
            name="ERP interno — Sincronización horas",
            url="https://erp.empresa.com/api/clarive/timesheets",
            secret="s3cr3t-hmac-key-example",
            events=json.dumps(["timesheet.approved","expense.approved"]),
            is_active=False,
            total_deliveries=12, failed_deliveries=5,
            created_by=admin.id if admin else None,
        ),
    ]
    db.add_all(hooks)
    db.flush()

    # ── SSO demo config (SAML, inactive — just example) ───────────────────────
    sso = SSOConfig(
        provider=SSOProvider.saml,
        is_active=False,
        is_default=False,
        saml_entity_id="https://sso.empresa.com/saml/metadata",
        saml_sso_url="https://sso.empresa.com/saml/sso",
        saml_slo_url="https://sso.empresa.com/saml/slo",
        saml_certificate="DEMO-CERTIFICATE-PLACEHOLDER",
        saml_attribute_email="email",
        saml_attribute_name="displayName",
        saml_attribute_role="clariveRole",
        role_mapping=json.dumps({"Clarive-Admin": "admin", "Clarive-PM": "pm", "Clarive-Dev": "employee"}),
        auto_create_users=True,
        default_role="employee",
        allowed_domains="empresa.com,filial.com",
        created_by=admin.id if admin else None,
    )
    db.add(sso)
    db.flush()

    # ── Subcontractors ─────────────────────────────────────────────────────────
    sub1 = Subcontractor(
        code="SUB-0001", name="Carlos Mendoza",
        company="Freelance Dev", email="carlos@freelance.com",
        country="España", currency=settings.DEFAULT_CURRENCY, is_active=True,
        notes="Especialista React/Node. Disponible a tiempo parcial.",
    )
    sub2 = Subcontractor(
        code="SUB-0002", name="TechPartners SL",
        company="TechPartners SL", email="proyectos@techpartners.es",
        country="España", vat_number="B-12345678", currency=settings.DEFAULT_CURRENCY, is_active=True,
        notes="Empresa de infraestructura DevOps y cloud.",
    )
    sub3 = Subcontractor(
        code="SUB-0003", name="DataAnalytics GmbH",
        company="DataAnalytics GmbH", email="contact@dataanalytics.de",
        country="Alemania", vat_number="DE-987654321", currency=settings.DEFAULT_CURRENCY, is_active=True,
        notes="Consultora de BI y analítica de datos.",
    )
    db.add_all([sub1, sub2, sub3])
    db.flush()

    # Rates
    r1 = SubcontractorRate(subcontractor_id=sub1.id, description="Desarrollo Frontend Senior", cost_rate=65.0, sell_rate=90.0, currency=settings.DEFAULT_CURRENCY)
    r2 = SubcontractorRate(subcontractor_id=sub2.id, description="DevOps / Cloud Engineer", cost_rate=80.0, sell_rate=110.0, currency=settings.DEFAULT_CURRENCY)
    r2b = SubcontractorRate(subcontractor_id=sub2.id, description="Arquitecto de soluciones", cost_rate=120.0, sell_rate=160.0, currency=settings.DEFAULT_CURRENCY)
    r3 = SubcontractorRate(subcontractor_id=sub3.id, description="Data Analyst", cost_rate=70.0, sell_rate=95.0, currency=settings.DEFAULT_CURRENCY)
    db.add_all([r1, r2, r2b, r3])
    db.flush()

    # Assign to projects
    project = db.query(Project).filter(Project.status == "active").first()
    if project:
        db.add(SubcontractorAssignment(
            subcontractor_id=sub1.id, project_id=project.id, rate_id=r1.id,
            po_number="PO-2025-001", po_amount=15000.0, hours_contracted=200.0, hours_logged=87.5,
            start_date=date.today() - timedelta(days=45),
            end_date=date.today() + timedelta(days=45),
        ))
        db.add(SubcontractorAssignment(
            subcontractor_id=sub2.id, project_id=project.id, rate_id=r2.id,
            po_number="PO-2025-002", po_amount=24000.0, hours_contracted=300.0, hours_logged=142.0,
            start_date=date.today() - timedelta(days=60),
            end_date=date.today() + timedelta(days=60),
        ))
        db.flush()

        # ── Revenue Forecast ───────────────────────────────────────────────────
        today = date.today()
        year = today.year
        for month in range(1, 13):
            is_past = month < today.month
            is_current = month == today.month

            rev_plan = 45000 + (month % 3) * 8000
            rev_actual = rev_plan * (0.92 + (month % 4) * 0.03) if is_past else (rev_plan * 0.45 if is_current else 0)
            rev_forecast = rev_plan if not is_past else rev_actual
            cost_plan = rev_plan * 0.65
            cost_actual = cost_plan * (0.88 + (month % 3) * 0.04) if is_past else (cost_plan * 0.5 if is_current else 0)

            margin = round((rev_forecast - (cost_actual or cost_plan)) / rev_forecast * 100, 1) if rev_forecast > 0 else None

            db.add(RevenueForecast(
                project_id=project.id, year=year, month=month,
                revenue_planned=round(rev_plan, 2),
                revenue_actual=round(rev_actual, 2),
                revenue_forecast=round(rev_forecast, 2),
                cost_planned=round(cost_plan, 2),
                cost_actual=round(cost_actual, 2),
                hours_planned=round(rev_plan / 75, 1),
                hours_actual=round(rev_actual / 75, 1) if rev_actual > 0 else 0,
                margin_pct=margin,
            ))
        db.flush()

    # ── Project permissions demo ───────────────────────────────────────────────
    if project and luis and ana:
        db.add(ProjectPermission(
            project_id=project.id, user_id=luis.id,
            level=ProjectPermissionLevel.member,
            can_see_financials=False, can_see_rates=False, can_export=True,
            granted_by=ana.id,
            note="Acceso como desarrollador asignado al proyecto",
        ))
        db.flush()

    # ── Welcome notifications ──────────────────────────────────────────────────
    if admin:
        from app.services.notifications import notify_user
        notify_user(db, admin.id, "system",
                   "🎉 Clarive v11 Enterprise activo",
                   "Audit log, SSO, webhooks, permisos granulares y previsión de ingresos ya están disponibles.",
                   action_url="/enterprise")
        if ana:
            notify_user(db, ana.id, "sprint_started",
                       "Sprint 2 en curso",
                       "El sprint activo tiene 4 tareas asignadas. Burndown actualizado.",
                       resource="sprints", action_url="/sprints")
        if luis:
            notify_user(db, luis.id, "expense_rejected",
                       "Gasto rechazado: Tren AVE Valencia",
                       "Falta adjuntar el billete como justificante. Puedes editarlo y volver a enviarlo.",
                       resource="expenses", action_url="/expenses")

    db.commit()
    db.close()
    print("  ✓ Enterprise seed completado")



def seed_v12():
    """Seed v12 demo data: project templates, workflows, sample invoices."""
    from app.db.session import SessionLocal
    import json
    from datetime import date, timedelta
    from app.models.user import User
    from app.models.project import Project
    from app.models.advanced_config import ProjectTemplate, TemplatePhase, TemplateTask
    from app.models.billing_reports import AutomationWorkflow, WorkflowStep, WorkflowStatus, StepType, Invoice, InvoiceLine, InvoiceStatus, ReportDefinition

    from app.db.base import Base as _Base
    from app.db.session import engine as _eng
    _Base.metadata.create_all(bind=_eng)
    db = SessionLocal()
    print("  Seeding v12 modules...")

    if db.query(ProjectTemplate).count() > 0:
        db.close()
        return

    admin = db.query(User).filter(User.username == "admin").first()
    ana   = db.query(User).filter(User.username == "ana.torres").first() # noqa: F841 F401

    # ── Project Templates ──────────────────────────────────────────────────────
    tpl1 = ProjectTemplate(
        name="Implementación ERP", description="Proyecto estándar de implementación de sistema ERP para empresa mediana",
        project_type="consulting", estimated_weeks=16, estimated_hours=480, created_by=admin.id if admin else None,
    )
    tpl2 = ProjectTemplate(
        name="Desarrollo Web a medida", description="Desarrollo de aplicación web con backend REST y frontend React",
        project_type="development", estimated_weeks=12, estimated_hours=360, created_by=admin.id if admin else None,
    )
    tpl3 = ProjectTemplate(
        name="Auditoría IT", description="Auditoría de sistemas, infraestructura y procesos TI",
        project_type="consulting", estimated_weeks=4, estimated_hours=80, created_by=admin.id if admin else None,
    )
    db.add_all([tpl1, tpl2, tpl3]); db.flush()

    # Phases for tpl1 (ERP)
    erp_phases = [
        ("Análisis y diseño", 3, [("Kick-off y toma de requisitos", 16), ("Análisis AS-IS", 24), ("Diseño TO-BE", 32), ("Aprobación de diseño", 8)]),
        ("Configuración", 5, [("Configuración módulo financiero", 40), ("Configuración RRHH", 24), ("Migración de datos", 32), ("Integraciones", 40)]),
        ("Formación y pruebas", 4, [("Formación usuarios clave", 32), ("Pruebas funcionales", 40), ("UAT", 32), ("Corrección de incidencias", 24)]),
        ("Go-live y soporte", 4, [("Go-live", 16), ("Soporte post-implantación", 40), ("Documentación final", 16), ("Cierre de proyecto", 8)]),
    ]
    for i, (phase_name, weeks, tasks) in enumerate(erp_phases):
        ph = TemplatePhase(template_id=tpl1.id, name=phase_name, order=i, estimated_weeks=weeks)
        db.add(ph); db.flush()
        for j, (task_title, hours) in enumerate(tasks):
            db.add(TemplateTask(phase_id=ph.id, title=task_title, estimated_hours=hours, order=j))

    # Phases for tpl2 (Web Dev)
    web_phases = [
        ("Análisis y UX", 2, [("Análisis de requisitos", 16), ("Wireframes y prototipos", 24), ("Aprobación de diseño", 8)]),
        ("Backend", 4, [("Setup arquitectura", 16), ("Desarrollo APIs REST", 80), ("Base de datos", 24), ("Autenticación", 16)]),
        ("Frontend", 4, [("Setup React", 8), ("Componentes base", 40), ("Páginas principales", 80), ("Integración API", 32)]),
        ("Testing y deploy", 2, [("Tests unitarios", 24), ("Tests E2E", 16), ("Deploy producción", 8), ("Documentación", 16)]),
    ]
    for i, (phase_name, weeks, tasks) in enumerate(web_phases):
        ph = TemplatePhase(template_id=tpl2.id, name=phase_name, order=i, estimated_weeks=weeks)
        db.add(ph); db.flush()
        for j, (task_title, hours) in enumerate(tasks):
            db.add(TemplateTask(phase_id=ph.id, title=task_title, estimated_hours=hours, order=j))

    db.flush()

    # ── Automation Workflows ───────────────────────────────────────────────────
    wf1 = AutomationWorkflow(
        name="Escalación automática tickets P1",
        description="Cuando se crea un ticket P1: notificar admin, esperar 30 min, si no asignado → escalar a L3",
        trigger_type="ticket_created",
        trigger_conditions=json.dumps({"field": "priority", "operator": "equals", "value": "p1_critical"}),
        status=WorkflowStatus.active,
        is_global=True, run_count=3, success_count=3,
        created_by=admin.id if admin else None,
    )
    db.add(wf1); db.flush()

    steps_wf1 = [
        WorkflowStep(workflow_id=wf1.id, order=0, step_type=StepType.notify, name="Notificar admin",
                     config=json.dumps({"role": "admin", "message": "🚨 Ticket P1 creado"})),
        WorkflowStep(workflow_id=wf1.id, order=1, step_type=StepType.wait, name="Esperar 30 min",
                     config=json.dumps({"duration": 30, "unit": "minutes"})),
        WorkflowStep(workflow_id=wf1.id, order=2, step_type=StepType.condition, name="¿Asignado?",
                     config=json.dumps({"field": "assigned_to", "operator": "not_equals", "value": "null"}),
                     next_step_yes=None, next_step_no=None),
        WorkflowStep(workflow_id=wf1.id, order=3, step_type=StepType.action, name="Escalar a L3",
                     config=json.dumps({"type": "escalate_ticket", "to_level": "l3"})),
    ]
    db.add_all(steps_wf1)

    wf2 = AutomationWorkflow(
        name="Onboarding nuevo empleado",
        description="Al crear un usuario → crear tareas de onboarding, notificar RRHH, asignar buddy",
        trigger_type="project_status_changed",
        trigger_conditions=json.dumps({"field": "status", "operator": "equals", "value": "active"}),
        status=WorkflowStatus.draft,
        is_global=True, run_count=0,
        created_by=admin.id if admin else None,
    )
    db.add(wf2); db.flush()
    db.add(WorkflowStep(workflow_id=wf2.id, order=0, step_type=StepType.notify, name="Notificar equipo",
                        config=json.dumps({"role": "employee", "message": "🚀 Nuevo proyecto activo"})))
    db.add(WorkflowStep(workflow_id=wf2.id, order=1, step_type=StepType.webhook, name="Notificar Slack",
                        config=json.dumps({"url": "https://hooks.slack.com/services/DEMO", "event": "project.activated"})))

    # ── Sample Invoice ─────────────────────────────────────────────────────────
    project = db.query(Project).filter(Project.status == "active").first()
    if project:
        inv = Invoice(
            number="INV-2025-0001",
            project_id=project.id,
            client_name=project.client_name or "Cliente Demo SA",
            client_vat="B-12345678",
            client_email="facturacion@cliente.com",
            issue_date=date.today() - timedelta(days=30),
            due_date=date.today() - timedelta(days=0),
            tax_rate=settings.DEFAULT_TAX_RATE,
            subtotal=12400.0,
            tax_amount=2604.0,
            total=15004.0,
            currency=settings.DEFAULT_CURRENCY,
            period_from=date.today() - timedelta(days=60),
            period_to=date.today() - timedelta(days=31),
            status=InvoiceStatus.sent,
            notes="Factura correspondiente a los servicios de consultoría del mes anterior.",
            created_by=admin.id if admin else None,
        )
        db.add(inv); db.flush()
        db.add(InvoiceLine(invoice_id=inv.id, order=0, description="Consultor Senior (80h × 95€/h)", quantity=80, unit="h", unit_price=95, amount=7600, source_type="timesheet"))
        db.add(InvoiceLine(invoice_id=inv.id, order=1, description="Project Manager (40h × 120€/h)", quantity=40, unit="h", unit_price=120, amount=4800, source_type="timesheet"))
        db.add(InvoiceLine(invoice_id=inv.id, order=2, description="Gastos de viaje", quantity=1, unit="servicio", unit_price=0, amount=0, source_type="expense"))

        # 2nd invoice paid
        inv2 = Invoice(
            number="INV-2025-0002",
            project_id=project.id,
            client_name=project.client_name or "Cliente Demo SA",
            client_vat="B-12345678",
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=30),
            paid_date=date.today() - timedelta(days=25),
            tax_rate=settings.DEFAULT_TAX_RATE, subtotal=9500.0, tax_amount=1995.0, total=11495.0, currency=settings.DEFAULT_CURRENCY,
            status=InvoiceStatus.paid, created_by=admin.id if admin else None,
        )
        db.add(inv2); db.flush()
        db.add(InvoiceLine(invoice_id=inv2.id, order=0, description="Consultor Senior (100h × 95€/h)", quantity=100, unit="h", unit_price=95, amount=9500, source_type="timesheet"))

    # ── Saved Reports ──────────────────────────────────────────────────────────
    db.add(ReportDefinition(
        name="Rentabilidad por proyecto (mes actual)", description="Margen y coste de proyectos activos",
        category="financial", icon="💰", is_public=True, data_source="projects",
        chart_type="bar_grouped", created_by=admin.id if admin else None,
    ))
    db.add(ReportDefinition(
        name="Utilización equipo (últimas 4 semanas)", description="Horas facturables vs no facturables",
        category="utilization", icon="👥", is_public=True, data_source="imputations",
        chart_type="bar_stacked", created_by=admin.id if admin else None,
    ))

    db.commit()
    db.close()
    print("  ✓ v12 seed completado (plantillas, workflows, facturas, informes)")



def seed_v13():
    """Seed v13 demo data: task dependencies, bookings, exchange rates, SLA schedules, API keys."""
    from app.db.session import SessionLocal
    import json
    from datetime import date, timedelta, time
    from app.models.user import User
    from app.models.project import Project
    from app.models.task import Task
    from app.models.bookings import (
        TaskDependency, DependencyType,
        ResourceBooking, BookingType,
        ExchangeRate, SLASchedule, SLAHoliday,
        ApiKey, RecurringInvoice, RecurringFrequency,
    )

    from app.db.base import Base as _Base
    from app.db.session import engine as _eng
    _Base.metadata.create_all(bind=_eng)
    db = SessionLocal()
    print("  Seeding v13 modules...")

    if db.query(SLASchedule).count() > 0:
        db.close()
        return

    admin = db.query(User).filter(User.username == "admin").first()
    ana   = db.query(User).filter(User.username == "ana.torres").first()
    luis  = db.query(User).filter(User.username == "luis.vega").first()
    sara  = db.query(User).filter(User.username == "sara.lope").first()

    # ── SLA Schedules ──────────────────────────────────────────────────────────
    sla_247 = SLASchedule(
        name="24/7 — Sin restricciones", timezone="UTC",
        is_default=False, work_days=json.dumps([1,2,3,4,5,6,7]),
    )
    sla_biz = SLASchedule(
        name="Horario laboral 9-18 L-V", timezone=settings.DEFAULT_TIMEZONE,
        is_default=True, work_days=json.dumps([1,2,3,4,5]),
        work_start=time(9,0), work_end=time(18,0),
    )
    db.add_all([sla_247, sla_biz]); db.flush()

    # Spanish holidays 2025
    holidays_es = [
        ("2025-01-01","Año Nuevo"),("2025-01-06","Reyes"),("2025-04-18","Viernes Santo"),
        ("2025-05-01","Día del Trabajo"),("2025-08-15","Asunción"),("2025-10-12","Fiesta Nacional"),
        ("2025-11-01","Todos los Santos"),("2025-12-06","Constitución"),("2025-12-08","Inmaculada"),
        ("2025-12-25","Navidad"),
    ]
    for d, name in holidays_es:
        db.add(SLAHoliday(schedule_id=sla_biz.id, date=date.fromisoformat(d), name=name, country="ES"))
    db.flush()
    print("    ✓ SLA schedules con festivos españoles 2025")

    # ── Exchange Rates ─────────────────────────────────────────────────────────
    today = date.today()
    rates = [
        ("EUR","USD",1.085), ("EUR","GBP",0.856), ("EUR","PLN",4.28),
        ("EUR","CHF",0.942), ("EUR","SEK",11.22), ("EUR","JPY",163.5),
        ("EUR","CAD",1.48), ("EUR","MXN",20.8), ("EUR","BRL",6.12),
        ("USD","EUR",0.922), ("GBP","EUR",1.168), ("PLN","EUR",0.234),
    ]
    for fc, tc, r in rates:
        db.add(ExchangeRate(from_currency=fc, to_currency=tc, rate=r, effective_date=today, source="manual"))
    db.flush()
    print("    ✓ Tipos de cambio configurados")

    # ── Task Dependencies + Resource Bookings ──────────────────────────────────
    project = db.query(Project).filter(Project.status == "active").first()
    if project and admin:
        tasks = db.query(Task).filter(Task.project_id == project.id).limit(8).all()

        # Create some FS dependencies between tasks
        if len(tasks) >= 4:
            db.add(TaskDependency(predecessor_id=tasks[0].id, successor_id=tasks[1].id,
                                  dependency_type=DependencyType.finish_to_start, lag_days=0, created_by=admin.id))
            db.add(TaskDependency(predecessor_id=tasks[1].id, successor_id=tasks[2].id,
                                  dependency_type=DependencyType.finish_to_start, lag_days=1, created_by=admin.id))
            db.add(TaskDependency(predecessor_id=tasks[0].id, successor_id=tasks[3].id,
                                  dependency_type=DependencyType.start_to_start, lag_days=0, created_by=admin.id))
            db.flush()
            print("    ✓ Dependencias entre tareas creadas")

        # Resource bookings
        if luis and ana:
            bookings = [
                ResourceBooking(user_id=luis.id, project_id=project.id, booking_type=BookingType.hard,
                    start_date=today, end_date=today + timedelta(days=20), hours_per_day=6.0,
                    note="Desarrollo sprint 2", created_by=ana.id),
                ResourceBooking(user_id=sara.id if sara else luis.id, project_id=project.id, booking_type=BookingType.hard,
                    start_date=today + timedelta(days=5), end_date=today + timedelta(days=35), hours_per_day=8.0,
                    note="DevOps y despliegue", created_by=ana.id),
                ResourceBooking(user_id=ana.id, project_id=project.id, booking_type=BookingType.soft,
                    start_date=today + timedelta(days=14), end_date=today + timedelta(days=28), hours_per_day=4.0,
                    note="Soporte gestión — pendiente confirmar", created_by=admin.id),
            ]
            db.add_all(bookings)
            db.flush()
            print("    ✓ Resource bookings (hard/soft) creados")

    # ── API Key demo ───────────────────────────────────────────────────────────
    if admin:
        import bcrypt as _bcrypt
        raw_key = os.getenv("SEED_API_KEY_DEMO", "nxpm_demo_integration_key_1234")
        hashed = _bcrypt.hashpw(raw_key.encode(), _bcrypt.gensalt()).decode()
        db.add(ApiKey(
            name="Integración BI Dashboard",
            key_hash=hashed,
            key_prefix=raw_key[:12],
            user_id=admin.id,
            scopes=json.dumps(["read"]),
            rate_limit_per_hour=500,
            rate_limit_per_day=5000,
        ))
        db.flush()
        print("    ✓ API key demo creada")

    # ── Recurring Invoice demo ─────────────────────────────────────────────────
    if project and admin:
        import calendar
        last_day = calendar.monthrange(today.year, today.month)[1] # noqa: F841 F401
        next_month_1 = date(today.year if today.month < 12 else today.year+1,
                           today.month % 12 + 1, 1)
        db.add(RecurringInvoice(
            name=f"Retainer mensual — {project.name}",
            project_id=project.id,
            frequency=RecurringFrequency.monthly,
            next_date=next_month_1,
            client_name=project.client_name or "Cliente Demo",
            amount=8500.0, tax_rate=settings.DEFAULT_TAX_RATE, currency=settings.DEFAULT_CURRENCY,
            description="Servicios de consultoría — retainer mensual",
            payment_terms_days=30,
            created_by=admin.id,
        ))
        db.flush()
        print("    ✓ Factura recurrente mensual configurada")

    db.commit()
    db.close()
    print("  ✓ v13 seed completado")



def seed_v14(db):
    """Seed v14 — email templates, onboarding states for existing users, demo widget layouts."""
    from app.models.cab import EmailTemplate
    import json
    from app.db.base import Base
    from app.db.session import engine as _eng_v14
    Base.metadata.create_all(bind=_eng_v14)

    # ── Email templates (seed only if empty)
    if db.query(EmailTemplate).count() == 0:
        email_templates_path = os.getenv("SEED_EMAIL_TEMPLATES_PATH", "seed_email_templates.json")
        if os.path.exists(email_templates_path):
            with open(email_templates_path, "r") as f:
                templates_data = json.load(f)
            templates = [EmailTemplate(
                name=tpl["name"],
                subject=tpl["subject"],
                body_html=tpl["body_html"],
                category=tpl["category"],
                is_system=tpl.get("is_system", True),
                variables=json.dumps(tpl.get("variables", [])),
            ) for tpl in templates_data]
        else:
            templates = [
                EmailTemplate(
                    name="Tarea vencida",
                    subject="[Clarive] Tarea vencida: {{task_title}}",
                    body_html="<h2>Tarea vencida</h2><p>La tarea <strong>{{task_title}}</strong> en el proyecto {{project_name}} ha vencido.</p><p>Responsable: {{assignee_name}}</p>",
                    category="automation", is_system=True,
                    variables=json.dumps(["task_title","project_name","assignee_name","due_date"]),
                ),
                EmailTemplate(
                    name="Alerta de presupuesto",
                    subject="[Clarive] Presupuesto al {{pct_used}}%: {{project_name}}",
                    body_html="<h2>Alerta de presupuesto</h2><p>El proyecto <strong>{{project_name}}</strong> ha consumido el {{pct_used}}% del presupuesto.</p><p>Total: {{budget_total}}€ | Consumido: {{budget_used}}€</p>",
                    category="alert", is_system=True,
                    variables=json.dumps(["project_name","budget_total","budget_used","pct_used"]),
                ),
                EmailTemplate(
                    name="Informe programado",
                    subject="[Clarive] Informe: {{report_name}}",
                    body_html="<h2>Informe: {{report_name}}</h2><p>Generado el {{generated_at}} para el período {{period}}.</p><p>Accede a Clarive para ver el informe completo.</p>",
                    category="report", is_system=True,
                    variables=json.dumps(["report_name","generated_at","period"]),
                ),
                EmailTemplate(
                    name="Ticket SLA vencido",
                    subject="[Service Desk] SLA vencido: #{{ticket_number}}",
                    body_html="<h2>SLA incumplido</h2><p>El ticket <strong>#{{ticket_number}} — {{ticket_title}}</strong> ha superado el SLA.</p><p>Asignado a: {{assignee_name}}</p>",
                    category="alert", is_system=True,
                    variables=json.dumps(["ticket_number","ticket_title","assignee_name","sla_due"]),
                ),
            ]
        for t in templates:
            db.add(t)
        db.flush()

    db.commit()
    print("  ✓ seed_v14: email templates")


def seed_v15(db):
    """Seed v15 — default Slack config, sample budget."""
    from app.models.mfa import SlackConfig, Budget, BudgetEntry
    import datetime

    if db.query(SlackConfig).count() == 0:
        db.add(SlackConfig(
            platform="slack",
            workspace_name="Mi empresa",
            default_channel="#clarive-alerts",
            is_active=False,
            subscriptions='["task_overdue","budget_alert","ticket_sla"]',
        ))
        db.flush()

    year = datetime.date.today().year
    if db.query(Budget).filter(Budget.year == year).count() == 0:
        b = Budget(
            name=f"Presupuesto TI {year}",
            year=year, department="Tecnología",
            total_amount=120000, currency=settings.DEFAULT_CURRENCY,
        )
        db.add(b); db.flush()
        for m in range(1, 13):
            db.add(BudgetEntry(budget_id=b.id, month=m, planned=10000.0))
        db.flush()

    db.commit()
    print("  ✓ seed_v15")


def seed_v16(db):
    """Seed v16 — AI governance config defaults."""
    from app.models.ai_chat import AIGovernanceConfig
    modules = [
        "nexusassist", "nexusagent", "nexusoracle",
        "meeting_assistant", "contract_intelligence", "knowledge_base", "voice",
    ]
    existing = {c.module for c in db.query(AIGovernanceConfig).all()}
    for mod in modules:
        if mod not in existing:
            db.add(AIGovernanceConfig(
                module=mod, is_enabled=True,
                requires_approval_for='[]',
                allowed_roles='["admin","pm","team_lead"]',
            ))
    db.commit()
    print("  ✓ seed_v16: AI governance configs")

def seed_itsm_v2():
    """Seed datos demo para módulos ITSM v2: Routing, Templates, Changes, Major Incidents, KEDB."""
    from app.db.session import SessionLocal
    from app.db.base import Base
    from app.db.session import engine as _engine
    from app.models.service_desk import (
        RoutingRule, TicketTemplate, ITSMChangeRequest, ChangeType, ChangeStatus, ChangeRisk,
        MajorIncident, MajorIncidentStatus, Problem, ProblemStatus, TicketPriority, TicketType,
        CIRelation, CIRelationType, ConfigurationItem, SLAPolicy, AgentGroup,
    )
    from app.models.user import User
    import json

    # Asegurar que todas las tablas nuevas existen (migraciones implícitas)
    Base.metadata.create_all(bind=_engine)

    db = SessionLocal()

    if db.query(RoutingRule).count() > 0:
        db.close()
        return

    users = {u.username: u for u in db.query(User).all()}
    admin = users.get('admin')
    ana   = users.get('ana.torres')
    luis  = users.get('luis.vega') # noqa: F841 F401

    l1_group = db.query(AgentGroup).filter(AgentGroup.name.ilike('%helpdesk%')).first()
    l2_group = db.query(AgentGroup).filter(AgentGroup.name.ilike('%tecnico%')).first()
    sla      = db.query(SLAPolicy).filter(SLAPolicy.is_default == True).first()

    # ── Routing Rules ──────────────────────────────────────────────────────────
    rules = [
        RoutingRule(name="P1 → L2 Técnico automático", priority=10, is_active=True,
                    conditions=json.dumps({"priority": ["p1_critical"]}),
                    actions=json.dumps({"assign_group": l2_group.id if l2_group else "", "set_support_level": "l2"})),
        RoutingRule(name="Incidentes → Helpdesk L1", priority=50, is_active=True,
                    conditions=json.dumps({"ticket_type": "incident", "priority": ["p3_medium", "p4_low"]}),
                    actions=json.dumps({"assign_group": l1_group.id if l1_group else ""})),
        RoutingRule(name="Solicitudes de acceso → L1", priority=60, is_active=True,
                    conditions=json.dumps({"ticket_type": "service_request"}),
                    actions=json.dumps({"assign_group": l1_group.id if l1_group else "", "set_priority": "p3_medium"})),
    ]
    db.add_all(rules); db.flush()

    # ── Ticket Templates ───────────────────────────────────────────────────────
    templates = [
        TicketTemplate(name="Solicitud de acceso VPN",
                       ticket_type=TicketType.service_request,
                       default_priority=TicketPriority.p3_medium,
                       default_group_id=l1_group.id if l1_group else None,
                       default_sla_id=sla.id if sla else None,
                       description_template="Por favor indique:\n- Usuario: \n- Motivo del acceso: \n- Fecha de inicio requerida: \n- Duración estimada: ",
                       custom_fields=json.dumps([
                           {"field": "justification", "label": "Justificación de negocio", "type": "textarea", "required": True},
                           {"field": "duration_days", "label": "Duración (días)", "type": "number", "required": False},
                       ])),
        TicketTemplate(name="Incidente de producción",
                       ticket_type=TicketType.incident,
                       default_priority=TicketPriority.p1_critical,
                       default_group_id=l2_group.id if l2_group else None,
                       default_sla_id=sla.id if sla else None,
                       description_template="**Sistema afectado:** \n**Síntomas observados:** \n**Inicio del incidente:** \n**Impacto en usuarios:** \n**Pasos para reproducir:** ",
                       custom_fields=json.dumps([
                           {"field": "affected_system", "label": "Sistema afectado", "type": "text", "required": True},
                           {"field": "users_affected", "label": "Nº usuarios afectados", "type": "number", "required": False},
                           {"field": "error_message", "label": "Mensaje de error", "type": "textarea", "required": False},
                       ])),
        TicketTemplate(name="Alta de nuevo usuario",
                       ticket_type=TicketType.service_request,
                       default_priority=TicketPriority.p3_medium,
                       default_group_id=l1_group.id if l1_group else None,
                       description_template="**Nombre completo:** \n**Email corporativo:** \n**Departamento:** \n**Rol en el sistema:** \n**Fecha de incorporación:** ",
                       custom_fields=json.dumps([
                           {"field": "role", "label": "Rol solicitado", "type": "select", "required": True,
                            "options": ["Viewer", "Editor", "Manager", "Admin"]},
                           {"field": "start_date", "label": "Fecha de inicio", "type": "date", "required": True},
                       ])),
    ]
    db.add_all(templates); db.flush()

    # ── ITSM Change Requests ───────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    changes = [
        ITSMChangeRequest(
            number="CHG00001", title="Actualización de base de datos PostgreSQL 14 → 16",
            description="Actualizar el motor de BD de producción de PostgreSQL 14 a 16 para aprovechar mejoras de rendimiento.",
            change_type=ChangeType.normal, status=ChangeStatus.cab_review,
            risk=ChangeRisk.high, priority=TicketPriority.p2_high,
            implementation_plan="1. Backup completo\n2. Migración en staging (2h)\n3. Validación\n4. Migración en producción (ventana mantenimiento)\n5. Verificación post-migración",
            rollback_plan="Restaurar backup de producción. Estimado: 45 minutos.",
            test_plan="Tests de regresión en staging con datos de producción anonimizados.",
            business_justification="PostgreSQL 14 EOL en noviembre. Mejora de rendimiento de hasta 30% en queries complejas.",
            impact_description="Downtime de BD estimado en 20-30 minutos durante ventana de mantenimiento.",
            downtime_minutes=25,
            requester_id=admin.id if admin else None,
            owner_id=ana.id if ana else None,
            planned_start=now + timedelta(days=7),
            planned_end=now + timedelta(days=7, hours=4),
        ),
        ITSMChangeRequest(
            number="CHG00002", title="Despliegue de módulo de facturación electrónica",
            description="Añadir integración con la AEAT para emisión de facturas electrónicas según normativa Verifactu 2025.",
            change_type=ChangeType.normal, status=ChangeStatus.approved,
            risk=ChangeRisk.medium, priority=TicketPriority.p2_high,
            implementation_plan="1. Despliegue en staging\n2. Pruebas con certificado de pruebas AEAT\n3. Configuración de producción\n4. Despliegue blue-green",
            rollback_plan="Rollback a versión anterior via blue-green deployment. Sin downtime.",
            business_justification="Obligatorio por normativa fiscal española a partir de 2025.",
            downtime_minutes=0,
            requester_id=admin.id if admin else None,
            owner_id=ana.id if ana else None,
            approved_by=admin.id if admin else None,
            approved_at=now - timedelta(days=2),
            planned_start=now + timedelta(days=3),
            planned_end=now + timedelta(days=3, hours=2),
        ),
        ITSMChangeRequest(
            number="CHG00003", title="Activación de caché Redis para reducir latencia",
            description="Implementar caché distribuida Redis para reducir carga en BD y mejorar tiempos de respuesta de la API.",
            change_type=ChangeType.standard, status=ChangeStatus.implemented,
            risk=ChangeRisk.low, priority=TicketPriority.p3_medium,
            implementation_plan="Deploy Redis cluster, configurar TTLs, invalidación de caché.",
            rollback_plan="Desactivar caché en config y reiniciar servicio. 5 minutos.",
            pir_notes="Reducción del 40% en latencia P95. Sin incidencias en 72h post-deploy.",
            pir_success=True,
            pir_date=now - timedelta(days=3),
            downtime_minutes=0,
            requester_id=admin.id if admin else None,
            actual_start=now - timedelta(days=5),
            actual_end=now - timedelta(days=5, hours=-2),
        ),
    ]
    db.add_all(changes); db.flush()

    # ── Major Incidents ────────────────────────────────────────────────────────
    mi = MajorIncident(
        number="MI0001",
        title="Caída del API de pagos — impacto en facturación clientes",
        status=MajorIncidentStatus.resolved,
        severity="P1",
        impact_statement="El servicio de pagos no responde desde las 14:32h afectando a ~200 clientes activos. Imposibilidad de procesar cobros recurrentes.",
        resolution_summary="Root cause: fallo en renovación automática del certificado SSL del gateway de pagos. Solución: renovación manual + automatización del proceso de renovación.",
        incident_commander_id=admin.id if admin else None,
        communication_lead_id=ana.id if ana else None,
        notifications_sent=3,
        declared_at=now - timedelta(hours=72),
        resolved_at=now - timedelta(hours=69),
        timeline=json.dumps([
            {"time": (now - timedelta(hours=72)).isoformat(), "action": "Incidente declarado P1", "user": "admin"},
            {"time": (now - timedelta(hours=71, minutes=30)).isoformat(), "action": "Root cause identificado: certificado SSL expirado", "user": "ana.torres"},
            {"time": (now - timedelta(hours=71)).isoformat(), "action": "Fix aplicado: renovación manual del certificado", "user": "luis.vega"},
            {"time": (now - timedelta(hours=69)).isoformat(), "action": "Servicio restaurado y verificado. Incidente cerrado.", "user": "admin"},
        ])
    )
    db.add(mi); db.flush()

    # ── KEDB — Problems con workaround ────────────────────────────────────────
    ci_api = db.query(ConfigurationItem).filter(ConfigurationItem.code == "CI-0002").first()
    prob = db.query(Problem).first()
    if not prob:
        prob = Problem(
            number="PRB-0001",
            title="Error 500 al exportar informes con rango > 6 meses",
            description="Los usuarios reportan error 500 al intentar exportar informes cuando el rango de fechas supera los 6 meses.",
            status=ProblemStatus.known_error,
            priority=TicketPriority.p3_medium,
            root_cause="La query SQL no tiene timeout configurado. En rangos largos supera el límite de memoria del proceso de exportación.",
            workaround="Dividir la exportación en períodos de máximo 6 meses. Ejemplo: dos exportaciones de 6 meses en lugar de una de 12.",
            fix_description="Implementar paginación en el proceso de exportación y añadir índice compuesto en fecha+proyecto.",
            ci_id=ci_api.id if ci_api else None,
            owner_user_id=ana.id if ana else None,
        )
        db.add(prob)

    # ── CMDB Relations ─────────────────────────────────────────────────────────
    cis = {ci.code: ci for ci in db.query(ConfigurationItem).all()}
    if cis.get("CI-0001") and cis.get("CI-0002") and not db.query(CIRelation).first():
        db.add(CIRelation(source_ci_id=cis["CI-0001"].id, target_ci_id=cis["CI-0002"].id,
                          relation_type=CIRelationType.depends_on, notes="Portal llama al API para todas las operaciones"))
        db.add(CIRelation(source_ci_id=cis["CI-0002"].id, target_ci_id=cis["CI-0003"].id,
                          relation_type=CIRelationType.depends_on, notes="API lee/escribe datos en la BD"))
        db.add(CIRelation(source_ci_id=cis["CI-0003"].id, target_ci_id=cis["CI-0004"].id,
                          relation_type=CIRelationType.hosts, notes="BD alojada en infraestructura AWS"))
        db.add(CIRelation(source_ci_id=cis["CI-0002"].id, target_ci_id=cis["CI-0004"].id,
                          relation_type=CIRelationType.hosts, notes="API alojada en AWS"))

    # ── CMDB — datos demo con campos específicos por tipo ─────────────────────
    from app.models.cmdb import CMDBItem as _CMDBItem
    if db.query(_CMDBItem).count() == 0:
        cmdb_items = [
            _CMDBItem(name='web-prod-01', ci_type='server', status='active',
                environment='production', hostname='web-prod-01.empresa.com',
                ip_address='10.0.1.10', version='Ubuntu 22.04',
                description='Servidor web principal de producción',
                attributes=json.dumps({'os':'Ubuntu 22.04 LTS','cpu_cores':'8',
                    'ram_gb':'32','serial_number':'DELL-SRV-001','location':'CPD Madrid Rack A-01'}),
                owner_id=admin.id if admin else None),
            _CMDBItem(name='Clarive PSA', ci_type='application', status='active',
                environment='production', version='v3.1.0',
                description='Plataforma PSA principal',
                attributes=json.dumps({'url':'https://clarive.empresa.com',
                    'tech_stack':'React 18 / FastAPI / PostgreSQL',
                    'owner_team':'Equipo Platform','sla_tier':'Gold',
                    'repo_url':'https://github.com/empresa/clarive'}),
                owner_id=ana.id if ana else None),
            _CMDBItem(name='db-prod-01', ci_type='database', status='active',
                environment='production', hostname='db-prod-01.empresa.com',
                ip_address='10.0.2.10', version='PostgreSQL 15.4',
                description='Base de datos principal de producción',
                attributes=json.dumps({'db_engine':'PostgreSQL 15.4','port':'5432',
                    'size_gb':'500','backup_schedule':'Diario 02:00h UTC'}),
                owner_id=admin.id if admin else None),
            _CMDBItem(name='fw-edge-01', ci_type='network', status='active',
                environment='production', hostname='fw-edge-01',
                ip_address='203.0.113.1', version='FortiOS 7.2',
                description='Firewall perimetral principal',
                attributes=json.dumps({'vendor':'Fortinet','model':'FortiGate 200F',
                    'serial_number':'FGT-SN-12345','location':'CPD Madrid Rack B-01'}),
                owner_id=admin.id if admin else None),
            _CMDBItem(name='API Gateway', ci_type='service', status='active',
                environment='production', version='v2.0',
                description='Gateway de APIs internas y externas',
                attributes=json.dumps({'url':'https://api.empresa.com',
                    'sla_tier':'Platinum','owner_team':'DevOps',
                    'dependencies':'auth-service, db-primary'}),
                owner_id=ana.id if ana else None),
        ]
        db.add_all(cmdb_items)
        db.flush()
        print("    ✓ CMDB: 5 activos IT demo creados")

    db.commit()
    db.close()
    print("  ITSM v2 seed completado (routing, templates, changes, major incidents, KEDB, CMDB, CI relations)")

if __name__ == "__main__":
    seed()
    seed_service_desk()
    seed_v10()
    seed_itsm_v2()
    seed_enterprise()
    seed_v12()
    seed_v13()
    db_main = SessionLocal()
    seed_v14(db_main)
    seed_v15(db_main)
    seed_v16(db_main)
    db_main.close()

