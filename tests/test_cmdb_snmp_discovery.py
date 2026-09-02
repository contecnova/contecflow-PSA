"""El descubrimiento SNMP de activos, y la duplicación que lo hacía peligroso.

Auditoría 2026-08 (P3-18 + duplicación encontrada de paso). `discover_snmp` (20)
y `discover_snmp_network` (23) eran **dos funciones casi idénticas** de un
centenar de líneas cada una. Lo único que las diferenciaba era el escaneo
opcional de interfaces y el texto del log.

Todo lo demás estaba duplicado literalmente: la expansión de rangos CIDR, los
cinco OID de sistema, el ayudante de autenticación v2c/v3, el mapeo de var_binds
y **la tabla de clasificación por descripción**.

Esa última duplicación es la que hacía daño. Las dos funciones están vivas:
`run_discovery_for_provider` llama a `discover_snmp` y el endpoint de CMDB llama
a `discover_snmp_network`. Añadir un fabricante a una copia y no a la otra hacía
que el **mismo dispositivo** se clasificara distinto según por dónde entrara el
descubrimiento — y nada fallaba: quedaba mal tipado en el inventario.

Ninguna de las dos tenía tests. Éstos cubren las piezas que ahora son una sola,
sin necesidad de red ni de `pysnmp`.
"""
from __future__ import annotations

import pytest

from app.services.cmdb.discovery import (
    _CLASIFICACION_POR_DESCRIPCION,
    _CI_TYPE_POR_DEFECTO,
    _MAX_IPS_POR_RANGO,
    _OIDS_DE_SISTEMA,
    _clasificar_por_descripcion,
    _expandir_hosts,
    _valores_de_var_binds,
)


# ── Clasificación por descripción ─────────────────────────────────────────────

@pytest.mark.parametrize("descripcion,esperado", [
    ("Cisco IOS Software, C2960 Software", "network_device"),
    ("Juniper Networks, Inc. ex2200", "network_device"),
    ("Arista Networks EOS version 4.20", "network_device"),
    ("Some vendor router v2", "network_device"),
    ("Generic 24-port switch", "network_device"),
    ("Fortinet firewall unit", "network_device"),
    ("Hardware: Intel64 ... Windows Server 2019", "server"),
    ("Microsoft Windows NT", "server"),
    ("Linux srv01 5.15.0-91-generic", "server"),
    ("Ubuntu 22.04.3 LTS", "server"),
    ("CentOS Stream release 9", "server"),
    ("Debian GNU/Linux 12", "server"),
    ("Red Hat Enterprise Linux rhel 9", "server"),
    ("HP LaserJet Pro MFP", "printer"),
    ("Xerox WorkCentre 6515", "printer"),
    ("Generic printer device", "printer"),
    ("APC Smart-UPS 1500", "ups"),
    ("Eaton ups 9PX", "ups"),
])
def test_la_descripcion_decide_el_tipo_de_activo(descripcion, esperado):
    assert _clasificar_por_descripcion(descripcion) == esperado


def test_la_clasificacion_no_distingue_mayusculas():
    """La descripción viene del equipo y cada fabricante la escribe a su manera."""
    for texto in ("CISCO IOS", "cisco ios", "CiScO IoS"):
        assert _clasificar_por_descripcion(texto) == "network_device"


def test_una_descripcion_desconocida_cae_en_equipo_de_red():
    """Es el valor por defecto y coincide con el primer tipo de la tabla: un
    equipo que responde a SNMP y no se identifica es, casi siempre, red."""
    assert _clasificar_por_descripcion("cacharro sin identificar") == _CI_TYPE_POR_DEFECTO
    assert _CI_TYPE_POR_DEFECTO == "network_device"


@pytest.mark.parametrize("vacio", ["", None])
def test_una_descripcion_vacia_no_revienta(vacio):
    assert _clasificar_por_descripcion(vacio) == _CI_TYPE_POR_DEFECTO


def test_el_orden_de_la_tabla_manda():
    """La primera coincidencia gana, y eso es observable: una descripción que
    menciona a la vez un fabricante de red y un sistema operativo se clasifica
    como equipo de red, porque esa fila va primero.

    Se fija porque reordenar la tabla cambiaría la clasificación de dispositivos
    reales —un switch que reporta su Linux interno— sin que nada fallara.
    """
    assert _clasificar_por_descripcion("Cisco Nexus running Linux kernel") == "network_device"


def test_la_tabla_no_tiene_grupos_de_palabras_vacios():
    for palabras, ci_type in _CLASIFICACION_POR_DESCRIPCION:
        assert palabras, f"grupo vacío para {ci_type}"
        assert ci_type, f"tipo vacío para {palabras}"
        assert all(kw == kw.lower() for kw in palabras), (
            f"las palabras clave deben estar en minúsculas: {palabras}"
        )


# ── Expansión de hosts ────────────────────────────────────────────────────────

def test_una_ip_suelta_se_deja_como_esta():
    assert _expandir_hosts(["10.0.0.5"]) == ["10.0.0.5"]


def test_un_nombre_dns_se_deja_como_esta():
    """Lo que no se puede interpretar como red se pasa tal cual: puede ser un
    nombre. Descartarlo dejaría equipos sin sondear en silencio."""
    assert _expandir_hosts(["switch-planta1.local"]) == ["switch-planta1.local"]


def test_un_rango_se_expande_a_sus_direcciones():
    ips = _expandir_hosts(["192.168.1.0/30"])
    assert ips == ["192.168.1.1", "192.168.1.2"]


def test_una_red_grande_se_corta_en_el_tope():
    """Un /16 son 65.534 equipos: sondearlos de uno en uno con dos segundos de
    espera son más de 36 horas. El tope evita que una máscara mal puesta
    convierta el descubrimiento en un barrido interminable."""
    ips = _expandir_hosts(["10.0.0.0/16"])
    assert len(ips) == _MAX_IPS_POR_RANGO


def test_se_pueden_mezclar_rangos_nombres_e_ips():
    ips = _expandir_hosts(["192.168.1.0/30", "switch.local", "10.0.0.9"])
    assert ips == ["192.168.1.1", "192.168.1.2", "switch.local", "10.0.0.9"]


def test_una_lista_vacia_no_revienta():
    assert _expandir_hosts([]) == []


# ── Mapeo de la respuesta SNMP ────────────────────────────────────────────────

class _VarBind(tuple):
    """Un par (oid, valor) como los devuelve pysnmp."""
    def __new__(cls, oid, valor):
        return super().__new__(cls, (oid, valor))


def test_los_cinco_campos_de_sistema_se_indexan():
    var_binds = [
        _VarBind(_OIDS_DE_SISTEMA["sys_descr"], "Cisco IOS"),
        _VarBind(_OIDS_DE_SISTEMA["sys_name"], "sw-01"),
        _VarBind(_OIDS_DE_SISTEMA["sys_location"], "Planta 1"),
        _VarBind(_OIDS_DE_SISTEMA["sys_contact"], "redes@x.com"),
        _VarBind(_OIDS_DE_SISTEMA["sys_objectid"], "1.3.6.1.4.1.9"),
    ]
    valores = _valores_de_var_binds(var_binds)
    assert valores == {
        "sys_descr": "Cisco IOS",
        "sys_name": "sw-01",
        "sys_location": "Planta 1",
        "sys_contact": "redes@x.com",
        "sys_objectid": "1.3.6.1.4.1.9",
    }


def test_un_oid_con_sufijo_tambien_se_reconoce():
    """La comparación es por `in` y no por igualdad porque el equipo puede
    devolver el OID con sufijos. Así estaba y así se conserva."""
    var_binds = [_VarBind(_OIDS_DE_SISTEMA["sys_name"] + ".1", "sw-02")]
    assert _valores_de_var_binds(var_binds)["sys_name"] == "sw-02"


def test_un_oid_desconocido_se_ignora():
    var_binds = [_VarBind("1.9.9.9.9", "lo que sea")]
    assert _valores_de_var_binds(var_binds) == {}


def test_una_respuesta_parcial_devuelve_solo_lo_que_hay():
    """Un equipo puede no contestar a todos los OID; los que falten se quedan
    fuera y el llamante usa sus valores por defecto."""
    var_binds = [_VarBind(_OIDS_DE_SISTEMA["sys_descr"], "Linux")]
    assert _valores_de_var_binds(var_binds) == {"sys_descr": "Linux"}


# ── Las dos entradas comparten el sondeo ──────────────────────────────────────

def test_las_dos_entradas_publicas_llaman_al_mismo_sondeo(monkeypatch):
    """La duplicación, cerrada. Antes eran dos copias de cien líneas."""
    from app.services.cmdb import discovery

    llamadas = []
    monkeypatch.setattr(
        discovery, "_sondear_snmp",
        lambda cfg, **kw: llamadas.append(kw) or [],
    )

    discovery.discover_snmp({"hosts": []})
    discovery.discover_snmp_network({"hosts": []})

    assert len(llamadas) == 2
    assert llamadas[0]["escanear_interfaces"] is False, (
        "el descubrimiento simple no debe escanear interfaces"
    )
    assert llamadas[1]["escanear_interfaces"] is True, (
        "el de red sí, y por defecto"
    )
    assert llamadas[0]["etiqueta_log"] != llamadas[1]["etiqueta_log"], (
        "los dos textos de log se conservan para poder distinguirlos"
    )


def test_el_escaneo_de_interfaces_se_puede_desactivar(monkeypatch):
    from app.services.cmdb import discovery

    llamadas = []
    monkeypatch.setattr(
        discovery, "_sondear_snmp",
        lambda cfg, **kw: llamadas.append(kw) or [],
    )
    discovery.discover_snmp_network({"hosts": [], "scan_interfaces": False})
    assert llamadas[0]["escanear_interfaces"] is False


def test_sin_pysnmp_el_error_dice_que_instalar():
    """El `ImportError` es accionable a propósito: SNMP es opcional y el mensaje
    tiene que decir qué falta, no fallar con un `ModuleNotFoundError` crudo."""
    import builtins

    from app.services.cmdb import discovery

    real = builtins.__import__

    def sin_pysnmp(nombre, *a, **k):
        if nombre.startswith("pysnmp"):
            raise ImportError("no está")
        return real(nombre, *a, **k)

    builtins.__import__ = sin_pysnmp
    try:
        with pytest.raises(ImportError, match="pip install pysnmp"):
            discovery._sondear_snmp(
                {"hosts": []}, escanear_interfaces=False, etiqueta_log="x"
            )
    finally:
        builtins.__import__ = real
