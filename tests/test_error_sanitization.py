from app.core.error_sanitizer import sanitize_http_detail


def test_sensitive_400_detail_is_sanitized():
    detail = "sqlalchemy error at line 42 while parsing token"
    safe = sanitize_http_detail(400, detail)
    assert safe == "Invalid request"


def test_benign_404_detail_is_preserved():
    detail = "Project not found"
    safe = sanitize_http_detail(404, detail)
    assert safe == detail


def test_500_detail_always_sanitized():
    detail = "Traceback: ValueError('secret key leaked')"
    safe = sanitize_http_detail(500, detail)
    assert safe == "Internal Server Error"


def test_422_structured_validation_is_preserved():
    detail = [{"loc": ["body", "rate"], "msg": "field required", "type": "value_error.missing"}]
    safe = sanitize_http_detail(422, detail)
    assert safe == detail
