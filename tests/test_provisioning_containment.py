"""Provisioning path containment — Terraform/Ansible runners.

Filesystem paths from tenant-stored provisioning config (workdir, playbook,
var_file, inventory) must never escape the operator-controlled
PROVISIONING_ROOT_DIR, and provisioning must be off unless explicitly enabled.
This is the control that prevents RCE via an attacker-staged playbook.
"""
import os

import pytest

from app.core.config import settings
from app.services import bookings_service as bs


def test_provisioning_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "PROVISIONING_ENABLED", False)
    with pytest.raises(PermissionError):
        bs._safe_provision_path("main.tf", label="workdir")


def test_provisioning_root_required(monkeypatch):
    monkeypatch.setattr(settings, "PROVISIONING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVISIONING_ROOT_DIR", "")
    with pytest.raises(PermissionError):
        bs._safe_provision_path("main.tf", label="workdir")


def test_path_inside_root_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVISIONING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVISIONING_ROOT_DIR", str(tmp_path))
    (tmp_path / "modules").mkdir()
    resolved = bs._safe_provision_path("modules", label="workdir")
    assert resolved == str((tmp_path / "modules").resolve())


def test_traversal_escape_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVISIONING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVISIONING_ROOT_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="escapes"):
        bs._safe_provision_path("../../etc/evil.tf", label="var_file", required=False)


def test_absolute_path_escape_is_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVISIONING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVISIONING_ROOT_DIR", str(tmp_path))
    outside = os.path.abspath(os.sep + os.path.join("tmp", "outside", "play.yml"))
    with pytest.raises(ValueError, match="escapes"):
        bs._safe_provision_path(outside, label="playbook")


def test_optional_empty_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVISIONING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVISIONING_ROOT_DIR", str(tmp_path))
    assert bs._safe_provision_path("", label="inventory", required=False) is None


def test_required_empty_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVISIONING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVISIONING_ROOT_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="required"):
        bs._safe_provision_path(None, label="playbook")
