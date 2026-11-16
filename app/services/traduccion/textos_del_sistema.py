"""Textos que genera el propio sistema, en el idioma de cada cual.

Los tickets que abre ALM (renovacion, averia, devolucion, peticion y compra)
guardaban titulo y descripcion escritos en castellano. Ahora guardan la
plantilla (`sd_tickets.system_template`) y sus datos (`system_params`, JSON):

- Al crearlo, titulo y descripcion se escriben en el idioma de quien lo pide
  (sus preferencias o el de la empresa): es lo que recibe por correo.
- Al verlo, cada operador lo lee en el suyo: `mensajes` pinta la plantilla en
  el idioma de quien mira, sin llamar a ningun proveedor (`origin=system`).
- Si va a un cliente del portal, en el idioma del cliente.

Las plantillas estan en los 8 idiomas del portal (que incluyen los 3 de los
operadores). Una linea solo sale si tiene sus datos (`(plantilla, claves)`).
"""
from __future__ import annotations

import json
from typing import Optional

from app.services.traduccion.idiomas import IDIOMAS_DE_OPERADOR, IDIOMAS_DEL_PORTAL, normalizar

#: Etiquetas de los vencimientos de un activo (`alm_ciclo_de_vida.VENCIMIENTOS`).
VENCIMIENTOS = {
    "warranty_expiry": {"es": "garantía", "en": "warranty", "fr": "garantie", "de": "Garantie", "it": "garanzia",
                        "pt": "garantia", "pl": "gwarancja", "zh": "保修"},
    "eol_date": {"es": "fin de vida", "en": "end of life", "fr": "fin de vie", "de": "Lebensende", "it": "fine vita",
                 "pt": "fim de vida", "pl": "koniec wsparcia", "zh": "生命周期结束"},
    "lease_expiry": {"es": "fin del alquiler", "en": "end of lease", "fr": "fin de location", "de": "Leasingende",
                     "it": "fine noleggio", "pt": "fim do aluguer", "pl": "koniec leasingu", "zh": "租赁到期"},
    "next_maintenance_date": {"es": "mantenimiento", "en": "maintenance", "fr": "maintenance", "de": "Wartung",
                              "it": "manutenzione", "pt": "manutenção", "pl": "konserwacja", "zh": "维护"},
}

# Cada plantilla: idioma -> (titulo, [(linea, claves que necesita)]).
PLANTILLAS: dict[str, dict[str, tuple[str, list[tuple[str, tuple]]]]] = {
    "alm_renewal": {
        "es": ("Renovación de {name}{tag}", [("El activo {name} necesita renovación o sustitución.", ()),
                                             ("Número de serie: {serial}", ()), ("Vence: {field} el {due}", ("due",))]),
        "en": ("Renewal of {name}{tag}", [("The asset {name} needs to be renewed or replaced.", ()),
                                          ("Serial number: {serial}", ()), ("Expires: {field} on {due}", ("due",))]),
        "fr": ("Renouvellement de {name}{tag}", [("L'équipement {name} doit être renouvelé ou remplacé.", ()),
                                                 ("Numéro de série : {serial}", ()),
                                                 ("Échéance : {field} le {due}", ("due",))]),
        "de": ("Erneuerung von {name}{tag}", [("Das Gerät {name} muss erneuert oder ersetzt werden.", ()),
                                              ("Seriennummer: {serial}", ()), ("Läuft ab: {field} am {due}", ("due",))]),
        "it": ("Rinnovo di {name}{tag}", [("Il bene {name} deve essere rinnovato o sostituito.", ()),
                                          ("Numero di serie: {serial}", ()), ("Scade: {field} il {due}", ("due",))]),
        "pt": ("Renovação de {name}{tag}", [("O ativo {name} precisa de ser renovado ou substituído.", ()),
                                            ("Número de série: {serial}", ()), ("Vence: {field} em {due}", ("due",))]),
        "pl": ("Odnowienie: {name}{tag}", [("Zasób {name} wymaga odnowienia lub wymiany.", ()),
                                           ("Numer seryjny: {serial}", ()), ("Wygasa: {field} {due}", ("due",))]),
        "zh": ("续订：{name}{tag}", [("资产 {name} 需要续订或更换。", ()), ("序列号：{serial}", ()),
                                    ("到期：{field}，{due}", ("due",))]),
    },
    "alm_breakdown": {
        "es": ("Avería: {name}{tag}", [("{text}", ()), ("", ()), ("Equipo: {name}{tag}", ()),
                                        ("Número de serie: {serial}", ())]),
        "en": ("Breakdown: {name}{tag}", [("{text}", ()), ("", ()), ("Device: {name}{tag}", ()),
                                           ("Serial number: {serial}", ())]),
        "fr": ("Panne : {name}{tag}", [("{text}", ()), ("", ()), ("Équipement : {name}{tag}", ()),
                                        ("Numéro de série : {serial}", ())]),
        "de": ("Defekt: {name}{tag}", [("{text}", ()), ("", ()), ("Gerät: {name}{tag}", ()),
                                        ("Seriennummer: {serial}", ())]),
        "it": ("Guasto: {name}{tag}", [("{text}", ()), ("", ()), ("Dispositivo: {name}{tag}", ()),
                                        ("Numero di serie: {serial}", ())]),
        "pt": ("Avaria: {name}{tag}", [("{text}", ()), ("", ()), ("Equipamento: {name}{tag}", ()),
                                        ("Número de série: {serial}", ())]),
        "pl": ("Awaria: {name}{tag}", [("{text}", ()), ("", ()), ("Urządzenie: {name}{tag}", ()),
                                        ("Numer seryjny: {serial}", ())]),
        "zh": ("故障：{name}{tag}", [("{text}", ()), ("", ()), ("设备：{name}{tag}", ()), ("序列号：{serial}", ())]),
    },
    "alm_return": {
        "es": ("Devolución de {name}{tag} — {person}", [
            ("Devolución del equipo {name}{tag}.", ()), ("Persona: {person}", ()), ("Número de serie: {serial}", ()),
            ("Fecha límite: {due}", ("due",)), ("Motivo: {reason}", ("reason",)),
            ("Baja de la persona.", ("offboarding",)), ("Se cierra con el acta de devolución firmada.", ())]),
        "en": ("Return of {name}{tag} — {person}", [
            ("Return of the device {name}{tag}.", ()), ("Person: {person}", ()), ("Serial number: {serial}", ()),
            ("Due date: {due}", ("due",)), ("Reason: {reason}", ("reason",)),
            ("The person is leaving.", ("offboarding",)), ("It is closed with the signed return act.", ())]),
        "fr": ("Restitution de {name}{tag} — {person}", [
            ("Restitution de l'équipement {name}{tag}.", ()), ("Personne : {person}", ()),
            ("Numéro de série : {serial}", ()), ("Date limite : {due}", ("due",)), ("Motif : {reason}", ("reason",)),
            ("Départ de la personne.", ("offboarding",)), ("Se clôt avec le procès-verbal de restitution signé.", ())]),
        "de": ("Rückgabe von {name}{tag} — {person}", [
            ("Rückgabe des Geräts {name}{tag}.", ()), ("Person: {person}", ()), ("Seriennummer: {serial}", ()),
            ("Frist: {due}", ("due",)), ("Grund: {reason}", ("reason",)),
            ("Austritt der Person.", ("offboarding",)), ("Wird mit dem unterschriebenen Rückgabeprotokoll geschlossen.", ())]),
        "it": ("Restituzione di {name}{tag} — {person}", [
            ("Restituzione del dispositivo {name}{tag}.", ()), ("Persona: {person}", ()),
            ("Numero di serie: {serial}", ()), ("Scadenza: {due}", ("due",)), ("Motivo: {reason}", ("reason",)),
            ("Uscita della persona.", ("offboarding",)), ("Si chiude con il verbale di restituzione firmato.", ())]),
        "pt": ("Devolução de {name}{tag} — {person}", [
            ("Devolução do equipamento {name}{tag}.", ()), ("Pessoa: {person}", ()), ("Número de série: {serial}", ()),
            ("Data limite: {due}", ("due",)), ("Motivo: {reason}", ("reason",)),
            ("Saída da pessoa.", ("offboarding",)), ("Fecha-se com o auto de devolução assinado.", ())]),
        "pl": ("Zwrot: {name}{tag} — {person}", [
            ("Zwrot urządzenia {name}{tag}.", ()), ("Osoba: {person}", ()), ("Numer seryjny: {serial}", ()),
            ("Termin: {due}", ("due",)), ("Powód: {reason}", ("reason",)),
            ("Odejście osoby.", ("offboarding",)), ("Zamyka się podpisanym protokołem zwrotu.", ())]),
        "zh": ("归还：{name}{tag} — {person}", [
            ("归还设备 {name}{tag}。", ()), ("人员：{person}", ()), ("序列号：{serial}", ()),
            ("截止日期：{due}", ("due",)), ("原因：{reason}", ("reason",)),
            ("人员离职。", ("offboarding",)), ("签署归还单后关闭。", ())]),
    },
    "alm_request": {
        "es": ("Petición: {item}", [("{reason}", ("reason",)), ("Petición de {item}", ("no_reason",))]),
        "en": ("Request: {item}", [("{reason}", ("reason",)), ("Request for {item}", ("no_reason",))]),
        "fr": ("Demande : {item}", [("{reason}", ("reason",)), ("Demande de {item}", ("no_reason",))]),
        "de": ("Anfrage: {item}", [("{reason}", ("reason",)), ("Anfrage für {item}", ("no_reason",))]),
        "it": ("Richiesta: {item}", [("{reason}", ("reason",)), ("Richiesta di {item}", ("no_reason",))]),
        "pt": ("Pedido: {item}", [("{reason}", ("reason",)), ("Pedido de {item}", ("no_reason",))]),
        "pl": ("Wniosek: {item}", [("{reason}", ("reason",)), ("Wniosek o {item}", ("no_reason",))]),
        "zh": ("申请：{item}", [("{reason}", ("reason",)), ("申请 {item}", ("no_reason",))]),
    },
    "alm_purchase_license": {
        "es": ("Compra: un asiento de {item} para {person}", [
            ("No queda un asiento de {item} disponible para {person}.", ()), ("Motivo: {reason}", ("reason",)),
            ("Al recibirlo, dalo de alta en el inventario y asígnalo desde ALM.", ())]),
        "en": ("Purchase: a seat of {item} for {person}", [
            ("There is no seat of {item} left for {person}.", ()), ("Reason: {reason}", ("reason",)),
            ("When it arrives, add it to the inventory and assign it from ALM.", ())]),
        "fr": ("Achat : une licence {item} pour {person}", [
            ("Il ne reste aucune licence {item} disponible pour {person}.", ()), ("Motif : {reason}", ("reason",)),
            ("À la réception, ajoutez-la à l'inventaire et attribuez-la depuis ALM.", ())]),
        "de": ("Kauf: eine Lizenz {item} für {person}", [
            ("Für {person} ist keine Lizenz {item} mehr frei.", ()), ("Grund: {reason}", ("reason",)),
            ("Nach Erhalt im Inventar erfassen und in ALM zuweisen.", ())]),
        "it": ("Acquisto: una licenza {item} per {person}", [
            ("Non resta una licenza {item} disponibile per {person}.", ()), ("Motivo: {reason}", ("reason",)),
            ("Alla ricezione, registrala nell'inventario e assegnala da ALM.", ())]),
        "pt": ("Compra: uma licença de {item} para {person}", [
            ("Não há nenhuma licença de {item} disponível para {person}.", ()), ("Motivo: {reason}", ("reason",)),
            ("Ao recebê-la, registe-a no inventário e atribua-a a partir do ALM.", ())]),
        "pl": ("Zakup: licencja {item} dla {person}", [
            ("Brak wolnej licencji {item} dla {person}.", ()), ("Powód: {reason}", ("reason",)),
            ("Po otrzymaniu dodaj ją do inwentarza i przypisz w ALM.", ())]),
        "zh": ("采购：为 {person} 采购一个 {item} 许可", [
            ("{item} 已没有可分配给 {person} 的许可。", ()), ("原因：{reason}", ("reason",)),
            ("收到后，请登记入库并在 ALM 中分配。", ())]),
    },
    "alm_purchase_asset": {
        "es": ("Compra: un equipo de tipo {item} para {person}", [
            ("No queda un equipo de tipo {item} disponible para {person}.", ()), ("Motivo: {reason}", ("reason",)),
            ("Al recibirlo, dalo de alta en el inventario y asígnalo desde ALM.", ())]),
        "en": ("Purchase: a {item} device for {person}", [
            ("There is no {item} device left for {person}.", ()), ("Reason: {reason}", ("reason",)),
            ("When it arrives, add it to the inventory and assign it from ALM.", ())]),
        "fr": ("Achat : un équipement de type {item} pour {person}", [
            ("Il ne reste aucun équipement de type {item} disponible pour {person}.", ()),
            ("Motif : {reason}", ("reason",)),
            ("À la réception, ajoutez-le à l'inventaire et attribuez-le depuis ALM.", ())]),
        "de": ("Kauf: ein Gerät vom Typ {item} für {person}", [
            ("Für {person} ist kein Gerät vom Typ {item} mehr frei.", ()), ("Grund: {reason}", ("reason",)),
            ("Nach Erhalt im Inventar erfassen und in ALM zuweisen.", ())]),
        "it": ("Acquisto: un dispositivo di tipo {item} per {person}", [
            ("Non resta un dispositivo di tipo {item} disponibile per {person}.", ()), ("Motivo: {reason}", ("reason",)),
            ("Alla ricezione, registralo nell'inventario e assegnalo da ALM.", ())]),
        "pt": ("Compra: um equipamento do tipo {item} para {person}", [
            ("Não há nenhum equipamento do tipo {item} disponível para {person}.", ()),
            ("Motivo: {reason}", ("reason",)),
            ("Ao recebê-lo, registe-o no inventário e atribua-o a partir do ALM.", ())]),
        "pl": ("Zakup: urządzenie typu {item} dla {person}", [
            ("Brak wolnego urządzenia typu {item} dla {person}.", ()), ("Powód: {reason}", ("reason",)),
            ("Po otrzymaniu dodaj je do inwentarza i przypisz w ALM.", ())]),
        "zh": ("采购：为 {person} 采购一台 {item} 设备", [
            ("已没有可分配给 {person} 的 {item} 设备。", ()), ("原因：{reason}", ("reason",)),
            ("收到后，请登记入库并在 ALM 中分配。", ())]),
    },
}

_VACIO = "—"


def idiomas() -> tuple[str, ...]:
    return IDIOMAS_DEL_PORTAL


def _datos(params: dict, idioma: str) -> dict:
    d = {k: ("" if v is None else str(v)) for k, v in (params or {}).items()}
    d.setdefault("serial", _VACIO)
    d["serial"] = d["serial"] or _VACIO
    d["tag"] = f" ({d['tag']})" if d.get("tag") else ""
    if d.get("field"):
        d["field"] = VENCIMIENTOS.get(d["field"], {}).get(idioma, d["field"])
    if not d.get("reason"):
        d["no_reason"] = "1"
    return d


class _Faltan(dict):
    def __missing__(self, clave):
        return _VACIO


def renderizar(codigo: str, params: dict, idioma: Optional[str]) -> Optional[tuple[str, str]]:
    """`(titulo, descripcion)` de la plantilla en `idioma` (o en el primero de los
    operadores si no la hay en ese). None si la plantilla no existe."""
    plantilla = PLANTILLAS.get(codigo)
    if plantilla is None:
        return None
    destino = normalizar(idioma)
    if destino not in plantilla:
        destino = IDIOMAS_DE_OPERADOR[0]
    titulo, lineas = plantilla[destino]
    d = _datos(params, destino)
    cuerpo = [linea.format_map(_Faltan(d)) for linea, claves in lineas if all(d.get(k) for k in claves)]
    return titulo.format_map(_Faltan(d)), "\n".join(cuerpo).strip()


def aplicar(db, ticket, codigo: str, params: dict, idioma: Optional[str] = None) -> None:
    """Escribe en el ticket la plantilla, sus datos y el texto en `idioma` (o el
    de quien lo pide, o el de la empresa)."""
    from app.services.traduccion.ajustes import idioma_por_defecto
    if idioma is None:
        idioma = _idioma_del_solicitante(db, ticket) or idioma_por_defecto(db, ticket.organization_id)
    texto = renderizar(codigo, params, idioma)
    if texto is None:
        return
    ticket.system_template = codigo
    ticket.system_params = json.dumps(params, ensure_ascii=False, default=str)
    ticket.title, ticket.description = texto[0][:500], texto[1]
    ticket.language = normalizar(idioma) if normalizar(idioma) in PLANTILLAS[codigo] else IDIOMAS_DE_OPERADOR[0]


def _idioma_del_solicitante(db, ticket) -> Optional[str]:
    from app.models.user import User
    if ticket.requester_client_id:
        from app.models.client_portal import ClientUser
        c = db.get(ClientUser, ticket.requester_client_id)
        return normalizar(getattr(c, "language", None))
    if ticket.requester_user_id:
        from app.services.traduccion.mensajes import idioma_de_usuario
        u = db.get(User, ticket.requester_user_id)
        return idioma_de_usuario(db, u) if u is not None else None
    return None


def params_de(ticket) -> Optional[dict]:
    try:
        datos = json.loads(ticket.system_params) if ticket.system_params else None
    except ValueError:
        return None
    return datos if isinstance(datos, dict) else None
