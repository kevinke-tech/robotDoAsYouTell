"""Persistent manifest for generated skills."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MANIFEST_FILE = ROOT / "logs" / "skill_manifest.json"


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST_FILE.exists():
        return {"skills": {}}
    try:
        data = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("skills"), dict):
            return data
    except Exception:
        pass
    return {"skills": {}}


def _save_manifest(data: dict[str, Any]) -> None:
    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST_FILE)


def upsert_generated_skill(name: str, meta: dict[str, Any]) -> None:
    data = _load_manifest()
    skills = data.setdefault("skills", {})
    record = dict(meta)
    record["name"] = name
    record.setdefault("quality_state", "draft")
    record["updated_at"] = datetime.now().isoformat(timespec="seconds")
    skills[name] = record
    _save_manifest(data)


def remove_skill(name: str) -> None:
    data = _load_manifest()
    skills = data.setdefault("skills", {})
    if name in skills:
        skills.pop(name, None)
        _save_manifest(data)


def get_skill_meta(name: str) -> dict[str, Any]:
    data = _load_manifest()
    skills = data.get("skills") or {}
    meta = skills.get(name)
    return dict(meta) if isinstance(meta, dict) else {}


def patch_skill_meta(name: str, fields: dict[str, Any]) -> None:
    if not name or not isinstance(fields, dict):
        return
    data = _load_manifest()
    skills = data.setdefault("skills", {})
    old = skills.get(name)
    if not isinstance(old, dict):
        return
    updated = dict(old)
    updated.update(fields)
    updated["updated_at"] = datetime.now().isoformat(timespec="seconds")
    skills[name] = updated
    _save_manifest(data)
