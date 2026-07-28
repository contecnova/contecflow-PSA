import ast
from pathlib import Path


# Legacy async handlers that still use sync DB access.
# Keep this list explicit so new files cannot add the same pattern silently.
LEGACY_ASYNC_DB_ENDPOINT_FILES = {
    "activity.py",
    "ai_chat.py",
    "cab.py",
    "documents_collab.py",
    "esign.py",
    "git_integration.py",
    "integrations_hub.py",
    "m365.py",  # external-integration async module (Graph API) — same pattern, pending async-DB migration
    # "v238_features.py",  # Eliminado: archivo no existe
}


def test_async_endpoints_do_not_use_sync_db_session() -> None:
    """Ensure async endpoint handlers do not depend on get_db() directly."""
    endpoint_dir = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints"

    failing_files = []
    for path in sorted(endpoint_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found_async_with_sync_db = False

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            total_args = len(node.args.args)
            defaults = node.args.defaults
            defaults_start = total_args - len(defaults)

            has_sync_db_dep = False
            for idx, arg in enumerate(node.args.args):
                if arg.arg != "db" or idx < defaults_start:
                    continue

                default = defaults[idx - defaults_start]
                if (
                    isinstance(default, ast.Call)
                    and isinstance(default.func, ast.Name)
                    and default.func.id == "Depends"
                    and default.args
                    and isinstance(default.args[0], ast.Name)
                    and default.args[0].id == "get_db"
                ):
                    has_sync_db_dep = True
                    break

            if not has_sync_db_dep:
                continue

            # Cumple si el acceso síncrono a BD se hace vía el wrapper de threadpool
            # `run_db(...)` (patrón explícitamente aceptado por este guard): no bloquea
            # el event loop aunque el handler sea async. Solo se marca si usa `db`
            # directamente sin threadpool.
            uses_run_db = any(
                isinstance(inner, ast.Call)
                and (
                    (isinstance(inner.func, ast.Name) and inner.func.id == "run_db")
                    or (isinstance(inner.func, ast.Attribute) and inner.func.attr == "run_db")
                )
                for inner in ast.walk(node)
            )
            if uses_run_db:
                continue

            found_async_with_sync_db = True
            break

        if found_async_with_sync_db:
            failing_files.append(path.name)

    unexpected_files = sorted(set(failing_files) - LEGACY_ASYNC_DB_ENDPOINT_FILES)

    assert unexpected_files == [], (
        "New async endpoint handlers must not depend on sync get_db() directly. "
        "Convert them to sync endpoints or use an explicit threadpool wrapper. "
        "Legacy files are temporarily allowlisted until migrated. "
        f"Unexpected files: {', '.join(unexpected_files)}"
    )
