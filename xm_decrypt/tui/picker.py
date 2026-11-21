"""文件 / 目录选择器（键盘优先，文件多选与选目录共用）。"""

from __future__ import annotations

import os
from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from ..metadata import sort_files_by_track_id

PICKER_HINT = "空格=选中/取消   a=全选   c=清空   Enter=进入目录/切换   Ctrl+S=确定   Esc=取消"


def expand_user(path_str: str) -> str:
    path_str = (path_str or "").strip()
    return str(Path(path_str).expanduser()) if path_str else ""


# --------------------------------------------------------------------------- #
# 文件 / 目录选择器
# --------------------------------------------------------------------------- #
class FilePicker(ModalScreen):
    """键盘优先的选择器。

    pick_mode="files" 返回 list[str]（选中的 .xm 绝对路径）；
    pick_mode="dirs"  返回 str（当前目录），用于选输入/输出目录。
    """

    BINDINGS = [
        Binding("escape", "cancel", "取消"),
        Binding("space", "toggle", "选中"),
        Binding("a", "select_all", "全选"),
        Binding("c", "clear_selection", "清空"),
        Binding("ctrl+s", "confirm", "确定"),
    ]

    def __init__(self, start_dir: str, pick_mode: str = "files", heading: str = "选择 .xm 文件"):
        super().__init__()
        self.pick_mode = pick_mode
        self.heading = heading
        self.cwd = self._initial_dir(start_dir)
        self.selected: set[str] = set()
        self._entries: list[tuple[str, Path]] = []

    @staticmethod
    def _initial_dir(start_dir: str) -> Path:
        candidate = Path(expand_user(start_dir) or os.getcwd())
        if candidate.is_file():
            candidate = candidate.parent
        while not candidate.is_dir() and candidate.parent != candidate:
            candidate = candidate.parent
        return candidate.resolve()

    # ---------- 布局 ----------
    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="picker-dialog"):
            with Horizontal(classes="field-row"):
                yield Label("路径")
                yield Input(str(self.cwd), id="path-input")
                yield Button("前往", id="go")
            yield Static("", id="cwd-line", classes="muted")
            yield ListView(id="entries")
            yield Static("", id="hint")
            with Horizontal(classes="dialog-buttons"):
                yield Button("全选", id="select-all")
                yield Button("清空", id="clear")
                yield Button("取消", id="cancel")
                yield Button("确定", id="confirm", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#picker-dialog").border_title = self.heading
        self.refresh_entries()

    # ---------- 数据 ----------
    def refresh_entries(self) -> None:
        entries: list[tuple[str, Path]] = []
        if self.cwd.parent != self.cwd:
            entries.append(("parent", self.cwd.parent))

        try:
            children = sorted(self.cwd.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            self.notify(f"无法读取目录：{exc}", severity="error")
            children = []

        dirs = [p for p in children if p.is_dir() and not p.name.startswith(".")]
        files = [p for p in children if p.is_file() and p.suffix.lower() == ".xm"]
        entries.extend(("dir", p) for p in dirs)
        entries.extend(("file", p) for p in files)

        self._entries = entries
        list_view = self.query_one("#entries", ListView)
        list_view.clear()
        list_view.extend(ListItem(Label(self._label(kind, path, False))) for kind, path in entries)
        if entries:
            list_view.index = 0
        list_view.focus()

        suffix = "" if files else "  [yellow]（该目录没有 .xm 文件）[/yellow]"
        self.query_one("#cwd-line", Static).update(
            f"当前目录：{escape(str(self.cwd))}{suffix}"
        )
        self._refresh_hint()
        # ListItem 里的 Label 要等下一帧才挂载完成，这里延后一帧再画箭头。
        self.call_after_refresh(self._refresh_labels)

    def _label(self, kind: str, path: Path, current: bool) -> str:
        prefix = ">> " if current else "   "
        if kind == "parent":
            return f"{prefix}[dim].. 上级目录[/dim]"
        if kind == "dir":
            return f"{prefix}[bold]▸[/bold] {escape(path.name)}/"
        if self.pick_mode == "dirs":
            return f"{prefix}[dim]{escape(path.name)}[/dim]"
        mark = "[bold][x][/bold]" if str(path) in self.selected else "[ ]"
        return f"{prefix}{mark} {escape(path.name)}"

    def _refresh_hint(self) -> None:
        if self.pick_mode == "dirs":
            extra = "Enter 进入目录，Ctrl+S 选定当前目录，Esc 取消"
        else:
            extra = f"已选中 [b]{len(self.selected)}[/b] 个 .xm 文件"
        self.query_one("#hint", Static).update(f"{PICKER_HINT}\n{extra}")

    def _refresh_labels(self) -> None:
        list_view = self.query_one("#entries", ListView)
        current = list_view.index
        for position, (item, (kind, path)) in enumerate(
            zip(list_view.children, self._entries, strict=False)
        ):
            labels = item.query(Label)
            if labels:
                labels.first().update(self._label(kind, path, position == current))
        self._refresh_hint()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._refresh_labels()

    # ---------- 交互 ----------
    def _goto(self, path: Path) -> None:
        if not path.is_dir():
            self.notify(f"目录不存在：{path}", severity="error")
            return
        self.cwd = path.resolve()
        self.query_one("#path-input", Input).value = str(self.cwd)
        self.refresh_entries()

    def _toggle_path(self, path: Path) -> None:
        key = str(path)
        if key in self.selected:
            self.selected.discard(key)
        else:
            self.selected.add(key)
        self._refresh_labels()

    def _current_entry(self):
        index = self.query_one("#entries", ListView).index
        if index is None or index >= len(self._entries):
            return None
        return self._entries[index]

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "path-input":
            self._goto(Path(expand_user(event.value)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        kind, path = entry
        if kind in ("dir", "parent"):
            self._goto(path)
        elif self.pick_mode == "files":
            self._toggle_path(path)

    def action_toggle(self) -> None:
        entry = self._current_entry()
        if entry is None:
            return
        kind, path = entry
        if kind in ("dir", "parent"):
            self._goto(path)
        elif self.pick_mode == "files":
            self._toggle_path(path)

    def action_select_all(self) -> None:
        if self.pick_mode != "files":
            return
        for kind, path in self._entries:
            if kind == "file":
                self.selected.add(str(path))
        self._refresh_labels()

    def action_clear_selection(self) -> None:
        self.selected.clear()
        self._refresh_labels()

    def action_confirm(self) -> None:
        if self.pick_mode == "dirs":
            self.dismiss(str(self.cwd))
            return
        if not self.selected:
            self.notify("还没有选中任何 .xm 文件", severity="warning")
            return
        self.dismiss(sort_files_by_track_id(sorted(self.selected)))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "go": lambda: self._goto(Path(expand_user(self.query_one("#path-input", Input).value))),
            "select-all": self.action_select_all,
            "clear": self.action_clear_selection,
            "cancel": self.action_cancel,
            "confirm": self.action_confirm,
        }
        handler = mapping.get(event.button.id or "")
        if handler:
            handler()
