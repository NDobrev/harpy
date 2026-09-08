"""Toggle which repositories appear in the analysis browser."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class RepoFilterDialog(ModalScreen[set[str]]):
    BINDINGS = [
        Binding("escape,enter,f", "close", "Done", show=False),
        Binding("space", "toggle_repo", "Toggle", show=False),
        Binding("j,down", "down", "Down", show=False),
        Binding("k,up", "up", "Up", show=False),
    ]

    def __init__(self, repos: list[str], disabled: set[str]) -> None:
        super().__init__()
        self._repos = list(repos)
        self._disabled = set(disabled)
        self._index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="repo-filter-box"):
            yield Static("Repositories", classes="scope-title")
            yield Static("Space hides a repo and its reviews.", id="repo-filter-help")
            yield Static(id="repo-filter-rows", markup=False)

    def on_mount(self) -> None:
        self._paint()

    def action_down(self) -> None:
        if self._repos:
            self._index = (self._index + 1) % len(self._repos)
            self._paint()

    def action_up(self) -> None:
        if self._repos:
            self._index = (self._index - 1) % len(self._repos)
            self._paint()

    def action_toggle_repo(self) -> None:
        if not self._repos:
            return
        repo = self._repos[self._index]
        if repo in self._disabled:
            self._disabled.discard(repo)
        else:
            self._disabled.add(repo)
        self._paint()

    def action_close(self) -> None:
        self.dismiss(set(self._disabled))

    def _paint(self) -> None:
        if not self._repos:
            self.query_one("#repo-filter-rows", Static).update("No repositories yet")
            return
        lines = [
            _row(repo, selected=index == self._index, enabled=repo not in self._disabled)
            for index, repo in enumerate(self._repos)
        ]
        self.query_one("#repo-filter-rows", Static).update("\n".join(lines))


def _row(repo: str, *, selected: bool, enabled: bool) -> str:
    cursor = "▸" if selected else " "
    mark = "on " if enabled else "off"
    return f"{cursor} [{mark}] {repo}"
