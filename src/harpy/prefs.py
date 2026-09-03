"""User-level review-scope preferences and named presets."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from harpy.models import ScopePreset, ScopeSelection
from harpy.review_scope import BUILTIN_PRESETS, default_selection

SCOPE_FILE = "scope.json"
PRESETS_FILE = "presets.json"


def config_dir(*, root: Path | None = None, env: dict[str, str] | None = None) -> Path:
    if root is not None:
        return root
    environ = env if env is not None else os.environ
    xdg = environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "harpy"
    return Path.home() / ".config" / "harpy"


def _write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


class PrefsStore:
    def __init__(self, root: Path | None = None, *, env: dict[str, str] | None = None) -> None:
        self.root = config_dir(root=root, env=env)

    def load_selection(self) -> ScopeSelection:
        path = self.root / SCOPE_FILE
        if not path.is_file():
            return default_selection()
        try:
            return ScopeSelection.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, ValidationError):
            return default_selection()

    def save_selection(self, selection: ScopeSelection) -> None:
        _write_json(self.root / SCOPE_FILE, selection.model_dump_json(indent=2))

    def user_presets(self) -> list[ScopePreset]:
        path = self.root / PRESETS_FILE
        if not path.is_file():
            return []
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(parsed, list):
            return []
        presets: list[ScopePreset] = []
        builtin_names = {item.name for item in BUILTIN_PRESETS}
        for item in parsed:
            try:
                preset = ScopePreset.model_validate(item)
            except ValidationError:
                continue
            if preset.name in builtin_names:
                continue
            presets.append(preset.model_copy(update={"builtin": False}))
        return presets

    def all_presets(self) -> list[ScopePreset]:
        return [*BUILTIN_PRESETS, *self.user_presets()]

    def save_preset(self, preset: ScopePreset) -> bool:
        name = preset.name.strip()
        if not name or name in {item.name for item in BUILTIN_PRESETS}:
            return False
        current = [item for item in self.user_presets() if item.name != name]
        current.append(preset.model_copy(update={"builtin": False, "name": name}))
        self._write_presets(current)
        return True

    def delete_preset(self, name: str) -> bool:
        if name in {item.name for item in BUILTIN_PRESETS}:
            return False
        current = [item for item in self.user_presets() if item.name != name]
        if len(current) == len(self.user_presets()):
            return False
        self._write_presets(current)
        return True

    def _write_presets(self, presets: list[ScopePreset]) -> None:
        payload = json.dumps([item.model_dump() for item in presets], indent=2)
        _write_json(self.root / PRESETS_FILE, payload)
