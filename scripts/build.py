"""Package the add-on for Firefox (AMO upload or about:debugging).

    python scripts/build.py            -> dist/reclaim-for-youtube-<version>.zip

Only the shipped files go in: manifest.json, src/, icons/. Tests, fixtures and docs stay out.
Also runs a few sanity checks so a broken manifest never gets packaged.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIP = ["manifest.json", "src", "icons"]
# HTTPS only: www.youtube.com is HSTS-preloaded, so http:// never renders a page to act on.
HOSTS = ["https://www.youtube.com/*"]
# Only these file types are packaged, so a stray backup, editor or test file in src/ or icons/
# stops the build instead of shipping.
SHIP_SUFFIXES = {".js", ".css", ".html", ".svg", ".png", ".json"}
# Clean links exports a writeText wrapper that the page calls and that runs with the add-on's
# principal. With clipboardWrite, YouTube could write the clipboard through it without a user
# gesture, so the permission is refused while that wrapper exists.
FORBIDDEN_PERMISSIONS = {"clipboardWrite"}


def shipped_files(root: Path = ROOT) -> list[Path]:
    out = []
    for name in SHIP:
        path = root / name
        out += [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    return out


def unexpected_files(root: Path = ROOT) -> list[str]:
    return [
        f.relative_to(root).as_posix()
        for f in shipped_files(root)
        if f.name.startswith(".") or f.suffix.lower() not in SHIP_SUFFIXES
    ]


def fault_injected_files(root: Path = ROOT) -> list[str]:
    """Scripts carrying the test suite's fault-injection code (tests/test_cleanlinks.py FAULTS),
    which reads a page-writable switch. Only the inert /* test-fault: … */ markers may ship."""
    return [
        f.relative_to(root).as_posix()
        for f in shipped_files(root)
        if f.suffix == ".js" and "rfyFault" in f.read_text(encoding="utf-8")
    ]


def check(manifest: dict) -> list[str]:
    problems = []
    for block in manifest.get("content_scripts", []):
        for key in ("js", "css"):
            for rel in block.get(key, []):
                if not (ROOT / rel).is_file():
                    problems.append(f"content_scripts {key}: missing {rel}")
        if any("localhost" in m for m in block.get("matches", [])):
            problems.append("content_scripts matches localhost (test build leaked into release)")
        elif block.get("matches") != HOSTS:
            problems.append(f"unexpected content_scripts matches: {block.get('matches')}")
    for rel in [manifest.get("action", {}).get("default_popup"), manifest.get("options_ui", {}).get("page")]:
        if rel and not (ROOT / rel).is_file():
            problems.append(f"missing page {rel}")
    if manifest.get("host_permissions") != HOSTS:
        problems.append(f"unexpected host_permissions: {manifest.get('host_permissions')}")
    requested = set(manifest.get("permissions", [])) | set(manifest.get("optional_permissions", []))
    for perm in sorted(requested & FORBIDDEN_PERMISSIONS):
        problems.append(f"permission {perm} would reach the page through the clipboard wrapper")
    problems += [f"unexpected file in package: {rel}" for rel in unexpected_files()]
    problems += [f"{rel}: fault-injection code (test build leaked into release)" for rel in fault_injected_files()]
    return problems


def main() -> int:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    problems = check(manifest)
    if problems:
        print("Refusing to build:\n  " + "\n  ".join(problems))
        return 1
    out = ROOT / "dist" / f"reclaim-for-youtube-{manifest['version']}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in shipped_files():
            z.write(f, f.relative_to(ROOT).as_posix())
    print(f"Built {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
