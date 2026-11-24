"""`scripts/copia_local.py` con SQLite: copia, manifiesto, restauración y zip slip.

Todo en carpetas temporales: ni `clarive.db` ni `uploads/` reales. `ajuste()`
lee primero el entorno, así que se fijan DATABASE_URL, UPLOAD_DIR, BACKUP_DIR
y BACKUP_KEEP con `monkeypatch` y se quitan las variables de S3.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sqlite3
import zipfile
from pathlib import Path

import pytest

_RUTA = Path(__file__).resolve().parents[1] / "scripts" / "copia_local.py"


@pytest.fixture(scope="module")
def cl():
    spec = importlib.util.spec_from_file_location("copia_local_bajo_prueba", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _filas(ruta: Path) -> list:
    con = sqlite3.connect(ruta)
    try:
        return con.execute("SELECT id, texto FROM notas ORDER BY id").fetchall()
    finally:
        con.close()


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    base = raiz / "datos.db"
    con = sqlite3.connect(base)
    try:
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES ('rev_prueba')")
        con.execute("CREATE TABLE notas (id INTEGER PRIMARY KEY, texto TEXT)")
        con.executemany("INSERT INTO notas (texto) VALUES (?)", [("uno",), ("dos",)])
        con.commit()
    finally:
        con.close()
    uploads = raiz / "subidas"
    (uploads / "sub").mkdir(parents=True)
    (uploads / "a.txt").write_text("hola", encoding="utf-8")
    (uploads / "sub" / "b.bin").write_bytes(b"\x00\x01\x02")
    copias = tmp_path / "copias"
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + base.as_posix())
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))
    monkeypatch.setenv("BACKUP_DIR", str(copias))
    monkeypatch.setenv("BACKUP_KEEP", "14")
    for var in ("AWS_S3_ENDPOINT_URL", "AWS_S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    return {"raiz": raiz, "base": base, "uploads": uploads, "copias": copias}


def test_copia_sqlite_con_integridad_y_manifiesto(cl, entorno):
    carpeta = Path(cl.hacer_copia(str(entorno["raiz"])))
    assert carpeta.parent == entorno["copias"] and carpeta.name.startswith(cl.PREFIJO)

    base = carpeta / cl.BASE_SQLITE
    zip_ = carpeta / cl.FICHEROS
    assert base.exists() and zip_.exists()
    cl.integridad_sqlite(str(base))   # no lanza
    assert _filas(base) == [(1, "uno"), (2, "dos")]
    with zipfile.ZipFile(zip_) as z:
        assert sorted(z.namelist()) == ["a.txt", "sub/b.bin"]

    datos, huellas = cl.leer_manifiesto(str(carpeta))
    assert datos["motor"] == "sqlite" and datos["alembic"] == "rev_prueba"
    for pieza in (cl.BASE_SQLITE, cl.FICHEROS):
        assert huellas[pieza] == hashlib.sha256((carpeta / pieza).read_bytes()).hexdigest()

    carpeta_verificada, _ = cl.verificar(str(carpeta / "MANIFIESTO"))
    assert Path(carpeta_verificada) == carpeta


def test_verificar_rechaza_una_pieza_alterada(cl, entorno):
    carpeta = Path(cl.hacer_copia(str(entorno["raiz"])))
    with open(carpeta / cl.FICHEROS, "ab") as f:
        f.write(b"basura")
    with pytest.raises(cl.ErrorDeCopia, match="huella"):
        cl.verificar(str(carpeta))


def test_integrity_check_detecta_una_base_danada(cl, tmp_path):
    rota = tmp_path / "rota.db"
    rota.write_bytes(b"esto no es una base sqlite" * 100)
    with pytest.raises((cl.ErrorDeCopia, sqlite3.DatabaseError)):
        cl.integridad_sqlite(str(rota))


def test_restauracion_verificada(cl, entorno):
    carpeta = cl.hacer_copia(str(entorno["raiz"]))

    # Cambios posteriores a la copia: en la base y en los ficheros.
    con = sqlite3.connect(entorno["base"])
    try:
        con.execute("DELETE FROM notas WHERE id = 1")
        con.execute("INSERT INTO notas (texto) VALUES ('tres')")
        con.commit()
    finally:
        con.close()
    (entorno["uploads"] / "a.txt").unlink()
    (entorno["uploads"] / "nuevo.txt").write_text("después", encoding="utf-8")

    cl.restaurar(carpeta, True, str(entorno["raiz"]))

    assert _filas(entorno["base"]) == [(1, "uno"), (2, "dos")]
    cl.integridad_sqlite(str(entorno["base"]))
    assert (entorno["uploads"] / "a.txt").read_text(encoding="utf-8") == "hola"
    assert (entorno["uploads"] / "sub" / "b.bin").read_bytes() == b"\x00\x01\x02"
    assert not (entorno["uploads"] / "nuevo.txt").exists()
    # Antes de restaurar se guardó lo que había.
    previas = [d for d in os.listdir(entorno["copias"]) if "antes-de-restaurar" in d]
    assert len(previas) == 1
    assert _filas(entorno["copias"] / previas[0] / cl.BASE_SQLITE) == [(2, "dos"), (3, "tres")]


@pytest.mark.parametrize("nombre", ["../fuera.txt", "sub/../../fuera.txt", "C:/fuera.txt"])
def test_comprobar_zip_rechaza_zip_slip(cl, tmp_path, nombre):
    ruta = tmp_path / "malo.zip"
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("bien.txt", "ok")
        z.writestr(nombre, "fuera")
    with pytest.raises(cl.ErrorDeCopia, match="fuera de la carpeta"):
        cl.comprobar_zip(str(ruta))


def test_restaurar_con_zip_slip_no_toca_nada(cl, entorno):
    carpeta = Path(cl.hacer_copia(str(entorno["raiz"])))
    # Se sustituye el zip por uno con una ruta que sale de la carpeta y se
    # rehace el manifiesto para que la huella cuadre: lo para comprobar_zip.
    zip_ = carpeta / cl.FICHEROS
    with zipfile.ZipFile(zip_, "w") as z:
        z.writestr("../../fuera.txt", "fuera")
    datos, _ = cl.leer_manifiesto(str(carpeta))
    cl.escribir_manifiesto(str(carpeta), datos["fecha"], "sqlite", datos["alembic"],
                           [cl.BASE_SQLITE, cl.FICHEROS])
    con = sqlite3.connect(entorno["base"])
    try:
        con.execute("INSERT INTO notas (texto) VALUES ('posterior')")
        con.commit()
    finally:
        con.close()

    with pytest.raises(cl.ErrorDeCopia, match="fuera de la carpeta"):
        cl.restaurar(str(carpeta), True, str(entorno["raiz"]))

    assert _filas(entorno["base"])[-1] == (3, "posterior")
    assert (entorno["uploads"] / "a.txt").exists()
    assert not (entorno["raiz"].parent / "fuera.txt").exists()
    assert not any("antes-de-restaurar" in d for d in os.listdir(entorno["copias"]))
