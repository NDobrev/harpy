from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "web" / "src" / "theme-tokens.json").read_text(encoding="utf-8"))
CSS = (ROOT / "web" / "src" / "tokens.css").read_text(encoding="utf-8")

TEXT_SURFACES = (
    "background",
    "surface",
    "surface-raised",
    "code-background",
    "addition-background",
    "deletion-background",
)


def _channel(pair: str) -> float:
    value = int(pair, 16) / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    hex_color = color.removeprefix("#")
    return (
        0.2126 * _channel(hex_color[0:2])
        + 0.7152 * _channel(hex_color[2:4])
        + 0.0722 * _channel(hex_color[4:6])
    )


def contrast(first: str, second: str) -> float:
    lighter = max(luminance(first), luminance(second))
    darker = min(luminance(first), luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


def test_css_contains_each_theme_block() -> None:
    for theme in TOKENS["themes"]:
        assert f'[data-theme="{theme}"]' in CSS


def test_hex_tokens_appear_in_css() -> None:
    for values in TOKENS["themes"].values():
        for name, value in values.items():
            if value.startswith("rgba"):
                continue
            assert value.lower() in CSS.lower()
            assert f"--{name}:" in CSS


def test_theme_text_contrast_meets_aa() -> None:
    for theme, values in TOKENS["themes"].items():
        for surface in TEXT_SURFACES:
            ratio = contrast(values["text"], values[surface])
            assert ratio >= 4.5, f"{theme} text on {surface}: {ratio:.2f}"
        muted = contrast(values["text-muted"], values["background"])
        assert muted >= 4.5, f"{theme} muted on background: {muted:.2f}"
        accent = contrast(values["on-accent"], values["accent"])
        assert accent >= 4.5, f"{theme} on-accent: {accent:.2f}"
        border = contrast(values["border"], values["surface"])
        assert border >= 3, f"{theme} border on surface: {border:.2f}"


def test_default_theme_is_dark_blue() -> None:
    assert TOKENS["defaultTheme"] == "dark_blue"
    assert re.search(
        r'data-theme="dark_blue"', (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    )
