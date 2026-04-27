from app.services.service_desk.workflow_designer_service import validate_graph


def test_validate_graph_accepts_minimal_valid_graph():
    graph = {
        "nodes": [
            {"id": "n1", "type": "start"},
            {"id": "n2", "type": "end"},
        ],
        "edges": [{"source": "n1", "target": "n2", "type": "default"}],
    }
    out = validate_graph(graph)
    assert out["valid"] is True
    assert out["errors"] == []


def test_validate_graph_rejects_without_start():
    graph = {
        "nodes": [{"id": "n2", "type": "end"}],
        "edges": [],
    }
    out = validate_graph(graph)
    assert out["valid"] is False
    assert any("start" in err for err in out["errors"])
