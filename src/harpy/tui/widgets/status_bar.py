from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    def set_text(self, text: str) -> None:
        self.update(Text(text))
