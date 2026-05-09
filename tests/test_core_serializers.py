"""Regression tests for core serialization and CMDB hash helpers."""

from app.core.serializers import ModelSerializer
from app.services.cmdb.parser import compute_config_hash


class _Dummy:
    def __init__(self):
        self.id = "obj-1"
        self.tags = {"env": "prod", "team": "ops"}
        self.items = [{"k": "v"}, {"n": 1}]


class _DummySerializer(ModelSerializer):
    fields = ["id", "tags", "items"]


def test_model_serializer_preserves_dict_shape():
    payload = _DummySerializer(_Dummy()).to_dict()

    assert payload["id"] == "obj-1"
    assert isinstance(payload["tags"], dict)
    assert payload["tags"] == {"env": "prod", "team": "ops"}
    assert isinstance(payload["items"], list)
    assert payload["items"][0] == {"k": "v"}


def test_compute_config_hash_normalizes_json_string_and_dict_equally():
    hash_from_string = compute_config_hash('{"b":2,"a":1}')
    hash_from_dict = compute_config_hash({"a": 1, "b": 2})

    assert hash_from_string
    assert hash_from_dict
    assert hash_from_string == hash_from_dict


def test_compute_config_hash_none_returns_empty_string():
    assert compute_config_hash(None) == ""
