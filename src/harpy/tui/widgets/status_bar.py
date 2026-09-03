from textual.widgets import Static


class StatusBar(Static):
    def set_text(self, text: str) -> None:
        self.update(text)
