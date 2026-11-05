"""La busqueda de la KB con pgvector, contra un Postgres que lo tenga.

Se salta sin `KB_PGVECTOR_URL` (p. ej. un `pgvector/pgvector:pg16` desechable).
Sin pgvector la busqueda sigue en Python: eso lo cubren las pruebas de la KB.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("KB_PGVECTOR_URL")
pytestmark = pytest.mark.skipif(not URL, reason="sin KB_PGVECTOR_URL (Postgres con pgvector)")

#: Tres temas, tres ejes: el «modelo» de prueba pone 1 en el eje de su tema.
TEMAS = {"vpn": 0, "impresora": 1, "correo": 2}


class _Modelo:
    def encode(self, textos, show_progress_bar=False):
        import numpy as np
        salida = []
        for t in textos:
            v = np.zeros(8)
            for palabra, eje in TEMAS.items():
                if palabra in t.lower():
                    v[eje] += 1
            v[7] = 0.01  # nunca un vector nulo
            salida.append(v)
        return salida


@pytest.fixture()
def pg(monkeypatch):
    from app.services.service_desk import kb_sugerencias, kb_vectores
    eng = create_engine(URL)
    with eng.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS sd_kb_articles CASCADE"))
        c.execute(text("CREATE TABLE sd_kb_articles (id varchar(36) PRIMARY KEY, number varchar(20), title text, "
                       "summary text, body text, status varchar(20), is_public boolean, organization_id varchar(36), "
                       "embedding text)"))
        assert kb_vectores.preparar(c), "el Postgres de la prueba no tiene pgvector"
    kb_vectores._disponible.clear(); kb_vectores._indices.clear()
    monkeypatch.setattr(kb_sugerencias, "_modelo", lambda: _Modelo())
    yield eng
    eng.dispose()


def test_la_base_ordena_por_coseno_y_crea_el_indice(pg):
    from app.services.service_desk import kb_vectores
    db = sessionmaker(bind=pg)()
    modelo = _Modelo()
    for i, titulo in enumerate(["Configurar la VPN", "La impresora no imprime", "Correo que no llega"]):
        db.execute(text("INSERT INTO sd_kb_articles (id, title, status) VALUES (:i, :t, 'published')"),
                   {"i": f"a{i}", "t": titulo})
        kb_vectores.guardar(db, f"a{i}", list(modelo.encode([titulo])[0]))
    db.commit()
    consulta = list(modelo.encode(["no conecta la vpn de casa"])[0])
    res = kb_vectores.buscar(db, ["a0", "a1", "a2"], consulta, 2)
    assert res[0][1] == "a0" and res[0][0] > 0.99, res
    assert len(res) == 2
    # Solo los visibles: el filtro de organizacion/estado llega como ids.
    assert [i for _, i in kb_vectores.buscar(db, ["a1", "a2"], consulta, 5)][0] != "a0"
    indices = {r[0] for r in db.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'sd_kb_articles'"))}
    assert "ix_sd_kb_embedding_vec_8" in indices
    # Con 3 filas el planificador prefiere recorrerlas; sin esa opcion, que el
    # indice sirve para la consulta (mismo cast que `buscar`).
    db.execute(text("SET enable_seqscan = off"))
    plan = " ".join(r[0] for r in db.execute(text(
        "EXPLAIN SELECT id FROM sd_kb_articles ORDER BY embedding_vec::vector(8) <=> CAST(:q AS vector(8)) LIMIT 1"),
        {"q": str(consulta)}))
    assert "ix_sd_kb_embedding_vec_8" in plan, plan
    db.close()


def test_sin_columna_no_esta_disponible(pg):
    from app.services.service_desk import kb_vectores
    with pg.begin() as c:
        c.execute(text("ALTER TABLE sd_kb_articles DROP COLUMN embedding_vec"))
    kb_vectores._disponible.clear()
    db = sessionmaker(bind=pg)()
    assert kb_vectores.disponible(db) is False
    kb_vectores.guardar(db, "x", [1.0])  # no hace nada ni falla
    db.close()


def test_sugerir_de_punta_a_punta_sobre_el_esquema_real(monkeypatch):
    """Esquema completo, articulo por el ORM, y `sugerir` por el camino de pgvector."""
    from app.db.base import Base
    import app.models  # noqa: F401  (registra todas las tablas)
    from app.models.service_desk import KBArticle, KBStatus
    from app.services.service_desk import kb_sugerencias, kb_vectores

    eng = create_engine(URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE")); c.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        assert kb_vectores.preparar(c)
    kb_vectores._disponible.clear(); kb_vectores._indices.clear()
    monkeypatch.setattr(kb_sugerencias, "_modelo", lambda: _Modelo())
    llamadas = []
    original = kb_vectores.buscar
    monkeypatch.setattr(kb_vectores, "buscar", lambda *a, **k: llamadas.append(1) or original(*a, **k))

    db = sessionmaker(bind=eng)()
    for n, (titulo, publico) in enumerate([("VPN desde casa", True), ("Impresora atascada", True),
                                           ("VPN interna del equipo", False)]):
        db.add(KBArticle(number=f"KB-{n}", title=titulo, body=titulo, status=KBStatus.published, is_public=publico))
    db.commit()
    agente = kb_sugerencias.sugerir(db, "la vpn no conecta", solo_publico=False)
    cliente = kb_sugerencias.sugerir(db, "la vpn no conecta", solo_publico=True)
    assert llamadas, "no paso por pgvector"
    assert {s["title"] for s in agente[:2]} == {"VPN desde casa", "VPN interna del equipo"}
    assert [s["title"] for s in cliente][0] == "VPN desde casa"
    assert "VPN interna del equipo" not in [s["title"] for s in cliente], "el cliente ve un articulo interno"
    db.close(); eng.dispose()


def test_EL_HALLAZGO_el_rol_sin_privilegios_guarda_y_el_dueno_crea_el_indice(pg):
    """Revisión 2026-11 (RLS). El rol de aplicación no puede crear el índice HNSW:
    guardar no debe fallar, y `asegurar_indices` (con el dueño) lo crea después."""
    from app.services.service_desk import kb_vectores
    with pg.begin() as c:
        c.execute(text("DROP ROLE IF EXISTS kb_app_prueba"))
        c.execute(text("CREATE ROLE kb_app_prueba LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD 'kb-prueba'"))
        # Lo mismo que concede `rls.crear_rol` al rol de aplicación.
        c.execute(text("GRANT USAGE ON SCHEMA public TO kb_app_prueba"))
        c.execute(text("GRANT SELECT, INSERT, UPDATE ON sd_kb_articles TO kb_app_prueba"))
        c.execute(text("INSERT INTO sd_kb_articles (id, title, status) VALUES ('v1', 'VPN', 'published')"))
    url_app = pg.url.set(username="kb_app_prueba", password="kb-prueba")
    eng_app = create_engine(url_app)
    try:
        db = sessionmaker(bind=eng_app)()
        kb_vectores.guardar(db, "v1", list(_Modelo().encode(["vpn"])[0]))
        db.commit()   # el vector queda guardado aunque el índice no se pudiera crear
        assert db.execute(text("SELECT embedding_vec IS NOT NULL FROM sd_kb_articles WHERE id='v1'")).scalar()
        db.close()
        with pg.connect() as c:
            assert "ix_sd_kb_embedding_vec_8" not in {r[0] for r in c.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'sd_kb_articles'"))}
        with pg.begin() as c:
            assert kb_vectores.asegurar_indices(c) == [8]
            assert kb_vectores.asegurar_indices(c) == [8], "idempotente"
        with pg.connect() as c:
            assert "ix_sd_kb_embedding_vec_8" in {r[0] for r in c.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'sd_kb_articles'"))}
    finally:
        eng_app.dispose()
        with pg.begin() as c:
            c.execute(text("DROP OWNED BY kb_app_prueba")); c.execute(text("DROP ROLE kb_app_prueba"))
