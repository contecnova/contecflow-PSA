import inspect

from app.models.user import User
from app.services.ai_chat_service import execute_tool


def test_execute_tool_no_tool_dot_input_reference():
    src = inspect.getsource(execute_tool)
    assert "tool.input" not in src


def test_execute_tool_search_projects_does_not_raise_nameerror(db):
    admin = db.query(User).filter(User.username == "admin").first()
    result = execute_tool("search_projects", {"query": "acme"}, db, admin)

    assert isinstance(result, dict)
    assert "projects" in result or "error" in result
    if "error" in result:
        assert "tool" not in result["error"].lower()
