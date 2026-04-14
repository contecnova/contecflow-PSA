"""
Regression test: ensure Pydantic v1 @validator is not reintroduced after v2 migration.

Pydantic v2 requires @field_validator. Mixing @validator (v1 compatibility mode) with
@field_validator weakens type safety and will break in future Pydantic versions.
"""
import ast
from pathlib import Path


def test_no_pydantic_v1_validator_decorator() -> None:
    """Ensure no uses of deprecated @validator decorator in app/."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    
    deprecated_files = []
    
    for py_file in app_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        
        for node in ast.walk(tree):
            # Look for decorator nodes named 'validator'
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                for decorator in node.decorator_list:
                    # Check if decorator is Name("validator") or Call with func=Name("validator")
                    decorator_name = None
                    if isinstance(decorator, ast.Name):
                        decorator_name = decorator.id
                    elif isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
                        decorator_name = decorator.func.id
                    
                    if decorator_name == "validator":
                        relative_path = py_file.relative_to(app_dir.parent)
                        deprecated_files.append(
                            f"{relative_path}:{node.lineno} ({node.name})"
                        )
    
    assert deprecated_files == [], (
        "Found deprecated @validator (Pydantic v1 API). "
        "Use @field_validator instead. "
        "Files: " + ", ".join(deprecated_files)
    )


def test_no_pydantic_v1_validator_imports() -> None:
    """Ensure no imports of deprecated 'validator' from pydantic."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    
    bad_imports = []
    
    for py_file in app_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "pydantic":
                    for alias in node.names:
                        if alias.name == "validator":
                            relative_path = py_file.relative_to(app_dir.parent)
                            bad_imports.append(f"{relative_path}:{node.lineno}")
    
    assert bad_imports == [], (
        "Found deprecated 'validator' import from pydantic (v1 API). "
        "Use 'field_validator' instead. "
        "Files: " + ", ".join(bad_imports)
    )
