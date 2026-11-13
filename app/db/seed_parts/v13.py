"""Seed v13: dependencias de tareas, bookings, tipos de cambio, SLA schedules, API keys."""
from app.core.config import settings

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
    from app.db.seed_parts._sesion import sesion_de_siembra
    db = sesion_de_siembra()
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
        ("2025-05-01","Día del Trabajo"),("2025-08-15","Asuncion"),("2025-10-12","Fiesta Nacional"),
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
        raw_key = settings.SEED_API_KEY_DEMO
        hashed = _bcrypt.hashpw(raw_key.encode(), _bcrypt.gensalt()).decode()
        db.add(ApiKey(
            name="Integración BI Dashboard",
            key_hash=hashed,
            key_prefix=raw_key[:8],
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
        last_day = calendar.monthrange(today.year, today.month)[1] # noqa: F841
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
