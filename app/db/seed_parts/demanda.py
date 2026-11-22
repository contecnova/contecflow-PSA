"""Siembra de demo del flujo de demanda (migración 195): la plantilla piloto en la empresa demo.

Idempotente: si la empresa demo ya tiene el flujo piloto, no hace nada. La
migración 195 hace lo mismo en una base ya creada.
"""


def seed_demanda() -> None:
    from app.db.seed_parts._sesion import sesion_de_siembra
    from app.services.demanda.plantillas import sembrar_plantilla_piloto
    db = sesion_de_siembra()
    try:
        org = db.info.get("organization_id")
        if not org:
            return
        res = sembrar_plantilla_piloto(db, org, None)
        db.commit()
        print(f"  Flujo de demanda: plantilla piloto {'creada' if res['created'] else 'ya existía'}")
    finally:
        db.close()
