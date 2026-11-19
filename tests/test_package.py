"""Static checks on what ships: the manifest's privileges and the release build's guards.

No browser needed. See process/security-review.md (R-04, R-05, R-06, R-14).
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))

_spec = importlib.util.spec_from_file_location("rfy_build", ROOT / "scripts" / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def test_manifest_is_least_privilege():
    assert MANIFEST["permissions"] == ["storage"]
    assert "optional_permissions" not in MANIFEST
    assert MANIFEST["host_permissions"] == ["https://www.youtube.com/*"]
    for block in MANIFEST["content_scripts"]:
        assert block["matches"] == ["https://www.youtube.com/*"]
        assert block["all_frames"] is False
    assert "web_accessible_resources" not in MANIFEST
    assert "externally_connectable" not in MANIFEST
    assert "content_security_policy" not in MANIFEST, "the MV3 default CSP is the intended one"
    gecko = MANIFEST["browser_specific_settings"]["gecko"]
    assert gecko["data_collection_permissions"] == {"required": ["none"]}


def test_release_build_passes_its_checks():
    assert build.check(MANIFEST) == []


def test_build_refuses_clipboard_write():
    for key in ("permissions", "optional_permissions"):
        m = copy.deepcopy(MANIFEST)
        m.setdefault(key, []).append("clipboardWrite")
        assert any("clipboardWrite" in p for p in build.check(m)), key


def test_build_refuses_other_hosts():
    for hosts in (["*://www.youtube.com/*"], ["https://www.youtube.com/*", "https://m.youtube.com/*"]):
        m = copy.deepcopy(MANIFEST)
        m["host_permissions"] = hosts
        m["content_scripts"][0]["matches"] = hosts
        problems = build.check(m)
        assert any("host_permissions" in p for p in problems), hosts
        assert any("matches" in p for p in problems), hosts


def test_build_refuses_stray_files(tmp_path):
    (tmp_path / "src" / "content").mkdir(parents=True)
    (tmp_path / "icons").mkdir()
    (tmp_path / "manifest.json").write_text("{}")
    for rel in ["src/content/core.js", "src/content/core.js.orig", "src/.DS_Store", "icons/icon.svg", "icons/notes.txt"]:
        (tmp_path / rel).write_text("")
    assert sorted(build.unexpected_files(tmp_path)) == ["icons/notes.txt", "src/.DS_Store", "src/content/core.js.orig"]


def test_build_refuses_fault_code(tmp_path):
    """The inert /* test-fault: … */ markers may ship; the code the suite swaps in for them may not."""
    from test_cleanlinks import FAULTS

    features = tmp_path / "src" / "content" / "features"
    features.mkdir(parents=True)
    source = (ROOT / "src" / "content" / "features" / "cleanlinks.js").read_text(encoding="utf-8")
    (features / "cleanlinks.js").write_text(source, encoding="utf-8")
    assert build.fault_injected_files(tmp_path) == [], "the shipped markers alone are fine"
    (features / "cleanlinks.js").write_text(
        source.replace("/* test-fault: clean */", FAULTS["clean"]), encoding="utf-8"
    )
    assert build.fault_injected_files(tmp_path) == ["src/content/features/cleanlinks.js"]
    assert build.fault_injected_files() == [], "the real source tree"
