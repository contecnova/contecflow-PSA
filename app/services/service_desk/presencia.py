"""Quien esta mirando o escribiendo en un ticket: aviso de colision en tiempo
real (mejoras de mercado 16-11-2026).

Va por el WebSocket de avisos que ya existe (`/ws/notifications`): la pantalla
del ticket manda `{"type": "ticket_presence", "ticket_id", "mode"}` al abrirlo,
cada cierto tiempo mientras sigue abierto, al empezar a escribir (`edit`) y al
cerrarlo (`leave`). El servidor apunta la presencia y empuja a todos los que
estan en ese ticket la lista de quien hay (`{"type": "ticket_presence",
"ticket_id", "viewers": [...]}`), por el mismo canal (Redis entre procesos).

La presencia caduca sola a los `SD_PRESENCE_TTL_SECONDS` sin latido: un
navegador que se cierra sin decir adios deja de contar.

Donde se guarda: en Redis si esta configurado (`contecflow:sd:presence:<id>`,
un hash usuario -> datos, con caducidad), compartido por todos los procesos;
si no, en la memoria del proceso (desarrollo con un solo proceso).
"""
from __future__ import annotations

import json
import time
from typing import Optional

from app.core.config import settings

MODOS = ("view", "edit", "leave")
_memoria: dict[str, dict[str, dict]] = {}


def _clave(ticket_id: str) -> str:
    return f"contecflow:sd:presence:{ticket_id}"


def ttl_de_presencia(db, org_id) -> int:
    from app.services.settings_service import get_runtime_int
    valor = get_runtime_int(db, "SD_PRESENCE_TTL_SECONDS", org_id)
    return int(valor) if valor and valor > 0 else int(settings.SD_PRESENCE_TTL_SECONDS)


def puede_ver(db, usuario, ticket_id: str) -> bool:
    """El usuario ve el ticket con la regla de siempre (empresa y visibilidad)."""
    from app.core.errores import ErrorDeDominio
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    try:
        get_scoped_ticket_or_404(db, usuario, ticket_id)
        return True
    except ErrorDeDominio:
        return False


def _vivos(filas: dict[str, dict], ahora: float, ttl: int) -> list[dict]:
    return sorted((dict(v, user_id=k) for k, v in filas.items() if ahora - float(v.get("ts", 0)) <= ttl),
                  key=lambda v: v.get("since", 0))


async def anotar(ticket_id: str, user_id: str, nombre: str, modo: str, ttl: int) -> list[dict]:
    """Apunta (o borra con `leave`) la presencia y devuelve quien sigue en el ticket."""
    ahora = time.time()
    if settings.REDIS_URL:
        from app.services.ws_manager import _get_redis
        r = await _get_redis()
        clave = _clave(ticket_id)
        if modo == "leave":
            await r.hdel(clave, user_id)
        else:
            previo = await r.hget(clave, user_id)
            desde = json.loads(previo).get("since", ahora) if previo else ahora
            await r.hset(clave, user_id, json.dumps({"name": nombre, "mode": modo, "ts": ahora, "since": desde}))
            await r.expire(clave, ttl * 2)
        filas = {k: json.loads(v) for k, v in (await r.hgetall(clave)).items()}
        return _vivos(filas, ahora, ttl)
    filas = _memoria.setdefault(ticket_id, {})
    if modo == "leave":
        filas.pop(user_id, None)
    else:
        desde = filas.get(user_id, {}).get("since", ahora)
        filas[user_id] = {"name": nombre, "mode": modo, "ts": ahora, "since": desde}
    vivos = _vivos(filas, ahora, ttl)
    if not vivos:
        _memoria.pop(ticket_id, None)
    return vivos


async def avisar(ticket_id: str, viewers: list[dict], tambien_a: Optional[str] = None, ttl: int = 0) -> None:
    """Empuja la lista a cada persona del ticket (y a quien se acaba de ir)."""
    from app.services.ws_manager import manager
    mensaje = {"type": "ticket_presence", "ticket_id": ticket_id, "ttl": ttl,
               "viewers": [{"user_id": v["user_id"], "name": v.get("name"), "mode": v.get("mode")} for v in viewers]}
    destinos = {v["user_id"] for v in viewers}
    if tambien_a:
        destinos.add(tambien_a)
    for uid in destinos:
        await manager.publish(uid, mensaje)
