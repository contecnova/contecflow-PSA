"""Seed Service Desk: categorías, SLA, grupos de agentes, CIs, tickets, KB, anuncios."""
from datetime import datetime, timezone, timedelta

from app.core.config import settings

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
    ci1 = ConfigurationItem(code="CI-0001",name="Portal Cliente Acme",    ci_type=CIType.application,status=CIStatus.operational,criticality="high",    environment="production",version="v1.2",organization_id=admin.organization_id if admin else None)
    ci2 = ConfigurationItem(code="CI-0002",name="API Backend Contecflow",    ci_type=CIType.application,status=CIStatus.operational,criticality="critical",environment="production",version="v8.0",organization_id=admin.organization_id if admin else None)
    ci3 = ConfigurationItem(code="CI-0003",name="Base de Datos Principal", ci_type=CIType.database,   status=CIStatus.operational,criticality="critical",environment="production",organization_id=admin.organization_id if admin else None)
    ci4 = ConfigurationItem(code="CI-0004",name="Infraestructura AWS",     ci_type=CIType.server,     status=CIStatus.operational,criticality="high",    environment="production",organization_id=admin.organization_id if admin else None)
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
