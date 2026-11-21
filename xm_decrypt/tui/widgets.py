"""Turbo Vision 风格的基础控件：标题栏、高亮提示条、键盘菜单。

参考的是 DOS 时代的全屏 TUI：黑底、单线框、框线上嵌标题、黄色表示当前项。
Textual 自带 Header/Footer/Button 是 Web 风格，这里一律不用，改为自绘，
避免界面看起来像个网页表单。
"""

from __future__ import annotations

import socket

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.content import Content
from textual.message import Message
from textual.widgets import Checkbox, Label, ListItem, ListView, Static


class BoxCheckbox(Checkbox):
    """`[x]` / `[ ]` 复选框。

    Textual 默认把复选框画成 `▐X▌` 色块（开关都显示 X，只靠颜色区分），
    在单色终端里根本看不出状态，这里换回传统写法。
    """

    @property
    def _button(self) -> Content:
        style = self.get_visual_style("toggle--button")
        inner = "x" if self.value else " "
        return Content.assemble(("[", style), (inner, style), ("]", style))


class TitleBar(Horizontal):
    """顶部标题行：左边程序名与版本，右边主机名。"""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__(id="titlebar")
        self._title = title
        self._subtitle = subtitle

    def compose(self) -> ComposeResult:
        text = f"{self._title}  {self._subtitle}".rstrip()
        yield Static(text, id="app-title")
        yield Static(socket.gethostname(), id="app-host")


class HintBar(Static):
    """黄底黑字的一行提示，用来放"输出目录 / 免责声明"这类常驻信息。"""

    def __init__(self, text: str = "") -> None:
        super().__init__(text, id="hintbar")

    def set_text(self, text: str) -> None:
        self.update(text)


class MenuList(ListView):
    """键盘菜单：`>>` 标记当前项，上下移动、Enter 触发。

    items 是 (显示文本, 动作标识) 的序列，动作由宿主界面解释。
    """

    class Activated(Message):
        """用户确认了某一项。"""

        def __init__(self, action: str) -> None:
            self.action = action
            super().__init__()

    def __init__(self, items, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items = [(label, action) for label, action in items]

    def compose(self) -> ComposeResult:
        for label, _ in self._items:
            yield ListItem(Label(label))

    def on_mount(self) -> None:
        if self.index is None and self._items:
            self.index = 0
        self._paint()

    def _paint(self) -> None:
        current = self.index
        for position, item in enumerate(self.children):
            labels = item.query(Label)
            if not labels:
                continue
            prefix = ">> " if position == current else "   "
            labels.first().update(prefix + self._items[position][0])

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._paint()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        index = self.index
        if index is not None and 0 <= index < len(self._items):
            self.post_message(self.Activated(self._items[index][1]))
