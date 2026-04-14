import ast
from pathlib import Path


def test_no_inline_pydantic_schemas_in_normalized_endpoints() -> None:
    """Domain endpoints should import schemas from app.schemas, not define them inline."""
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "app" / "api" / "v1" / "endpoints" / "bookings.py",
        root / "app" / "api" / "v1" / "endpoints" / "billing_reports.py",
        root / "app" / "api" / "v1" / "endpoints" / "service_desk.py",
    ]

    offenders = []
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "BaseModel":
                    offenders.append(f"{path.name}:{node.lineno}:{node.name}")

    assert offenders == [], (
        "Found inline Pydantic schemas in normalized endpoints. "
        "Move them to app/schemas/<domain>.py. Offenders: " + ", ".join(offenders)
    )
