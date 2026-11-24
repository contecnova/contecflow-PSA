"""Árboles de ficheros, diff y comprobaciones antes de abrir el PR (TICKET_A_PR.md §Controles).

Todo en Python puro y en memoria: nada del repositorio se ejecuta en el host.

- `leer_tar`: el tar del repositorio (el que da GitHub o GitLab, o el que
  devuelve el contenedor) a `{ruta: Fichero}`, sin extraer al disco. Se
  descartan enlaces simbólicos, dispositivos y rutas absolutas o con `..`; un
  enlace o una ruta así que aparezca en el resultado del agente BLOQUEA el PR.
- `comparar`: añadidos, modificados y borrados entre el árbol de partida y el resultado.
- `comprobar`: ficheros protegidos (globs configurables), secretos añadidos
  (detector simple de patrones conocidos y de la propia clave del modelo),
  binarios, nº de ficheros y tamaño del diff. Devuelve el primer bloqueo con su
  código del catálogo, o None.
"""
from __future__ import annotations

import difflib
import io
import re
import tarfile
from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass(frozen=True)
class Fichero:
    contenido: bytes
    ejecutable: bool = False


@dataclass
class Arbol:
    ficheros: dict[str, Fichero] = field(default_factory=dict)
    #: Lo que no se ha aceptado al leer (enlaces, rutas raras, dispositivos): ruta → motivo.
    rechazados: dict[str, str] = field(default_factory=dict)


@dataclass
class Cambio:
    ruta: str
    accion: str                      # create | update | delete
    contenido: Optional[bytes] = None
    ejecutable: bool = False


# ── Rutas y globs ────────────────────────────────────────────────────────────

def ruta_segura(nombre: str) -> Optional[str]:
    """La ruta normalizada (sin `./` inicial) si es relativa y sin `..`; si no, None."""
    ruta = (nombre or "").replace("\\", "/")
    while ruta.startswith("./"):
        ruta = ruta[2:]
    ruta = ruta.strip("/") if not ruta.startswith("/") else None
    if not ruta or "\x00" in ruta:
        return None
    partes = ruta.split("/")
    if any(p in ("", ".", "..") for p in partes):
        return None
    return ruta


def _glob_a_regex(patron: str) -> re.Pattern:
    p = patron.strip().replace("\\", "/").lstrip("/")
    salida, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            salida += "(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            salida += ".*"
            i += 2
        elif p[i] == "*":
            salida += "[^/]*"
            i += 1
        elif p[i] == "?":
            salida += "[^/]"
            i += 1
        else:
            salida += re.escape(p[i])
            i += 1
    if "/" not in p:            # sin carpeta: el nombre en cualquier carpeta
        salida = "(?:.*/)?" + salida
    return re.compile(f"^{salida}$", re.IGNORECASE)


def casa(ruta: str, patrones: Iterable[str]) -> Optional[str]:
    """El primer patrón que casa con `ruta`, o None."""
    for p in patrones:
        if p and _glob_a_regex(p).match(ruta):
            return p
    return None


# ── Tar ──────────────────────────────────────────────────────────────────────

def leer_tar(datos: bytes, *, quitar_prefijo: bool = False, max_bytes: int = 200 * 1024 * 1024,
             excluir: Iterable[str] = ()) -> Arbol:
    """`{ruta: Fichero}` desde un tar (o tar.gz). Nunca escribe al disco.

    `quitar_prefijo`: GitHub y GitLab meten todo bajo una carpeta `owner-repo-sha/`.
    `excluir`: globs que no se copian (secretos del repositorio que el agente no debe leer).
    Pasar de `max_bytes` descomprimidos lanza `ValueError("ticket_pr_repo_demasiado_grande")`.
    """
    arbol = Arbol()
    total = 0
    excluir = tuple(excluir)
    with tarfile.open(fileobj=io.BytesIO(datos), mode="r:*") as tar:
        for m in tar:
            nombre = m.name
            if quitar_prefijo:
                nombre = nombre.split("/", 1)[1] if "/" in nombre else ""
                if not nombre:
                    continue
            if m.isdir():
                continue
            ruta = ruta_segura(nombre)
            if ruta is None:
                arbol.rechazados[nombre[:300]] = "ruta"
                continue
            if ruta == ".git" or ruta.startswith(".git/"):
                continue
            if m.issym() or m.islnk():
                arbol.rechazados[ruta] = "enlace"
                continue
            if not m.isfile():
                arbol.rechazados[ruta] = "tipo"
                continue
            if excluir and casa(ruta, excluir):
                continue
            total += m.size
            if total > max_bytes:
                raise ValueError("ticket_pr_repo_demasiado_grande")
            f = tar.extractfile(m)
            contenido = f.read() if f is not None else b""
            arbol.ficheros[ruta] = Fichero(contenido, bool(m.mode & 0o111))
    return arbol


def escribir_tar(arbol: Arbol) -> bytes:
    """Tar (sin comprimir) con los ficheros del árbol, con dueño 1000:1000 y permisos 0644/0755."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for ruta, f in sorted(arbol.ficheros.items()):
            info = tarfile.TarInfo(ruta)
            info.size = len(f.contenido)
            info.mode = 0o755 if f.ejecutable else 0o644
            info.uid = info.gid = 1000
            tar.addfile(info, io.BytesIO(f.contenido))
    return buf.getvalue()


# ── Ignorados (artefactos de compilación y tests) ────────────────────────────

#: Lo que genera una compilación o un `npm ci` dentro del contenedor y nunca va al PR.
IGNORADOS_DE_FABRICA: tuple[str, ...] = (
    "node_modules/**", "**/node_modules/**", "**/__pycache__/**", "*.pyc", ".pytest_cache/**", ".mypy_cache/**",
    ".ruff_cache/**", ".venv/**", "venv/**", ".tox/**", "dist/**", "build/**", "target/**", ".gradle/**",
    "coverage/**", ".coverage", ".nyc_output/**", ".next/**", ".turbo/**", ".cache/**", ".opencode/**",
    ".local/**", ".config/**", ".npm/**",
)


def patrones_de_gitignore(arbol: Arbol) -> list[str]:
    """Los patrones simples del `.gitignore` de la raíz (sin negaciones)."""
    f = arbol.ficheros.get(".gitignore")
    if f is None:
        return []
    patrones = []
    for linea in f.contenido.decode("utf-8", errors="replace").splitlines()[:500]:
        linea = linea.strip()
        if not linea or linea.startswith(("#", "!")):
            continue
        anclado = "/" in linea.rstrip("/")      # git: con barra en medio o al principio, relativo a la raíz
        linea = linea.strip("/")
        if not linea:
            continue
        base = linea if anclado else f"**/{linea}"
        patrones += [base, f"{base}/**"]        # el fichero o todo lo que haya debajo de la carpeta
    return patrones


def quitar_ignorados(antes: Arbol, despues: Arbol) -> Arbol:
    """El resultado sin lo NUEVO que casa con los ignorados (de fábrica y del `.gitignore`).

    Lo que ya estaba en el repositorio nunca se ignora: un cambio en un fichero
    versionado siempre cuenta.
    """
    ignorados = IGNORADOS_DE_FABRICA + tuple(patrones_de_gitignore(antes))
    limpio = Arbol()
    for ruta, f in despues.ficheros.items():
        if ruta in antes.ficheros or not casa(ruta, ignorados):
            limpio.ficheros[ruta] = f
    for ruta, motivo in despues.rechazados.items():
        # Un enlace que ya estaba en el repositorio no lo ha creado el agente (no se le copió).
        if ruta not in antes.rechazados and not casa(ruta, ignorados):
            limpio.rechazados[ruta] = motivo
    return limpio


# ── Diff ─────────────────────────────────────────────────────────────────────

def comparar(antes: Arbol, despues: Arbol) -> list[Cambio]:
    cambios: list[Cambio] = []
    for ruta in sorted(set(antes.ficheros) | set(despues.ficheros)):
        a, d = antes.ficheros.get(ruta), despues.ficheros.get(ruta)
        if a is None and d is not None:
            cambios.append(Cambio(ruta, "create", d.contenido, d.ejecutable))
        elif a is not None and d is None:
            cambios.append(Cambio(ruta, "delete"))
        elif a is not None and d is not None and (a.contenido != d.contenido or a.ejecutable != d.ejecutable):
            cambios.append(Cambio(ruta, "update", d.contenido, d.ejecutable))
    return cambios


def es_binario(contenido: Optional[bytes]) -> bool:
    if not contenido:
        return False
    if b"\x00" in contenido[:8192]:
        return True
    try:
        contenido.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _texto(contenido: Optional[bytes]) -> list[str]:
    if not contenido:
        return []
    return contenido.decode("utf-8", errors="replace").splitlines()


def lineas_anadidas(antes: Arbol, cambio: Cambio) -> list[str]:
    if cambio.accion == "delete":
        return []
    viejo = _texto(antes.ficheros[cambio.ruta].contenido) if cambio.ruta in antes.ficheros else []
    nuevo = _texto(cambio.contenido)
    return [linea[1:] for linea in difflib.unified_diff(viejo, nuevo, lineterm="", n=0)
            if linea.startswith("+") and not linea.startswith("+++")]


def diff_unificado(antes: Arbol, cambios: list[Cambio], max_bytes: int = 200_000) -> str:
    """El diff para leer (descripción del PR y pantalla), recortado."""
    trozos, total = [], 0
    for c in cambios:
        viejo = _texto(antes.ficheros[c.ruta].contenido) if c.ruta in antes.ficheros else []
        nuevo = _texto(c.contenido) if c.accion != "delete" else []
        texto = "\n".join(difflib.unified_diff(viejo, nuevo, f"a/{c.ruta}", f"b/{c.ruta}", lineterm=""))
        total += len(texto)
        if total > max_bytes:
            trozos.append("… (diff recortado)")
            break
        trozos.append(texto)
    return "\n".join(trozos)


def resumen(antes: Arbol, cambios: list[Cambio]) -> dict:
    """Ficheros con su acción y líneas añadidas/quitadas (para el ticket y el PR)."""
    ficheros, anadidas, quitadas = [], 0, 0
    for c in cambios:
        viejo = _texto(antes.ficheros[c.ruta].contenido) if c.ruta in antes.ficheros else []
        nuevo = _texto(c.contenido) if c.accion != "delete" else []
        mas = menos = 0
        for linea in difflib.unified_diff(viejo, nuevo, lineterm="", n=0):
            if linea.startswith("+") and not linea.startswith("+++"):
                mas += 1
            elif linea.startswith("-") and not linea.startswith("---"):
                menos += 1
        anadidas, quitadas = anadidas + mas, quitadas + menos
        ficheros.append({"path": c.ruta, "action": c.accion, "added": mas, "removed": menos})
    return {"files": ficheros, "added": anadidas, "removed": quitadas}


# ── Detector de secretos ─────────────────────────────────────────────────────

#: Patrones conocidos (nombre, regex). Simple a propósito: falsos positivos
#: bloquean y una persona lo revisa; un falso negativo lo verá el revisor del PR.
PATRONES_DE_SECRETO: tuple[tuple[str, re.Pattern], ...] = tuple((n, re.compile(p)) for n, p in (
    ("clave_privada", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"),
    ("aws_access_key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("github_token", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    ("gitlab_token", r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),
    ("slack_token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("stripe_key", r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b"),
    ("anthropic_key", r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    ("openai_key", r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b"),
    ("contecflow_key", r"\bnxpm_[A-Za-z0-9_\-]{16,}\b"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    ("credencial_en_url", r"[a-z][a-z0-9+.\-]*://[^/\s:@]{1,64}:[^/\s@]{6,}@"),
    ("asignacion_de_secreto",
     r"(?i)\b(?:api[_-]?key|secret|password|passwd|pwd|token|access[_-]?key|private[_-]?key)\b"
     r"[\"']?\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"),
))


def buscar_secreto(lineas: Iterable[str], literales: Iterable[str] = ()) -> Optional[str]:
    """Nombre del primer patrón encontrado en `lineas` (o `literal` si aparece uno de `literales`)."""
    literales = [x for x in literales if x and len(x) >= 8]
    for linea in lineas:
        for lit in literales:
            if lit in linea:
                return "literal"
        for nombre, patron in PATRONES_DE_SECRETO:
            if patron.search(linea):
                return nombre
    return None


# ── Comprobación ─────────────────────────────────────────────────────────────

@dataclass
class Bloqueo:
    codigo: str
    params: dict


def comprobar(antes: Arbol, despues: Arbol, cambios: list[Cambio], *, protegidos: Iterable[str],
              max_ficheros: int, max_diff_kb: int, literales: Iterable[str] = ()) -> Optional[Bloqueo]:
    """El primer motivo para NO abrir el PR, o None si el diff se puede proponer."""
    for ruta, motivo in sorted(despues.rechazados.items()):
        return Bloqueo("ticket_pr_bloqueo_fichero_no_admitido", {"fichero": ruta[:200], "motivo": motivo})
    if not cambios:
        return Bloqueo("ticket_pr_sin_cambios", {})
    if len(cambios) > max_ficheros:
        return Bloqueo("ticket_pr_bloqueo_demasiados_ficheros", {"n": len(cambios), "max": max_ficheros})
    protegidos = tuple(protegidos)
    for c in cambios:
        patron = casa(c.ruta, protegidos)
        if patron:
            return Bloqueo("ticket_pr_bloqueo_fichero_protegido", {"fichero": c.ruta[:200], "patron": patron})
    total = 0
    for c in cambios:
        if c.accion != "delete" and es_binario(c.contenido):
            return Bloqueo("ticket_pr_bloqueo_binario", {"fichero": c.ruta[:200]})
        total += len(c.contenido or b"")
    if total > max_diff_kb * 1024:
        return Bloqueo("ticket_pr_bloqueo_diff_grande", {"kb": total // 1024, "max": max_diff_kb})
    literales = tuple(literales)
    for c in cambios:
        tipo = buscar_secreto(lineas_anadidas(antes, c), literales)
        if tipo:
            return Bloqueo("ticket_pr_bloqueo_secreto", {"fichero": c.ruta[:200], "tipo": tipo})
    return None
