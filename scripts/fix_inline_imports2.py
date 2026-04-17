"""
fix_inline_imports2.py — Move inline `from X import Y [as Z]` statements
from function bodies to module-level in all app/services/**/*.py files.

Strategy (AST-based):
  1. Parse module-level imports via AST.
  2. Scan for indented `from X import ...` nodes (inside functions).
     - Skip nodes inside `if TYPE_CHECKING:` blocks.
     - Skip nodes directly inside `try:` blocks (conditional imports).
     - Build canonical names_str from AST node.names (handles multi-line).
  3. For each unique inline import not already at module level, add it
     after the last existing top-level import block.
  4. Remove (strip) all inline import lines from function bodies.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SERVICES = ROOT / "app" / "services"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _names_str_from_node(node: ast.ImportFrom) -> str:
    """Build canonical names string from AST ImportFrom node (alias-preserving)."""
    return ", ".join(
        (f"{a.name} as {a.asname}" if a.asname else a.name)
        for a in node.names
    )


def _canonical_key(module: str, names_str: str) -> str:
    """Stable dict key that normalises whitespace."""
    return f"from {module} import {re.sub(r'\\s+', ' ', names_str)}"


def _last_module_import_line(source: str) -> int:
    """Return 0-based index of the last line belonging to a module-level
    import statement (accounts for multi-line parenthesised imports).
    Returns -1 if no imports found.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fallback: scan raw lines
        last = -1
        for i, line in enumerate(source.splitlines()):
            if line.startswith("from ") or line.startswith("import "):
                last = i
        return last

    last = -1
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            end = getattr(node, "end_lineno", node.lineno) - 1  # 0-based
            if end > last:
                last = end
    return last


def _collect_try_block_linenos(tree: ast.AST) -> set[int]:
    """Collect line numbers of ALL nodes inside any try/except/else/finally
    construct.  Imports inside these blocks are intentional conditional
    imports and must not be moved."""
    linenos: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            sections = list(node.body) + list(node.orelse) + list(node.finalbody)
            for handler in node.handlers:
                sections.extend(handler.body)
            for child in sections:
                for n in ast.walk(child):
                    if hasattr(n, "lineno"):
                        linenos.add(n.lineno)
    return linenos


def fix_file(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)

    # ── Phase 1: use AST to find inline from-imports ──────────────────────
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False  # Don't touch files that already have syntax errors

    # Collect TYPE_CHECKING block line numbers so we can exclude them
    type_checking_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
            )
            if is_tc:
                for child in ast.walk(node):
                    if hasattr(child, "lineno"):
                        type_checking_lines.add(child.lineno)

    # Collect line numbers inside try-body blocks (skip those — conditional imports)
    try_body_linenos = _collect_try_block_linenos(tree)

    # Inline import line numbers (1-based) → set
    inline_linenos: set[int] = set()
    inline_imports: list[tuple[str, str]] = []   # [(module, names_str), ...]
    seen_keys: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.col_offset == 0:
            continue  # module-level, skip
        if node.lineno in type_checking_lines:
            continue  # inside TYPE_CHECKING, skip
        if node.lineno in try_body_linenos:
            continue  # inside try: block — conditional import, skip
        # Mark all lines of this import as inline
        for lineno in range(node.lineno, getattr(node, "end_lineno", node.lineno) + 1):
            inline_linenos.add(lineno)
        # Build names_str from AST node (handles multi-line imports correctly)
        module = node.module or ""
        names_str = _names_str_from_node(node)
        key = _canonical_key(module, names_str)
        if key not in seen_keys:
            seen_keys.add(key)
            inline_imports.append((module, names_str))

    if not inline_imports:
        return False

    # ── Phase 2: determine which are already at module level ──────────────
    existing_module_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names_str = _names_str_from_node(node)
            existing_module_imports.add(_canonical_key(mod, names_str))
        elif isinstance(node, ast.Import):
            for a in node.names:
                existing_module_imports.add(f"import {a.name}")

    to_add = [
        (mod, names)
        for mod, names in inline_imports
        if _canonical_key(mod, names) not in existing_module_imports
    ]

    # ── Phase 3: remove inline from-import lines ──────────────────────────
    new_lines = [
        line for i, line in enumerate(lines)
        if (i + 1) not in inline_linenos  # 1-based
    ]

    # ── Phase 4: insert new module-level imports ───────────────────────────
    if to_add:
        cleaned_source = "".join(new_lines)
        insert_after = _last_module_import_line(cleaned_source)
        new_import_text = "".join(
            f"from {mod} import {names}\n"
            for mod, names in sorted(to_add, key=lambda x: x[0])
        )
        if insert_after == -1:
            new_lines.insert(0, new_import_text)
        else:
            new_lines.insert(insert_after + 1, new_import_text)

    result = "".join(new_lines)
    if result == source:
        return False

    path.write_text(result, encoding="utf-8")
    return True


def main() -> None:
    files = list(SERVICES.rglob("*.py"))
    changed = []
    errors = []
    for f in sorted(files):
        try:
            if fix_file(f):
                changed.append(f.relative_to(ROOT))
        except Exception as exc:
            errors.append((f.relative_to(ROOT), exc))

    print(f"\nFixed {len(changed)} files:")
    for p in changed:
        print(f"  {p}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for p, e in errors:
            print(f"  {p}: {e}")


if __name__ == "__main__":
    main()
