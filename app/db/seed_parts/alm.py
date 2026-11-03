"""Datos de demostracion de Licencias y activos (ALM).

Auditoria 2026-11: ALM no tenia semilla, asi que la pantalla salia vacia y no
se veian ni el enlace con la CMDB, ni los vencimientos, ni el UC. Fechas
relativas a hoy para que «Vencen pronto» siempre tenga algo que ensenar. No hace
nada si ya hay proveedores.
"""
from __future__ import annotations

from datetime import timedelta


def seed_alm() -> None:
    from app.core import timeutil
    from app.db.session import SessionLocal
    from app.models.alm import ALMAsset, ALMContract, ALMLicense, ALMVendor
    from app.models.service_desk import ConfigurationItem
    from app.models.user import User

    db = SessionLocal()
    try:
        if db.query(ALMVendor).first():
            return
        usuarios = {u.username: u for u in db.query(User).all()}
        admin = usuarios.get("admin")
        org = admin.organization_id if admin else None
        cis = {c.name: c.id for c in db.query(ConfigurationItem)}
        hoy = timeutil.today()
        dia = lambda n: hoy + timedelta(days=n)  # noqa: E731

        dell = ALMVendor(organization_id=org, name="Dell Technologies", category="hardware",
                         support_email="soporte@dell.example", country="ES")
        msft = ALMVendor(organization_id=org, name="Microsoft", category="software", country="IE")
        aws = ALMVendor(organization_id=org, name="Amazon Web Services", category="cloud", country="US")
        db.add_all([dell, msft, aws])
        db.flush()

        db.add_all([
            ALMContract(organization_id=org, vendor_id=dell.id, title="ProSupport Plus servidores", type="support",
                        status="active", start_date=dia(-300), end_date=dia(65), renewal_date=dia(35),
                        annual_value=4200, billing_cycle="annual", resolution_hours=8,
                        notes="Plazo de resolución 8 h laborables (UC)."),
            ALMContract(organization_id=org, vendor_id=msft.id, title="Enterprise Agreement M365", type="subscription",
                        status="active", start_date=dia(-200), end_date=dia(165), annual_value=18600,
                        billing_cycle="annual"),
            ALMContract(organization_id=org, vendor_id=aws.id, title="Business Support", type="support",
                        status="active", start_date=dia(-120), end_date=dia(245), annual_value=3600,
                        billing_cycle="monthly", resolution_hours=24),
        ])
        db.add_all([
            ALMLicense(organization_id=org, vendor_id=msft.id, name="Microsoft 365 E3", product_name="M365",
                       type="subscription", platform="any", status="active", total_seats=25,
                       expiry_date=dia(165), annual_cost=8400),
            ALMLicense(organization_id=org, vendor_id=msft.id, name="Windows Server 2022 Datacenter",
                       type="perpetual", platform="windows", status="active", total_seats=2),
        ])
        db.add_all([
            ALMAsset(organization_id=org, name="PowerEdge R750 · web-prod-01", type="server", brand="Dell",
                     model="PowerEdge R750", serial_number="DELL-SRV-001", asset_tag="ACT-0001", status="in_use",
                     condition="good", vendor_id=dell.id, location="CPD Madrid Rack A-01",
                     purchase_date=dia(-900), purchase_price=9800, warranty_expiry=dia(5), depreciation_years=5,
                     eol_date=dia(400), next_maintenance_date=dia(20), maintenance_contract="ProSupport Plus",
                     ci_id=cis.get("web-prod-01"), hostname="web-prod-01", ip_address="10.0.1.10"),
            ALMAsset(organization_id=org, name="PowerEdge R650 · db-prod-01", type="server", brand="Dell",
                     model="PowerEdge R650", serial_number="DELL-SRV-002", asset_tag="ACT-0002", status="in_use",
                     condition="good", vendor_id=dell.id, location="CPD Madrid Rack A-02",
                     purchase_date=dia(-700), purchase_price=8600, warranty_expiry=dia(45), depreciation_years=5,
                     ci_id=cis.get("db-prod-01"), hostname="db-prod-01", ip_address="10.0.2.10"),
            ALMAsset(organization_id=org, name="FortiGate 200F", type="network", brand="Fortinet",
                     model="FortiGate 200F", serial_number="FGT-SN-12345", asset_tag="ACT-0003", status="in_use",
                     condition="good", location="CPD Madrid Rack B-01", purchase_date=dia(-1100),
                     purchase_price=5200, lease_expiry=dia(80), depreciation_years=5,
                     ci_id=cis.get("fw-edge-01"), ip_address="203.0.113.1"),
            ALMAsset(organization_id=org, name="Portátil Ana Torres", type="laptop", brand="Dell",
                     model="Latitude 7440", serial_number="DELL-LAT-7440-01", asset_tag="ACT-0004", status="in_use",
                     condition="good", vendor_id=dell.id,
                     assigned_to_id=usuarios["ana.torres"].id if "ana.torres" in usuarios else None,
                     purchase_date=dia(-400), purchase_price=1650, warranty_expiry=dia(330), depreciation_years=3),
            ALMAsset(organization_id=org, name="Portátil de repuesto", type="laptop", brand="Lenovo",
                     model="ThinkPad T14", serial_number="LNV-T14-0099", asset_tag="ACT-0005", status="available",
                     condition="fair", purchase_date=dia(-1300), purchase_price=1200, warranty_expiry=dia(-200),
                     eol_date=dia(25), depreciation_years=3),
        ])
        db.commit()
        print("    ✓ ALM: 3 proveedores, 3 contratos (2 con UC), 2 licencias, 5 activos")
    finally:
        db.close()
