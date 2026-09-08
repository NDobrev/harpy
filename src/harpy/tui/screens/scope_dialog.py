"""Checks-first analysis configuration with explicit model and preset controls."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from harpy.models import ScopePreset, ScopeSelection
from harpy.prefs import PrefsStore
from harpy.review_scope import (
    apply_preset,
    matching_preset,
    normalize,
    plan_calls,
    short_model_label,
)
from harpy.tui.scope_rows import (
    SCOPE_COPY,
    diagrams_available,
    model_summary,
    run_details,
    run_summary,
)
from harpy.tui.screens.scope_controls import (
    PickerChoice,
    ScopeCheckList,
    ScopePicker,
    ScopePresetName,
)


class ScopeDialog(ModalScreen[ScopeSelection | None]):
    CSS_PATH = "../scope_dialog.tcss"
    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(
        self,
        selection: ScopeSelection,
        *,
        models: Sequence[str],
        presets: Sequence[ScopePreset] | None = None,
        store: PrefsStore | None = None,
        default_model: str | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        if not models and not default_model:
            raise ValueError("At least one model or a default model is required")
        self._default_model = default_model or models[0]
        self._selection = normalize(
            selection.model_copy(deep=True), default_model=self._default_model
        )
        self._models = tuple(
            dict.fromkeys([*models, *self._selection.models.values(), self._default_model])
        )
        self._store = store
        self._presets = list(presets) if presets is not None else []
        self._base_model = Counter(self._selection.models.values()).most_common(1)[0][0]
        self._force_custom = False
        self._customizing = False
        self._details_open = False

    def compose(self) -> ComposeResult:
        with Vertical(id="scope-box"):
            yield Static("Configure analysis", classes="scope-title")
            yield Static("Choose what Harpy should examine.", id="scope-subtitle")
            with VerticalScroll(id="scope-body"):
                with Horizontal(classes="scope-toolbar"):
                    yield Button("Preset", id="scope-preset")
                    yield Button("Save preset…", id="scope-save", disabled=self._store is None)
                yield ScopeCheckList()
                with Horizontal(classes="scope-toolbar"):
                    yield Button("Model", id="scope-model")
                    yield Button("Customize by check…", id="scope-customize")
                with Vertical(id="scope-model-editor"):
                    for item in SCOPE_COPY:
                        if item.id != "diagrams":
                            with Horizontal(classes="scope-model-row"):
                                yield Static(item.label, classes="scope-model-label")
                                yield Button("", id=f"scope-model-{item.id}")
                yield Static("", id="scope-run-details", markup=False)
            with Vertical(id="scope-footer"):
                yield Static("", id="scope-focused-help", markup=False)
                yield Static("", id="scope-note", markup=False)
                yield Static("", id="scope-summary", markup=False)
                yield Static(
                    "Selected checks will run again, including previously analyzed ones.",
                    id="scope-rerun-note",
                )
                with Horizontal(classes="scope-actions"):
                    yield Static("↑↓ Move · Space Toggle", id="scope-help")
                    yield Button("Run details", id="scope-details")
                    yield Button("Cancel", id="scope-cancel")
                    yield Button("Start analysis", id="scope-start", variant="primary")

    def on_mount(self) -> None:
        self._refresh()
        self.query_one(ScopeCheckList).focus()

    def on_resize(self, _event: events.Resize) -> None:
        if self.is_mounted:
            self._refresh()
            if self.query_one(ScopeCheckList).has_focus:
                self.call_after_refresh(self.query_one(ScopeCheckList).reveal_selection)

    def _preset_list(self) -> list[ScopePreset]:
        return self._store.all_presets() if self._store is not None else list(self._presets)

    def _refresh(self) -> None:
        self._selection = normalize(self._selection, default_model=self._default_model)
        presets = self._preset_list()
        selected = next((item for item in presets if item.name == self._selection.preset), None)
        matched = matching_preset(
            self._selection, [selected] if selected else [], default_model=self._default_model
        )
        if not matched and not self._force_custom:
            matched = matching_preset(self._selection, presets, default_model=self._default_model)
        self._selection = self._selection.model_copy(update={"preset": matched})
        self.query_one("#scope-preset", Button).label = Text(f"Preset: {matched or 'Custom'} ▾")
        self.query_one("#scope-preset", Button).disabled = not presets
        compact = self.app.size.width < 100
        self.set_class(compact, "-compact")
        self.query_one(ScopeCheckList).update_selection(
            self._selection, base_model=self._base_model, compact=compact
        )
        self.query_one("#scope-model", Button).label = Text(
            f"Model: {model_summary(self._selection)} ▾"
        )
        self.query_one("#scope-model-editor").display = self._customizing
        self.query_one("#scope-customize", Button).label = (
            "Hide customization" if self._customizing else "Customize by check…"
        )
        for scope_id, model in self._selection.models.items():
            button = self.query_one(f"#scope-model-{scope_id}", Button)
            button.label = Text(short_model_label(model) + " ▾")
            button.tooltip = model
        self.query_one("#scope-run-details", Static).update(
            run_details(self._selection, default_model=self._default_model)
        )
        self.query_one("#scope-run-details").display = self._details_open
        self.query_one("#scope-details", Button).label = (
            "Hide details" if self._details_open else "Run details"
        )
        self.query_one("#scope-summary", Static).update(
            run_summary(self._selection, default_model=self._default_model)
        )
        self.query_one("#scope-start", Button).disabled = not plan_calls(
            self._selection, default_model=self._default_model
        )
        note = ""
        if not self._selection.enabled["security"]:
            note = "Security analysis is off. Security/data scoring dimensions will not be assessed, and importance scores may be lower."
        self.query_one("#scope-note", Static).update(note)
        self.query_one("#scope-note").display = bool(note)
        self._refresh_help()

    def _refresh_help(self) -> None:
        item = self.query_one(ScopeCheckList).selected_scope
        help_text = item.help
        if item.id == "diagrams" and not diagrams_available(self._selection):
            help_text = "Select API contracts or Database changes to include diagrams."
        self.query_one("#scope-focused-help", Static).update(f"{item.label}: {help_text}")

    def on_scope_check_list_highlighted(self, event: ScopeCheckList.Highlighted) -> None:
        event.stop()
        self._refresh_help()

    def on_scope_check_list_toggled(self, event: ScopeCheckList.Toggled) -> None:
        event.stop()
        if event.scope_id == "diagrams" and not diagrams_available(self._selection):
            self._refresh_help()
            return
        enabled = dict(self._selection.enabled)
        enabled[event.scope_id] = not enabled[event.scope_id]
        self._selection = self._selection.model_copy(update={"enabled": enabled, "preset": None})
        self._force_custom = False
        self._refresh()

    def on_scope_check_list_run_requested(self, event: ScopeCheckList.RunRequested) -> None:
        event.stop()
        self.action_run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        button_id = event.button.id or ""
        if button_id == "scope-start":
            self.action_run()
        elif button_id == "scope-cancel":
            self.dismiss(None)
        elif button_id == "scope-customize":
            self._customizing = not self._customizing
            self._refresh()
        elif button_id == "scope-details":
            self._details_open = not self._details_open
            self._refresh()
            if self._details_open:
                self.query_one("#scope-run-details").scroll_visible(animate=False)
        elif button_id == "scope-preset":
            self._open_presets()
        elif button_id == "scope-save":
            self._save_preset()
        elif button_id == "scope-model":
            self._open_models()
        elif button_id.startswith("scope-model-"):
            self._open_models(button_id.removeprefix("scope-model-"))

    def _open_models(self, scope_id: str | None = None) -> None:
        title = (
            "Model for all checks"
            if scope_id is None
            else f"Model for {next(item.label for item in SCOPE_COPY if item.id == scope_id)}"
        )
        current = (
            self._selection.models.get(scope_id)
            if scope_id
            else (
                next(iter(self._selection.models.values()))
                if len(set(self._selection.models.values())) == 1
                else None
            )
        )
        choices = [PickerChoice(model, short_model_label(model), model) for model in self._models]

        def chosen(model: str | None) -> None:
            if model is not None:
                models = dict(self._selection.models)
                if scope_id:
                    models[scope_id] = model
                else:
                    models = {key: model for key in models}
                    self._base_model = model
                self._selection = self._selection.model_copy(
                    update={"models": models, "preset": None}
                )
                self._force_custom = False
                self._refresh()

        self.app.push_screen(ScopePicker(title, choices, current=current), chosen)

    def _open_presets(self) -> None:
        choices = []
        for preset in self._preset_list():
            selection = apply_preset(preset, default_model=self._default_model)
            detail = run_summary(selection, default_model=self._default_model)
            detail += "\n" + run_details(selection, default_model=self._default_model)
            choices.append(PickerChoice(preset.name, preset.name, detail, not preset.builtin))

        def chosen(name: str | None) -> None:
            presets = self._preset_list()
            picked = next((item for item in presets if item.name == name), None)
            if picked:
                self._selection = apply_preset(picked, default_model=self._default_model)
                self._base_model = Counter(self._selection.models.values()).most_common(1)[0][0]
                self._force_custom = False
            elif self._selection.preset and not any(
                item.name == self._selection.preset for item in presets
            ):
                self._selection = self._selection.model_copy(update={"preset": None})
                self._force_custom = True
            self._refresh()

        self.app.push_screen(
            ScopePicker(
                "Choose a preset", choices, current=self._selection.preset, store=self._store
            ),
            chosen,
        )

    def _save_preset(self) -> None:
        if self._store is None:
            return
        presets = self._preset_list()

        def chosen(name: str | None) -> None:
            if name is None or self._store is None:
                return
            preset = ScopePreset(
                name=name,
                enabled=dict(self._selection.enabled),
                models=dict(self._selection.models),
            )
            try:
                saved = self._store.save_preset(preset)
            except OSError as exc:
                self.notify(f"Could not save preset: {exc}", severity="error")
                return
            if saved:
                self._selection = self._selection.model_copy(update={"preset": name})
                self._force_custom = False
                self._refresh()

        self.app.push_screen(
            ScopePresetName(
                builtins={item.name for item in presets if item.builtin},
                existing={item.name for item in presets},
            ),
            chosen,
        )

    def action_run(self) -> None:
        if plan_calls(self._selection, default_model=self._default_model):
            self.dismiss(normalize(self._selection, default_model=self._default_model))

    def action_cancel(self) -> None:
        if self._customizing:
            self._customizing = False
            self._refresh()
            self.query_one("#scope-customize").focus()
        elif self._details_open:
            self._details_open = False
            self._refresh()
            self.query_one("#scope-details").focus()
        else:
            self.dismiss(None)
