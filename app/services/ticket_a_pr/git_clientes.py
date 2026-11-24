"""Clientes Git (GitHub y GitLab) para «Del ticket al PR», detrás de una interfaz.

Todo por la API HTTP del proveedor y desde el servidor (por el validador único
de salidas `app/core/outbound_url.py`): el contenedor del agente nunca recibe una
credencial de Git ni habla con el host Git.

- **GitHub**: GitHub App de la empresa. Por ejecución se pide un **token de
  instalación** (1 h) limitado a ESE repositorio y a los permisos mínimos
  `contents: write`, `pull_requests: write`, `statuses: write`. La rama
  protegida la protege GitHub (reglas de rama: exigir el estado
  `contecflow/cab` y revisión); contecflow solo crea `contecflow/...`.
- **GitLab**: token de proyecto (rol Developer, alcance `api`) guardado cifrado.
  Las ramas protegidas no admiten push de Developer; el MR se abre como
  «Draft:» (GitLab no deja fusionar un borrador) y con el estado
  `contecflow/cab` («Pipelines must succeed»).

Operaciones: rama base → sha; tar del árbol en ese sha; rama nueva con un
commit (blobs/árbol/commit/ref en GitHub; API de commits en GitLab); abrir PR;
publicar el estado del CAB; leer el estado del PR; prueba de credenciales.
`ClienteGitSimulado` es el de los tests.
"""
from __future__ import annotations

import base64
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

from app.services.ticket_a_pr.diff import Cambio

logger = logging.getLogger(__name__)

CONTEXTO_DE_ESTADO = "contecflow/cab"
ESTADOS = ("pending", "success", "failure")


class ErrorGit(RuntimeError):
    """Fallo del proveedor Git, con código del catálogo y el estado HTTP (sin el cuerpo remoto)."""

    def __init__(self, codigo: str, estado: Optional[int] = None, paso: str = ""):
        super().__init__(f"{codigo} {paso} {estado or ''}".strip())
        self.codigo, self.estado, self.paso = codigo, estado, paso

    @property
    def params(self) -> dict:
        return {"paso": self.paso, "estado": self.estado or 0}


class ClienteGit(ABC):
    proveedor: str = ""

    @abstractmethod
    def sha_de_rama(self, repo: str, rama: str) -> str: ...

    @abstractmethod
    def descargar(self, repo: str, sha: str) -> bytes: ...

    @abstractmethod
    def publicar(self, repo: str, base_sha: str, rama: str, cambios: list[Cambio], mensaje: str) -> str: ...

    @abstractmethod
    def abrir_pr(self, repo: str, rama: str, base: str, titulo: str, cuerpo: str) -> tuple[int, str]: ...

    @abstractmethod
    def actualizar_pr(self, repo: str, numero: int, *, cuerpo: Optional[str] = None,
                      listo: Optional[bool] = None) -> None: ...

    @abstractmethod
    def poner_estado(self, repo: str, sha: str, estado: str, descripcion: str, url: str) -> None: ...

    @abstractmethod
    def estado_pr(self, repo: str, numero: int) -> str:
        """open | merged | closed"""

    @abstractmethod
    def probar(self, repo: Optional[str]) -> dict:
        """{"ok", "detail", "verificado"}: credencial válida y, con `repo`, acceso a ese repositorio."""


def _cliente_http(defecto: float = 30):
    """Cliente HTTP del proveedor git. La espera es `OUTBOUND_HTTP_TIMEOUT_SECONDS`
    si el operador la fija; si no, `defecto` (300 s para descargar el código,
    120 s para publicar, 30 s el resto)."""
    from app.core.outbound_url import cliente_httpx
    from app.services.settings_service import outbound_http_timeout
    return cliente_httpx(timeout=outbound_http_timeout(default=defecto), follow_redirects=True)


def _exigir(r, codigo: str, paso: str, *esperados: int) -> None:
    if r.status_code not in (esperados or (200,)):
        raise ErrorGit(codigo, r.status_code, paso)


# ── GitHub ───────────────────────────────────────────────────────────────────

@dataclass
class ClienteGitHub(ClienteGit):
    app_id: str
    installation_id: str
    private_key: str
    api_url: str = "https://api.github.com"
    _token: Optional[str] = field(default=None, repr=False)
    _repo_del_token: Optional[str] = field(default=None, repr=False)

    proveedor = "github"

    def __repr__(self) -> str:
        return f"ClienteGitHub(app={self.app_id}, instalacion={self.installation_id})"

    def _jwt(self) -> str:
        import jwt
        ahora = int(time.time())
        return jwt.encode({"iat": ahora - 60, "exp": ahora + 540, "iss": str(self.app_id)}, self.private_key,
                          algorithm="RS256")

    def _token_para(self, repo: str) -> str:
        """Token de instalación limitado a `repo` y a los permisos mínimos (no se guarda)."""
        if self._token and self._repo_del_token == repo:
            return self._token
        nombre = repo.split("/", 1)[-1]
        with _cliente_http() as c:
            r = c.post(f"{self.api_url.rstrip('/')}/app/installations/{self.installation_id}/access_tokens",
                       headers={"Authorization": f"Bearer {self._jwt()}", "Accept": "application/vnd.github+json"},
                       json={"repositories": [nombre],
                             "permissions": {"contents": "write", "pull_requests": "write", "statuses": "write"}})
        _exigir(r, "ticket_pr_git_credencial", "token", 201)
        self._token, self._repo_del_token = r.json()["token"], repo
        return self._token

    def _h(self, repo: str) -> dict:
        return {"Authorization": f"Bearer {self._token_para(repo)}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def _url(self, repo: str, ruta: str) -> str:
        return f"{self.api_url.rstrip('/')}/repos/{repo}{ruta}"

    def sha_de_rama(self, repo: str, rama: str) -> str:
        with _cliente_http() as c:
            r = c.get(self._url(repo, f"/git/ref/heads/{quote(rama, safe='/')}"), headers=self._h(repo))
        _exigir(r, "ticket_pr_git_rama_no_encontrada", "rama")
        return r.json()["object"]["sha"]

    def descargar(self, repo: str, sha: str) -> bytes:
        with _cliente_http(defecto=300) as c:
            r = c.get(self._url(repo, f"/tarball/{sha}"), headers=self._h(repo))
        _exigir(r, "ticket_pr_git_descarga", "tarball")
        return r.content

    def publicar(self, repo: str, base_sha: str, rama: str, cambios: list[Cambio], mensaje: str) -> str:
        h = self._h(repo)
        with _cliente_http(defecto=120) as c:
            r = c.get(self._url(repo, f"/git/commits/{base_sha}"), headers=h)
            _exigir(r, "ticket_pr_git_publicar", "commit base")
            arbol_base = r.json()["tree"]["sha"]
            entradas = []
            for cambio in cambios:
                if cambio.accion == "delete":
                    entradas.append({"path": cambio.ruta, "mode": "100644", "type": "blob", "sha": None})
                    continue
                r = c.post(self._url(repo, "/git/blobs"), headers=h,
                           json={"content": base64.b64encode(cambio.contenido or b"").decode(), "encoding": "base64"})
                _exigir(r, "ticket_pr_git_publicar", "blob", 201)
                entradas.append({"path": cambio.ruta, "mode": "100755" if cambio.ejecutable else "100644",
                                 "type": "blob", "sha": r.json()["sha"]})
            r = c.post(self._url(repo, "/git/trees"), headers=h, json={"base_tree": arbol_base, "tree": entradas})
            _exigir(r, "ticket_pr_git_publicar", "tree", 201)
            r = c.post(self._url(repo, "/git/commits"), headers=h,
                       json={"message": mensaje, "tree": r.json()["sha"], "parents": [base_sha]})
            _exigir(r, "ticket_pr_git_publicar", "commit", 201)
            sha = r.json()["sha"]
            # La rama es nueva: si ya existe, falla (nunca se reescribe una rama, y menos la protegida).
            r = c.post(self._url(repo, "/git/refs"), headers=h, json={"ref": f"refs/heads/{rama}", "sha": sha})
            _exigir(r, "ticket_pr_git_publicar", "ref", 201)
        return sha

    def abrir_pr(self, repo: str, rama: str, base: str, titulo: str, cuerpo: str) -> tuple[int, str]:
        with _cliente_http() as c:
            r = c.post(self._url(repo, "/pulls"), headers=self._h(repo),
                       json={"title": titulo[:250], "head": rama, "base": base, "body": cuerpo[:60000],
                             "maintainer_can_modify": False})
        _exigir(r, "ticket_pr_git_pr", "pull", 201)
        datos = r.json()
        return int(datos["number"]), str(datos["html_url"])

    def actualizar_pr(self, repo: str, numero: int, *, cuerpo: Optional[str] = None,
                      listo: Optional[bool] = None) -> None:
        if cuerpo is None:
            return                      # en GitHub el merge lo bloquea el estado, no el borrador
        with _cliente_http() as c:
            r = c.patch(self._url(repo, f"/pulls/{numero}"), headers=self._h(repo), json={"body": cuerpo[:60000]})
        _exigir(r, "ticket_pr_git_pr", "pull update")

    def poner_estado(self, repo: str, sha: str, estado: str, descripcion: str, url: str) -> None:
        with _cliente_http() as c:
            r = c.post(self._url(repo, f"/statuses/{sha}"), headers=self._h(repo),
                       json={"state": estado, "description": descripcion[:139], "context": CONTEXTO_DE_ESTADO,
                             "target_url": url or None})
        _exigir(r, "ticket_pr_git_estado", "status", 201)

    def estado_pr(self, repo: str, numero: int) -> str:
        with _cliente_http() as c:
            r = c.get(self._url(repo, f"/pulls/{numero}"), headers=self._h(repo))
        _exigir(r, "ticket_pr_git_pr", "pull get")
        d = r.json()
        return "merged" if d.get("merged") else ("closed" if d.get("state") == "closed" else "open")

    def probar(self, repo: Optional[str]) -> dict:
        with _cliente_http() as c:
            r = c.get(f"{self.api_url.rstrip('/')}/app/installations/{self.installation_id}",
                      headers={"Authorization": f"Bearer {self._jwt()}", "Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            return {"ok": False, "verificado": "nada", "detail": f"GitHub App HTTP {r.status_code}"}
        if not repo:
            return {"ok": True, "verificado": "credencial", "detail": "GitHub App e instalación válidas"}
        try:
            self._token_para(repo)
            with _cliente_http() as c:
                r = c.get(self._url(repo, ""), headers=self._h(repo))
        except ErrorGit as e:
            return {"ok": False, "verificado": "credencial", "detail": f"GitHub token {e.estado}"}
        if r.status_code != 200:
            return {"ok": False, "verificado": "credencial", "detail": f"GitHub repo HTTP {r.status_code}"}
        return {"ok": True, "verificado": "credencial_y_uso", "detail": f"Token de instalación para {repo}"}


# ── GitLab ───────────────────────────────────────────────────────────────────

@dataclass
class ClienteGitLab(ClienteGit):
    token: str
    base_url: str = "https://gitlab.com"

    proveedor = "gitlab"

    def __repr__(self) -> str:
        return f"ClienteGitLab({self.base_url})"

    def _h(self) -> dict:
        return {"PRIVATE-TOKEN": self.token}

    def _url(self, repo: str, ruta: str) -> str:
        return f"{self.base_url.rstrip('/')}/api/v4/projects/{quote(repo, safe='')}{ruta}"

    def sha_de_rama(self, repo: str, rama: str) -> str:
        with _cliente_http() as c:
            r = c.get(self._url(repo, f"/repository/branches/{quote(rama, safe='')}"), headers=self._h())
        _exigir(r, "ticket_pr_git_rama_no_encontrada", "rama")
        return r.json()["commit"]["id"]

    def descargar(self, repo: str, sha: str) -> bytes:
        with _cliente_http(defecto=300) as c:
            r = c.get(self._url(repo, "/repository/archive.tar.gz"), params={"sha": sha}, headers=self._h())
        _exigir(r, "ticket_pr_git_descarga", "archive")
        return r.content

    def publicar(self, repo: str, base_sha: str, rama: str, cambios: list[Cambio], mensaje: str) -> str:
        acciones = []
        for cambio in cambios:
            if cambio.accion == "delete":
                acciones.append({"action": "delete", "file_path": cambio.ruta})
            else:
                acciones.append({"action": cambio.accion, "file_path": cambio.ruta, "encoding": "base64",
                                 "content": base64.b64encode(cambio.contenido or b"").decode(),
                                 "execute_filemode": bool(cambio.ejecutable)})
        with _cliente_http(defecto=120) as c:
            # `branch` nueva desde `start_sha`: GitLab la crea; si ya existe, falla.
            r = c.post(self._url(repo, "/repository/commits"), headers=self._h(),
                       json={"branch": rama, "start_sha": base_sha, "commit_message": mensaje, "actions": acciones})
        _exigir(r, "ticket_pr_git_publicar", "commits", 201)
        return r.json()["id"]

    def abrir_pr(self, repo: str, rama: str, base: str, titulo: str, cuerpo: str) -> tuple[int, str]:
        with _cliente_http() as c:
            r = c.post(self._url(repo, "/merge_requests"), headers=self._h(),
                       json={"source_branch": rama, "target_branch": base, "title": f"Draft: {titulo}"[:250],
                             "description": cuerpo[:60000], "remove_source_branch": True})
        _exigir(r, "ticket_pr_git_pr", "merge request", 201)
        d = r.json()
        return int(d["iid"]), str(d["web_url"])

    def actualizar_pr(self, repo: str, numero: int, *, cuerpo: Optional[str] = None,
                      listo: Optional[bool] = None) -> None:
        datos: dict = {}
        if cuerpo is not None:
            datos["description"] = cuerpo[:60000]
        with _cliente_http() as c:
            if listo is not None:
                r = c.get(self._url(repo, f"/merge_requests/{numero}"), headers=self._h())
                _exigir(r, "ticket_pr_git_pr", "merge request get")
                titulo = str(r.json().get("title") or "")
                sin = titulo[len("Draft: "):] if titulo.startswith("Draft: ") else titulo
                datos["title"] = sin if listo else f"Draft: {sin}"
            if datos:
                r = c.put(self._url(repo, f"/merge_requests/{numero}"), headers=self._h(), json=datos)
                _exigir(r, "ticket_pr_git_pr", "merge request update")

    def poner_estado(self, repo: str, sha: str, estado: str, descripcion: str, url: str) -> None:
        gl = {"pending": "pending", "success": "success", "failure": "failed"}[estado]
        with _cliente_http() as c:
            r = c.post(self._url(repo, f"/statuses/{sha}"), headers=self._h(),
                       json={"state": gl, "name": CONTEXTO_DE_ESTADO, "description": descripcion[:255],
                             "target_url": url or None})
        _exigir(r, "ticket_pr_git_estado", "status", 200, 201)

    def estado_pr(self, repo: str, numero: int) -> str:
        with _cliente_http() as c:
            r = c.get(self._url(repo, f"/merge_requests/{numero}"), headers=self._h())
        _exigir(r, "ticket_pr_git_pr", "merge request get")
        estado = r.json().get("state")
        return "merged" if estado == "merged" else ("closed" if estado in ("closed", "locked") else "open")

    def probar(self, repo: Optional[str]) -> dict:
        with _cliente_http() as c:
            r = c.get(f"{self.base_url.rstrip('/')}/api/v4/personal_access_tokens/self", headers=self._h())
            if r.status_code != 200:
                return {"ok": False, "verificado": "nada", "detail": f"GitLab token HTTP {r.status_code}"}
            if not repo:
                return {"ok": True, "verificado": "credencial", "detail": "Token de GitLab válido"}
            r = c.get(self._url(repo, ""), headers=self._h())
        if r.status_code != 200:
            return {"ok": False, "verificado": "credencial", "detail": f"GitLab proyecto HTTP {r.status_code}"}
        return {"ok": True, "verificado": "credencial_y_uso", "detail": f"Acceso al proyecto {repo}"}


# ── Simulado (tests) ─────────────────────────────────────────────────────────

class ClienteGitSimulado(ClienteGit):
    """Repositorio en memoria: `ficheros` del árbol base; registra lo publicado, los PR y los estados."""

    def __init__(self, ficheros: Optional[dict[str, bytes]] = None, proveedor: str = "github"):
        self.proveedor = proveedor
        self.ficheros = ficheros if ficheros is not None else {"app.py": b"print('roto')\n", "README.md": b"# demo\n"}
        self.publicados: list[dict] = []
        self.prs: list[dict] = []
        self.estados: list[dict] = []
        self.actualizaciones: list[dict] = []
        self.estado = "open"

    def sha_de_rama(self, repo: str, rama: str) -> str:
        return "a" * 40

    def descargar(self, repo: str, sha: str) -> bytes:
        import io
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for ruta, contenido in self.ficheros.items():
                info = tarfile.TarInfo(f"owner-repo-{sha[:7]}/{ruta}")
                info.size = len(contenido)
                tar.addfile(info, io.BytesIO(contenido))
        return buf.getvalue()

    def publicar(self, repo: str, base_sha: str, rama: str, cambios: list[Cambio], mensaje: str) -> str:
        self.publicados.append({"repo": repo, "base": base_sha, "rama": rama, "mensaje": mensaje,
                                "cambios": [(c.ruta, c.accion) for c in cambios]})
        return "b" * 40

    def abrir_pr(self, repo: str, rama: str, base: str, titulo: str, cuerpo: str) -> tuple[int, str]:
        self.prs.append({"repo": repo, "rama": rama, "base": base, "titulo": titulo, "cuerpo": cuerpo})
        return len(self.prs), f"https://git.example/{repo}/pull/{len(self.prs)}"

    def actualizar_pr(self, repo: str, numero: int, *, cuerpo: Optional[str] = None,
                      listo: Optional[bool] = None) -> None:
        self.actualizaciones.append({"numero": numero, "cuerpo": cuerpo, "listo": listo})

    def poner_estado(self, repo: str, sha: str, estado: str, descripcion: str, url: str) -> None:
        self.estados.append({"sha": sha, "estado": estado, "descripcion": descripcion})

    def estado_pr(self, repo: str, numero: int) -> str:
        return self.estado

    def probar(self, repo: Optional[str]) -> dict:
        return {"ok": True, "verificado": "credencial_y_uso", "detail": "simulado"}


_forzado: Optional[ClienteGit] = None


def forzar_cliente(cliente: Optional[ClienteGit]) -> None:
    """Los tests fijan un cliente simulado (sin red ni credenciales)."""
    global _forzado
    _forzado = cliente


def cliente_para(proveedor: str, credenciales: dict) -> ClienteGit:
    """El cliente del proveedor con las credenciales de la empresa; 409 si faltan."""
    from app.core.codigos_de_error import ErrorConCodigo
    if _forzado is not None:
        return _forzado
    if proveedor == "github":
        app_id, inst, clave = (credenciales.get("github_app_id"), credenciales.get("github_installation_id"),
                               credenciales.get("github_private_key"))
        if not (app_id and inst and clave):
            raise ErrorConCodigo("ticket_pr_git_sin_credencial", proveedor="GitHub")
        return ClienteGitHub(str(app_id), str(inst), str(clave),
                             str(credenciales.get("github_api_url") or "https://api.github.com"))
    if proveedor == "gitlab":
        token = credenciales.get("gitlab_token")
        if not token:
            raise ErrorConCodigo("ticket_pr_git_sin_credencial", proveedor="GitLab")
        return ClienteGitLab(str(token), str(credenciales.get("gitlab_base_url") or "https://gitlab.com"))
    raise ErrorConCodigo("ticket_pr_proveedor_git_no_valido", proveedor=str(proveedor)[:20])
