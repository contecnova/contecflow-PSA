"""Seed ITSM v2: routing, templates, changes, major incidents, KEDB, CMDB, CI relations."""
from datetime import datetime, timezone, timedelta

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
            description="Los usuarios reportaban error 500 al intentar exportar informes cuando el rango de fechas superaba los 6 meses. Ahora el sistema soporta exportación paginada y eficiente para grandes volúmenes de datos.",
            status=ProblemStatus.known_error,
            priority=TicketPriority.p3_medium,
            root_cause="La query SQL no tenía timeout ni paginación. En rangos largos superaba el límite de memoria del proceso de exportación.",
            workaround=None,
            fix_description="Solución definitiva: exportación paginada y optimizada mediante índices compuestos en fecha+proyecto. Ya no hay límite práctico de rango.",
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
            _CMDBItem(name='Contecflow PSA', ci_type='application', status='active',
                attributes=json.dumps({'url':'https://contecflow.empresa.com',
                    'repo_url':'https://github.com/empresa/contecflow'}),
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
