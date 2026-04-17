"""
fix_inline_imports.py — Move all inline `from X import Y` statements
that appear inside function/method bodies (indented) to module-level imports.

Only touches files under app/services/. Safe to re-run (idempotent).
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SERVICES = ROOT / "app" / "services"


def _collect_inline_imports(source: str) -> dict[str, set[str]]:
    """
    Parse *source* and return {module: {names}} for every import statement
    that appears at indentation > 0 (i.e., inside a function/class body).
    Excludes imports inside `if TYPE_CHECKING:` blocks.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    # Find all TYPE_CHECKING blocks to exclude
    type_checking_linenos: set[int] = set()
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
                        type_checking_linenos.add(child.lineno)

    lines = source.splitlines()
    imports: dict[str, set[str]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        lineno = node.lineno
        if lineno in type_checking_linenos:
            continue
        # Check if this import is indented (inside a function)
        line = lines[lineno - 1]
        if not line.startswith((" ", "\t")):
            continue  # already at module level

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {alias.asname if alias.asname else alias.name for alias in node.names}
            if module not in imports:
                imports[module] = set()
            imports[module] |= names
        else:
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                module = name  # `import foo` → treat as module = foo, name = foo
                if module not in imports:
                    imports[module] = set()
                imports[module].add(name)

    return imports


def _build_import_lines(module: str, names: set[str]) -> list[str]:
    sorted_names = sorted(names)
    joined = ", ".join(sorted_names)
    return [f"from {module} import {joined}"]


def _remove_inline_import_lines(source: str) -> str:
    """
    Strip lines that are indented `from X import ...` / `import X` statements
    (i.e., inline imports inside function bodies).
    Leave TYPE_CHECKING blocks alone.
    """
    lines = source.splitlines(keepends=True)
    result = []
    in_type_checking = False
    tc_indent: int | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n").rstrip()

        # Detect `if TYPE_CHECKING:` block start
        if re.match(r"^(\s*)if\s+TYPE_CHECKING\s*:", stripped):
            indent = len(stripped) - len(stripped.lstrip())
            in_type_checking = True
            tc_indent = indent
            result.append(line)
            i += 1
            continue

        # Detect end of TYPE_CHECKING block
        if in_type_checking and tc_indent is not None:
            current_indent = len(line) - len(line.lstrip()) if line.strip() else None
            if current_indent is not None and current_indent <= tc_indent and line.strip():
                in_type_checking = False
                tc_indent = None

        if in_type_checking:
            result.append(line)
            i += 1
            continue

        # Check if it's an indented import line
        lstripped = line.lstrip()
        if (line.startswith((" ", "\t")) and
                (lstripped.startswith("from ") or lstripped.startswith("import ")) and
                " import " in lstripped):
            # Handle line continuations (backslash or parentheses)
            # Just drop the line (and any continuation)
            while line.rstrip().endswith("\\"):
                i += 1
                if i < len(lines):
                    line = lines[i]
                else:
                    break
            # Skip open-paren multi-line imports
            if "(" in lstripped and ")" not in lstripped:
                while ")" not in (lines[i] if i < len(lines) else ")"):
                    i += 1
            i += 1
            continue

        result.append(line)
        i += 1

    return "".join(result)


def _insert_imports_after_existing(source: str, new_imports: dict[str, set[str]]) -> str:
    """
    Insert missing module-level imports into *source*.
    Places them after the last existing `import` / `from ... import` block
    at module level (col 0).
    """
    lines = source.splitlines(keepends=True)

    # Gather already-present module-level imports so we don't duplicate
    existing: dict[str, set[str]] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {alias.asname if alias.asname else alias.name for alias in node.names}
            if module not in existing:
                existing[module] = set()
            existing[module] |= names
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name
                if name not in existing:
                    existing[name] = set()
                existing[name].add(name)

    # Compute what still needs to be added
    to_add: dict[str, set[str]] = {}
    for module, names in new_imports.items():
        missing = names - existing.get(module, set())
        if missing:
            to_add[module] = missing

    if not to_add:
        return source

    # Find insertion point: after last module-level import line
    last_import_lineno = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # end_lineno handles multi-line imports
            last_import_lineno = getattr(node, "end_lineno", node.lineno)

    if last_import_lineno == 0:
        # No existing imports — insert after module docstring / __future__
        insert_at = 0
        for node in tree.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                insert_at = node.end_lineno
                break
    else:
        insert_at = last_import_lineno  # 1-based

    new_lines = []
    for module, names in sorted(to_add.items()):
        # If the module already exists at top level with SOME names, append to it
        # For simplicity, always add as a new import line
        new_lines.append("".join(_build_import_lines(module, names)) + "\n")

    # Insert after line `insert_at` (1-based index → 0-based slice)
    lines.insert(insert_at, "".join(new_lines))
    return "".join(lines)


def fix_file(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")

    inline = _collect_inline_imports(source)
    if not inline:
        return False

    # Step 1: remove all inline import lines
    cleaned = _remove_inline_import_lines(source)

    # Step 2: insert them at module level
    fixed = _insert_imports_after_existing(cleaned, inline)

    if fixed == source:
        return False

    path.write_text(fixed, encoding="utf-8")
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
