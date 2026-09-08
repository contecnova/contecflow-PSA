#!/usr/bin/env python3
"""Quick static audit for tenant isolation patterns in app/services.

Flags candidate lines where a query is created without obvious scoping helpers.
This is conservative and intended as a review aid, not a strict proof.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import re

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "app" / "services"

QUERY_RE = re.compile(r"\bdb\.query\(")
SAFE_HINTS = (
    "organization_id",
    "_scoped(",
    "_scope_",
    "org_id",
    "is_superadmin",
    "tenant",
    # Ayudante real de este repositorio: devuelve la organizacion del sujeto
    # y lanza 403 si no tiene. Faltaba, asi que toda consulta acotada con el
    # se marcaba como sospechosa.
    "_org(",
)

#: Cuantas lineas se miran hacia atras desde el `db.query(` para reconocer el
#: ambito. Una consulta acotada suele venir precedida de la resolucion de la
#: organizacion, no seguida.
LINEAS_DE_CONTEXTO_ANTERIOR = 3

#: Suelo de lineas posteriores. La ventana es la sentencia completa, pero
#: nunca menos que esto: asi domina estrictamente a la ventana fija anterior
#: y el cambio no puede hacer aparecer avisos que antes no salian.
LINEAS_DE_CONTEXTO_POSTERIOR = 3


def _statement_window(lines: list[str], index: int) -> str:
    """La sentencia completa que arranca en `index`, mas su contexto anterior.

    Auditoria 2026-08: antes la ventana era fija, `lines[i-3:i+3]`. Una consulta
    encadenada —`db.query(X)` en una linea y `.filter(X.organization_id == ...)`
    cuatro mas abajo, que es el estilo de casi todo el repositorio— caia fuera
    de la ventana y se marcaba como sin acotar. Medido sobre
    `app/services/collaboration`: **93 de 118 avisos eran ese falso positivo**,
    y con ese ruido el gate no se puede leer.

    Se sigue el balance de parentesis hasta cerrar la sentencia, asi que la
    ventana es la que el codigo define y no un numero de lineas.
    """
    inicio = max(0, index - LINEAS_DE_CONTEXTO_ANTERIOR)
    fin = min(len(lines), index + LINEAS_DE_CONTEXTO_POSTERIOR)
    saldo = 0
    for pos in range(index, len(lines)):
        linea = lines[pos]
        saldo += linea.count(chr(40)) - linea.count(chr(41))
        if pos > index and saldo <= 0:
            fin = max(fin, pos + 1)
            break
    else:
        fin = len(lines)
    return chr(10).join(lines[inicio:fin])


def _normalize_identifier(rel: Path, src: str) -> str:
    """Identificador estable de un hallazgo, comparable entre plataformas.

    Auditoria 2026-08: aqui se interpolaba el `Path` directamente, y en Windows
    eso serializa con la barra invertida, mientras el baseline se escribio con
    `/`. Resultado:
    NINGUNA linea del baseline coincidia y `--strict` daba STRICT FAIL con los
    2.334 hallazgos ya revisados marcados como nuevos. El gate no podia pasar
    nunca en Windows, asi que no informaba de nada. `as_posix()` fija la forma.
    """
    normalized_src = re.sub(r"\s+", " ", src.strip())
    return f"{rel.as_posix()}:{normalized_src}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Static tenant isolation audit")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit code when candidate lines are found.",
    )
    parser.add_argument(
        "--baseline",
        default=str((ROOT / "scripts" / "tenant_audit_baseline.txt").resolve()),
        help="Path to baseline file with known findings.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write current findings into baseline file and exit 0.",
    )
    args = parser.parse_args()

    total_queries = 0
    flagged: list[tuple[Path, int, str]] = []

    for path in SERVICES.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if not QUERY_RE.search(line):
                continue
            total_queries += 1
            window = _statement_window(lines, i - 1)
            if not any(hint in window for hint in SAFE_HINTS):
                flagged.append((path.relative_to(ROOT), i, line.strip()))

    identifiers = [_normalize_identifier(rel, src) for rel, _, src in flagged]

    if args.write_baseline:
        baseline_path = Path(args.baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text("\n".join(sorted(identifiers)) + "\n", encoding="utf-8")
        print(f"[tenant-audit] baseline written: {baseline_path}")
        print(f"[tenant-audit] baseline entries: {len(identifiers)}")
        return 0

    print(f"[tenant-audit] total queries scanned: {total_queries}")
    print(f"[tenant-audit] candidates to review: {len(flagged)}")
    for rel, line_no, src in flagged[:200]:
        print(f"- {rel}:{line_no}: {src}")
    if len(flagged) > 200:
        print(f"[tenant-audit] ... y {len(flagged) - 200} más (listado truncado a 200)")

    if flagged:
        if args.strict:
            baseline_path = Path(args.baseline)
            baseline_entries: set[str] = set()
            if baseline_path.exists():
                baseline_entries = {
                    line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines() if line.strip()
                }
            new_entries = sorted(set(identifiers) - baseline_entries)
            print(f"[tenant-audit] baseline entries: {len(baseline_entries)}")
            print(f"[tenant-audit] new entries: {len(new_entries)}")
            for item in new_entries[:200]:
                print(f"+ {item}")
            if len(new_entries) > 200:
                print(f"[tenant-audit] ... y {len(new_entries) - 200} más (listado truncado a 200)")
            if new_entries:
                print("[tenant-audit] STRICT FAIL: new unreviewed tenant findings detected.")
                return 1

        print("[tenant-audit] REVIEW REQUIRED: found query sites without obvious tenant hint.")
        return 0

    print("[tenant-audit] OK: no obvious unscoped query sites found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
