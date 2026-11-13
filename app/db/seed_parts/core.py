"""Seed principal: settings, departamentos, usuarios, skills, clientes,
proyectos, tareas, imputaciones, pipeline, contratos, riesgos, entregables."""
import random

from datetime import date, timedelta
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


def default_seed_users():
    """Usuarios del seed por defecto.

    Extraído del cuerpo de `seed()` en la auditoría 2026-08 (hallazgo P1-26)
    para que sus propiedades de seguridad sean verificables sin ejecutar el
    seed completo. `tests/test_seed_fixture_parity.py` comprueba que `admin`
    siga siendo el superadministrador de plataforma: si pierde ese flag, los
    endpoints de /organizations quedan inaccesibles para todo el mundo.

    Se lee de forma perezosa (función, no constante de módulo) porque los
    valores dependen de `settings`, que se valida al importar configuración.
    """
    from app.models.user import UserRole

    return [
            dict(username="admin",    email=settings.SUPERADMIN_EMAIL,    full_name="Admin Sistema",  role=UserRole.admin,    department="Direccion",      job_title="CTO",               hourly_rate=None,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS, is_superadmin=True),
            dict(username="ana.torres",email="ana.torres@example.com",full_name="Ana Torres",   role=UserRole.pm,       department="Backend",        job_title="Tech Lead PM",      hourly_rate=85.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="luis.vega", email="luis.vega@example.com", full_name="Luis Vega",    role=UserRole.employee, department="Backend",        job_title="Senior Developer",  hourly_rate=70.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="marta.gil", email="marta.gil@example.com", full_name="Marta Gil",    role=UserRole.employee, department="IA / Data",      job_title="Data Scientist",    hourly_rate=80.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="carlos.ruiz",email="carlos.ruiz@example.com",full_name="Carlos Ruiz",role=UserRole.pm,      department="Gestion",        job_title="Project Manager",   hourly_rate=75.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="sara.lope", email="sara.lope@example.com", full_name="Sara Lopez",   role=UserRole.employee, department="Infraestructura",job_title="DevOps Engineer",   hourly_rate=72.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="diego.mora",email="diego.mora@example.com",full_name="Diego Mora",   role=UserRole.employee, department="Frontend",       job_title="Frontend Developer",hourly_rate=55.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="elena.pardo",email="elena.pardo@example.com",full_name="Elena Pardo",role=UserRole.employee,department="Diseno UX",      job_title="UX Designer",       hourly_rate=65.0,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
            dict(username="rrhh",      email="rrhh@example.com",      full_name="RRHH Manager", role=UserRole.hr,       department="RRHH",           job_title="HR Manager",        hourly_rate=None,  weekly_capacity_hours=settings.DEFAULT_WEEKLY_CAPACITY_HOURS),
    ]

# ── Siembra de datos de demostracion, por fases ──────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18). `seed()` era complejidad 67 en 528 lineas: la
# funcion mas compleja del proyecto, y con 57 de exceso el 12 % de todo lo que
# quedaba del hallazgo. Ya venia dividida en 24 secciones marcadas con
# comentarios, asi que la particion no se ha inventado: se ha leido.
#
# Son datos de DEMOSTRACION, asi que el riesgo de tocarlo es bajo — pero por eso
# mismo llevaba tanto tiempo sin partir. La verificacion es que la siembra siga
# produciendo lo mismo, y eso lo cubre `tests/test_seed_fases.py`.
#
# Los imports siguen siendo LOCALES a cada funcion y no se han subido a nivel de
# modulo: ya lo eran, y `app.models` se importa entre si, asi que subirlos podria
# formar ciclos. Cada fase lleva exactamente los que usa.


def _sembrar_ajustes(db):
    """Ajustes de aplicacion con sus valores por defecto."""
    from app.models.settings import AppSetting

    for key, value in {
        "company_name":"Consultora Contecflow SL","currency":settings.DEFAULT_CURRENCY,
        "timezone":settings.DEFAULT_TIMEZONE,"language":settings.DEFAULT_LANGUAGE,
        "work_hours_per_day":str(settings.DEFAULT_WORKING_HOURS_PER_DAY),
    }.items():
        if not db.query(AppSetting).filter(AppSetting.key==key).first():
            db.add(AppSetting(key=key, value=value))
    db.commit()

def _sembrar_departamentos(db):
    """Los departamentos de la demostracion."""
    from app.models.settings import Department

    for d in ["Backend","Frontend","IA / Data","Infraestructura","Diseno UX","Gestion","RRHH","Ventas"]:
        if not db.query(Department).filter(Department.name==d).first():
            db.add(Department(name=d))
    db.commit()

def _sembrar_festivos(db):
    """Festivos del calendario laboral."""
    from app.models.settings import Holiday

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


def _sembrar_organizacion(db):
    """La organizacion por defecto. Devuelve la fila."""
    from app.models.mfa import Organization

    org = db.query(Organization).filter(Organization.slug == "contecflow-demo").first()
    if not org:
        org = Organization(
            name="Consultora Contecflow SL",
            slug="contecflow-demo",
            plan="enterprise",
            is_active=True,
            max_users=200,
            max_projects=500,
            admin_email="admin@example.com",
            timezone=settings.DEFAULT_TIMEZONE,
            locale=settings.DEFAULT_LANGUAGE,
        )
        db.add(org)
        db.flush()
        print(f"  Org: {org.name} (id={org.id})")
    db.commit()
    return org

def _es_org_vacia_por_defecto(db, org_id) -> bool:
    from app.models.mfa import Organization
    from app.models.project import Project
    org = db.query(Organization).filter(Organization.id == org_id).first()
    return bool(org and org.slug == "default"
                and not db.query(Project.id).filter(Project.organization_id == org_id).first())


def _sembrar_usuarios(db, org):
    """Los usuarios de la demostracion. Devuelve (usuarios, contrasena).

    La contrasena se devuelve porque la ultima seccion la vuelve a
    imprimir al terminar, y calcularla dos veces daria dos distintas."""
    from app.models.user import User

    import json, os
    users_data_path = settings.SEED_USERS_DATA_PATH
    if os.path.exists(users_data_path):
        with open(users_data_path, "r") as f:
            users_data = json.load(f)
    else:
        users_data = default_seed_users()
    users = {}
    seed_pwd = settings.DEFAULT_USER_PASSWORD
    print(f"\n  ⚠️  Seed user password: {seed_pwd}")
    print("     Set DEFAULT_USER_PASSWORD env var to override.\n")
    for ud in users_data:
        u = db.query(User).filter(User.username==ud["username"]).first()
        # ── El `.env` MANDA sobre el superadmin (2026-09-17) ──────────────
        #
        # `SUPERADMIN_PASSWORD` estaba declarada en `.env`, VALIDADA en
        # `app/core/config.py` —que se niega a arrancar si es débil— y no se
        # usaba para poner ninguna contraseña. El superadmin recibía
        # `DEFAULT_USER_PASSWORD` como cualquier otro usuario semilla, y solo
        # en el momento de CREARLO: si la cuenta ya existía, ninguna de las dos
        # se aplicaba nunca.
        #
        # O sea que el fichero de configuración anunciaba una credencial que no
        # dejaba entrar, y encima bloqueaba el arranque si la ponías débil. El
        # mismo fallo se reportó en `contecmind` el mismo día.
        #
        # La contraseña del `.env` se re-afirma en CADA seed: es la vía de
        # recuperación de un superadmin bloqueado, y una vía que solo funciona
        # la primera vez no es una vía.
        #
        # El precio, dicho claro: cambiar la contraseña del superadmin desde la
        # interfaz no sobrevive a un `seed`. Cámbiala también en el `.env`.
        es_superadmin = bool(ud.get("is_superadmin"))
        pwd_usuario = settings.SUPERADMIN_PASSWORD if es_superadmin else seed_pwd
        if not u:
            # Assign all users (including superadmin) to the default org.
            # is_superadmin=True already grants platform-wide elevated access;
            # organization_id NOT NULL is enforced by PostgreSQL.
            u = User(**ud, hashed_password=get_password_hash(pwd_usuario),
                     organization_id=org.id)
            db.add(u); db.flush()
            print(f"  User: {ud['full_name']}")
        elif es_superadmin:
            # Re-afirmar credenciales y acceso del superadmin. Sin esto, una
            # cuenta desactivada o con otra contraseña deja al dueño de la
            # instalación fuera y sin nada que lo arregle salvo tocar la base.
            u.hashed_password = get_password_hash(pwd_usuario)
            if hasattr(u, "is_active"):
                u.is_active = True
            if not u.organization_id or _es_org_vacia_por_defecto(db, u.organization_id):
                # Tras un «clean» el superadmin vive en «Default Organization»,
                # sin datos; la demo se siembra en otra y le salia todo a cero.
                u.organization_id = org.id
            db.flush()
            print(f"  User: {ud['full_name']} (credenciales resincronizadas desde .env)")
        elif not u.organization_id and not u.is_superadmin:
            # Back-fill existing users that missed the org assignment.
            u.organization_id = org.id
        users[ud["username"]] = u
    db.commit()
    return users, seed_pwd

def _sembrar_catalogo_de_habilidades(db):
    """El catalogo de habilidades. Devuelve el indice por nombre."""
    from app.models.resources import Skill, SkillCategory

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
    return skills

def _sembrar_habilidades_de_usuario(db, skills, users):
    """Asigna habilidades a los usuarios de la demostracion."""
    from app.models.resources import SkillLevel, UserSkill

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

def _sembrar_secuencias_de_numeracion(db):
    """Las secuencias de numeracion de cada entidad."""
    from app.models.advanced_config import NumberingSequence

    # Idem: rama muerta, datos de demostracion.
    NUMBERING_SEQUENCES = [
        ("project","PRJ",4),("task","TSK",4),("contract","CNT",4),
        ("opportunity","OPP",4),("risk","RSK",4),
        ("change_request","CR",4),("deliverable","DEL",4)
    ]
    for entity, prefix, padding in NUMBERING_SEQUENCES:
        if not db.query(NumberingSequence).filter(NumberingSequence.entity==entity).first():
            db.add(NumberingSequence(entity=entity, prefix=prefix, padding=padding, current_value=0))
    db.commit()

def _sembrar_tipos_de_tarea(db):
    """Los tipos de tarea con su color e icono."""
    from app.models.advanced_config import TaskType

    # Idem: rama muerta, datos de demostracion.
    TASK_TYPES = [
        ("Feature","#7c3aed","✦"),("Bug","#ff4757","⚠"),
        ("Improvement","#00d4ff","↑"),("Documentation","#ffb800","📄"),
        ("Research","#00c896","🔍"),("DevOps","#ff6b35","⚙")
    ]
    for tname, color, icon in TASK_TYPES:
        if not db.query(TaskType).filter(TaskType.name==tname).first():
            db.add(TaskType(name=tname, value=tname.lower(), color=color, icon=icon, is_active=True))
    db.commit()

def _sembrar_configuracion_de_alertas(db):
    """Umbrales de las alertas."""
    # Revisión 2026-11: los umbrales los siembra `advanced_config_service.seed_alert_configs`
    # con los tipos que lee el motor; aquí se sembraban otros nombres que nadie leía.
    from app.services.advanced_config_service import seed_alert_configs
    seed_alert_configs(db)

def _sembrar_politica_de_vacaciones(db, users):
    """La politica de vacaciones y los saldos iniciales."""
    from app.models.advanced_config import UserVacationBalance, VacationPolicy

    if not db.query(VacationPolicy).first():
        db.add(VacationPolicy(name="Politica estandar", days_per_year=settings.DEFAULT_VACATION_DAYS_PER_YEAR,
                              carries_over=True, max_carryover_days=5,
                              is_default=True, is_active=True))
        db.commit()
    vp = db.query(VacationPolicy).first()

    # Fields: user_id, year, policy_id, days_entitled, days_taken, days_pending
    # Idem: `VACATION_USERS` no se declara; el `getattr` daba siempre esta lista.
    for uname in ["ana.torres", "luis.vega", "marta.gil", "carlos.ruiz",
                  "sara.lope", "diego.mora", "elena.pardo"]:
        u = users.get(uname)
        if u and not db.query(UserVacationBalance).filter(UserVacationBalance.user_id==u.id).first():
            days_taken_val = random.choice([0,2,3,5])
            db.add(UserVacationBalance(user_id=u.id, policy_id=vp.id, year=2026,
                                       days_entitled=settings.DEFAULT_VACATION_DAYS_PER_YEAR,
                                       days_taken=days_taken_val,
                                       days_pending=settings.DEFAULT_VACATION_DAYS_PER_YEAR - days_taken_val))
    db.commit()

def _sembrar_clientes(db, users):
    """Los clientes de la demostracion. Devuelve la lista."""
    import os
    import json
    from app.models.clients import Client, ClientIndustry, ClientStatus

    clients_data_path = settings.SEED_CLIENTS_DATA_PATH
    if os.path.exists(clients_data_path):
        with open(clients_data_path, "r") as f:
            clients_data = json.load(f)
        # Map usernames to user IDs for account_manager_id
        for c in clients_data:
            if "account_manager_username" in c:
                c["account_manager_id"] = users.get(c["account_manager_username"]).id if users.get(c["account_manager_username"]) else None
    else:
        # Idem: `CLIENTS_DATA` no se declara; el `getattr` daba siempre esta lista.
        clients_data = [
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
    client_columns = set(Client.__table__.columns.keys())
    for cd in clients_data:
        c = db.query(Client).filter(Client.name == cd["name"]).first()
        if not c:
            payload = {k: v for k, v in cd.items() if k in client_columns}
            c = Client(**payload, created_by=users["admin"].id)
            db.add(c)
            db.flush()
            print(f"  Client: {cd['name']}")
        clients[cd["name"]] = c
    db.commit()
    print(f"  {len(clients)} clientes disponibles")
    return clients

def _sembrar_proyectos(db, clients, org, users, today):
    """Proyectos de la demostracion. Devuelve el indice por codigo.

    Los devuelve SIEMPRE: si ya habia proyectos los lee de la base en vez
    de crearlos, porque cinco fases posteriores los necesitan."""
    from app.models.project import Project, ProjectStatus, ProjectType

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
    return projects

def _sembrar_tareas(db, projects, users):
    """Tareas de los proyectos, si no hay ninguna."""
    from app.models.task import Task, TaskPriority, TaskStatus

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

def _sembrar_imputaciones(db, projects, users, today):
    """Imputaciones de horas, si no hay ninguna."""
    from app.models.imputation import Imputation

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

def _sembrar_ausencias(db, users, today):
    """Ausencias de la demostracion."""
    from app.models.resources import Absence, AbsenceStatus, AbsenceType

    if db.query(Absence).count() == 0:
        db.add(Absence(user_id=users["luis.vega"].id,  type=AbsenceType.vacation, start_date=today+timedelta(days=14), end_date=today+timedelta(days=21), status=AbsenceStatus.approved, reason="Vacaciones verano"))
        db.add(Absence(user_id=users["marta.gil"].id,  type=AbsenceType.sick,     start_date=today-timedelta(days=5),  end_date=today-timedelta(days=3),  status=AbsenceStatus.approved, reason="Baja medica"))
        db.add(Absence(user_id=users["diego.mora"].id, type=AbsenceType.vacation, start_date=today+timedelta(days=30), end_date=today+timedelta(days=37), status=AbsenceStatus.pending))
        db.add(Absence(user_id=users["elena.pardo"].id,type=AbsenceType.personal, start_date=today+timedelta(days=7),  end_date=today+timedelta(days=7),  status=AbsenceStatus.approved))
        db.add(Absence(user_id=users["sara.lope"].id,  type=AbsenceType.vacation, start_date=today+timedelta(days=60), end_date=today+timedelta(days=74), status=AbsenceStatus.pending))
        db.commit()
        print("  Ausencias creadas")

def _sembrar_oportunidades(db, clients, users, today):
    """Oportunidades del embudo comercial."""
    from app.models.pipeline import Opportunity, OpportunityStage

    if db.query(Opportunity).count() == 0:
        opp_templates = [
            dict(code="OPP-0001",name="Portal B2B RetailCorp",    client_name="RetailCorp SA",  expected_revenue=180000,stage=OpportunityStage.proposal,    probability=60, expected_close_date=today+timedelta(days=30), owner_id=users["carlos.ruiz"].id,description="Portal de gestion de proveedores B2B"),
            dict(code="OPP-0002",name="Sistema RRHH HospitalX",   client_name="Hospital X",     expected_revenue=95000, stage=OpportunityStage.negotiation,  probability=80, expected_close_date=today+timedelta(days=15), owner_id=users["carlos.ruiz"].id),
            dict(code="OPP-0003",name="App Analytics FinanceCo",  client_name="FinanceCo SA",   expected_revenue=220000,stage=OpportunityStage.qualification, probability=35, expected_close_date=today+timedelta(days=60), owner_id=users["ana.torres"].id),
            dict(code="OPP-0004",name="Plataforma IoT Fab",       client_name="FabriTech SL",   expected_revenue=310000,stage=OpportunityStage.lead,          probability=20, expected_close_date=today+timedelta(days=90), owner_id=users["carlos.ruiz"].id),
            dict(code="OPP-0005",name="Migracion cloud StartupX", client_name="StartupX",       expected_revenue=45000, stage=OpportunityStage.won,           probability=100,expected_close_date=today-timedelta(days=5),  owner_id=users["ana.torres"].id),
            dict(code="OPP-0006",name="CRM PymesGroup",           client_name="PymesGroup",     expected_revenue=78000, stage=OpportunityStage.lost,          probability=0,  expected_close_date=today-timedelta(days=20), owner_id=users["carlos.ruiz"].id),
        ]
        created_opps = 0
        for tpl in opp_templates:
            c = clients.get(tpl["client_name"])
            if not c:
                continue
            od = dict(tpl)
            od["client_id"] = c.id
            db.add(Opportunity(**od))
            created_opps += 1
        db.commit()
        print(f"  Oportunidades creadas: {created_opps}")

def _sembrar_contratos(db, clients, projects, today):
    """Contratos y ordenes de trabajo."""
    from app.models.pipeline import Contract, ContractStatus, ContractType, WorkOrder

    if db.query(Contract).count() == 0:
        contract_templates = [
            dict(code="CNT-0001",name="Contrato ERP Acme Industries",project_code="PRJ-0002",client_name="Acme Industries SA",contract_type=ContractType.fixed_price,status=ContractStatus.active,start_date=today-timedelta(days=30),end_date=today+timedelta(days=120),total_amount=95000,signed_date=today-timedelta(days=35)),
            dict(code="CNT-0002",name="Soporte y mantenimiento TechStart",project_code="PRJ-0004",client_name="TechStart SL",contract_type=ContractType.time_material,status=ContractStatus.active,start_date=today-timedelta(days=90),end_date=today+timedelta(days=90),total_amount=36000,monthly_retainer=3000,signed_date=today-timedelta(days=92)),
            dict(code="CNT-0003",name="Proyecto Data Analytics RetailCorp",project_code="PRJ-0003",client_name="RetailCorp SA",contract_type=ContractType.fixed_price,status=ContractStatus.draft,start_date=today+timedelta(days=15),end_date=today+timedelta(days=150),total_amount=180000),
        ]

        created_contracts = {}
        for tpl in contract_templates:
            p = projects.get(tpl["project_code"])
            c = clients.get(tpl["client_name"])
            if not p or not c:
                continue
            payload = dict(tpl)
            payload["project_id"] = p.id
            payload["client_id"] = c.id
            payload.pop("project_code", None)
            contract = Contract(**payload)
            db.add(contract)
            db.flush()
            created_contracts[payload["code"]] = contract

        c1 = created_contracts.get("CNT-0001")
        c2 = created_contracts.get("CNT-0002")
        if c1:
            db.add(WorkOrder(code="OT-0001",contract_id=c1.id,name="Fase 1 - Analisis y diseno",  amount=23750,hours=190,start_date=today-timedelta(days=30),end_date=today-timedelta(days=10)))
            db.add(WorkOrder(code="OT-0002",contract_id=c1.id,name="Fase 2 - Desarrollo API",     amount=33250,hours=270,start_date=today-timedelta(days=10),end_date=today+timedelta(days=40)))
        if c2:
            db.add(WorkOrder(code="OT-0003",contract_id=c2.id,name="Soporte Mensual Marzo",        amount=3000, hours=40, start_date=today,                   end_date=today+timedelta(days=31)))

        db.commit()
        print(f"  Contratos creados: {len(created_contracts)}")

def _sembrar_riesgos(db, projects, users):
    """Riesgos de proyecto."""
    from app.models.pipeline import Risk, RiskImpact, RiskProbability, RiskStatus

    if db.query(Risk).count() == 0:
        risks = [
            dict(code="RSK-0001",title="Retraso entrega API legacy",    description="La integracion con el sistema legacy puede causar retrasos.", project_id=projects["PRJ-0002"].id,probability=RiskProbability.high,    impact=RiskImpact.major,    status=RiskStatus.identified,owner_id=users["luis.vega"].id,  mitigation_plan="Plan de contingencia con API mock"),
            dict(code="RSK-0002",title="Rotacion de personal clave",    description="Riesgo de baja del Tech Lead en proyecto critico.",           project_id=projects["PRJ-0002"].id,probability=RiskProbability.medium,  impact=RiskImpact.critical, status=RiskStatus.mitigating, owner_id=users["ana.torres"].id, mitigation_plan="Documentacion tecnica completa y pair programming"),
            dict(code="RSK-0003",title="Cambio de requisitos cliente",  description="El cliente puede solicitar cambios mayores en alcance.",       project_id=projects["PRJ-0001"].id,probability=RiskProbability.medium,  impact=RiskImpact.moderate, status=RiskStatus.identified,owner_id=users["carlos.ruiz"].id,mitigation_plan="Change control process establecido"),
            dict(code="RSK-0005",title="Caida proveedores cloud",       description="AWS puede tener incidencias que afecten produccion.",          project_id=projects["PRJ-0005"].id,probability=RiskProbability.very_low,impact=RiskImpact.critical, status=RiskStatus.identified,owner_id=users["sara.lope"].id,  mitigation_plan="Multi-region deployment y backup automatico"),
        ]
        for rd in risks:
            rd["risk_score"] = _risk_score(rd["probability"], rd["impact"])
            db.add(Risk(**rd))
        db.commit()
        print("  Riesgos creados")

def _sembrar_peticiones_de_cambio(db, projects, users):
    """Peticiones de cambio."""
    from app.models.resources import ChangeRequest, ChangeRequestImpact, ChangeRequestStatus

    if db.query(ChangeRequest).count() == 0:
        db.add(ChangeRequest(code="CR-0001",title="Anadir modulo facturacion automatica",description="Integrar generacion automatica de facturas con el ERP.",project_id=projects["PRJ-0002"].id,status=ChangeRequestStatus.approved,impact=ChangeRequestImpact.medium,cost_impact=1680,requested_by=users["carlos.ruiz"].id,approved_by=users["admin"].id))
        db.add(ChangeRequest(code="CR-0002",title="Cambio diseno dashboard principal",  description="El cliente solicita rediseno completo del dashboard.",          project_id=projects["PRJ-0001"].id,status=ChangeRequestStatus.submitted,impact=ChangeRequestImpact.high,  cost_impact=2600,requested_by=users["ana.torres"].id))
        db.commit()
        print("  Change requests creados")

def _sembrar_entregables(db, projects, today):
    """Entregables con su estado."""
    from app.models.resources import Deliverable, DeliverableStatus

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

def _sembrar_hitos(db, projects, today):
    """Hitos de proyecto con su importe."""
    from app.models.financial import ProjectMilestone

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


def seed():
    # ── Imports ────────────────────────────────────────────────────────────────
    #
    # Estos imports ya NO los usa esta función: cada fase importa los suyos.
    # Se conservan a propósito, con `noqa`, porque el `create_all` de la línea
    # siguiente crea las tablas de los modelos que estén REGISTRADOS en ese
    # momento — y estos imports son parte de lo que los registra. Quitarlos
    # cambiaría qué tablas se crean al sembrar, que es un cambio de
    # comportamiento y no de estructura.
    #
    # Lo correcto a futuro es `from app import models`, que registra TODOS y no
    # depende de qué haya importado antes quien llame. Pero eso también cambia
    # qué se crea, así que va aparte: el esquema de verdad lo gobierna Alembic
    # desde el hallazgo 11, y este `create_all` es el camino heredado.
    from app.models.user import User  # noqa: F401
    from app.models.clients import Client, ClientStatus, ClientIndustry  # noqa: F401
    from app.models.project import Project, ProjectType, ProjectStatus  # noqa: F401
    from app.models.task import Task, TaskStatus, TaskPriority  # noqa: F401
    from app.models.imputation import Imputation  # noqa: F401
    from app.models.settings import AppSetting, Department, Holiday  # noqa: F401
    from app.models.financial import ProjectMilestone  # noqa: F401
    from app.models.pipeline import (  # noqa: F401
        Opportunity, OpportunityStage,
        Contract, WorkOrder, ContractType, ContractStatus,
        Risk, RiskProbability, RiskImpact, RiskStatus
    )
    from app.models.resources import (  # noqa: F401
        Skill, UserSkill, SkillLevel, SkillCategory,
        Absence, AbsenceType, AbsenceStatus,
        ChangeRequest, ChangeRequestStatus, ChangeRequestImpact,
        Deliverable, DeliverableStatus
    )
    from app.models.advanced_config import (  # noqa: F401
        TaskType, AlertConfig, NumberingSequence, VacationPolicy,
        UserVacationBalance
    )

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    print("Seeding Contecflow database...")
    today = date.today()

    # ── AppSettings ────────────────────────────────────────────────────────────
    _sembrar_ajustes(db)
    _sembrar_departamentos(db)
    _sembrar_festivos(db)
    org = _sembrar_organizacion(db)
    # Auditoria 2026-11: lo que se siembra desde aqui lleva la organizacion.
    db.info["organization_id"] = org.id
    users, seed_pwd = _sembrar_usuarios(db, org)
    skills = _sembrar_catalogo_de_habilidades(db)
    _sembrar_habilidades_de_usuario(db, skills, users)
    _sembrar_secuencias_de_numeracion(db)
    _sembrar_tipos_de_tarea(db)
    _sembrar_configuracion_de_alertas(db)
    _sembrar_politica_de_vacaciones(db, users)
    clients = _sembrar_clientes(db, users)
    projects = _sembrar_proyectos(db, clients, org, users, today)
    _sembrar_tareas(db, projects, users)
    _sembrar_imputaciones(db, projects, users, today)
    _sembrar_ausencias(db, users, today)
    _sembrar_oportunidades(db, clients, users, today)
    _sembrar_contratos(db, clients, projects, today)
    _sembrar_riesgos(db, projects, users)
    _sembrar_peticiones_de_cambio(db, projects, users)
    _sembrar_entregables(db, projects, today)
    _sembrar_hitos(db, projects, today)

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
