"""Siembra de demo del flujo de demanda.

23-11-2026: ya NO siembra nada. Antes instalaba en la empresa demo la plantilla «piloto» con los
nombres de un cliente concreto (migración 195 y este seed). La plantilla es ahora OPCIONAL: el
administrador la elige en la biblioteca de plantillas de Demanda (`biblioteca.instalar`).
"""


def seed_demanda() -> None:
    print("  Flujo de demanda: sin siembra por defecto (las plantillas se instalan desde la biblioteca)")
