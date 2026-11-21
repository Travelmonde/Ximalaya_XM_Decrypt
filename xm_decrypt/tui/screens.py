"""TUI 的各个界面：文件选择、命名确认、目录确认、设置、运行进度。

约定：所有弹窗都用 dismiss(result) 返回数据，取消统一返回 None，
由主界面（app.MainScreen）负责串联流程与持久化。
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Static,
)

from ..batch import run_batch
from ..exporter import replace_invalid_chars
from ..metadata import read_xm_meta, scan_xm_files
from .picker import FilePicker, expand_user
from .widgets import BoxCheckbox
from ..settings import Settings, default_process_count, settings_path

WAV_OPTIONS = [("保留 WAV", "keep"), ("封装为 ALAC (.m4a)", "alac")]

# --------------------------------------------------------------------------- #
# 多文件：输出目录 + 逐个改名
# --------------------------------------------------------------------------- #
class PlanScreen(ModalScreen):
    """确认输出目录与每个文件的输出名（不含扩展名）。"""

    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(self, files: list[str], settings: Settings):
        super().__init__()
        self.files = list(files)
        self.settings = settings
        self.total = len(self.files)
        self.width = len(str(max(self.total, 1)))

        metas = [read_xm_meta(path) for path in self.files]
        self.defaults: list[str] = []
        for index, (path, meta) in enumerate(zip(self.files, metas, strict=True)):
            if meta is None or not meta.title:
                self.defaults.append(replace_invalid_chars(Path(path).stem))
                continue
            title = replace_invalid_chars(meta.title)
            if self.total > 1:
                # 编号按列表顺序（1..N），与批量模式一致。
                # 注意不能用 ID3 的 TRCK：喜马拉雅文件里那是内部 id（如 718468768），
                # 不是曲序。
                self.defaults.append(f"{index + 1:0{self.width}d} - {title}")
            else:
                self.defaults.append(title)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="plan-dialog"):
            with Horizontal(classes="field-row"):
                yield Label("输出目录")
                yield Input(self.settings.resolved_output_dir(), id="out-dir")
                yield Button("浏览", id="browse-out")
            yield BoxCheckbox("按专辑名再建一层子目录", value=False, id="album-sub")
            yield Static("可逐个修改文件名（不含扩展名，扩展名按解密结果补全）", classes="muted")
            with VerticalScroll(id="rows"):
                for index, path in enumerate(self.files):
                    with Horizontal(classes="row"):
                        yield Static(escape(Path(path).name), classes="fname")
                        yield Input(self.defaults[index], id=f"name-{index}")
            yield Static("", id="error", classes="error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("恢复默认", id="reset")
                yield Button("取消", id="cancel")
                yield Button("开始解密", id="start", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#plan-dialog").border_title = f"确认输出与命名（共 {self.total} 个文件）"
        self.query_one("#start", Button).focus()

    def _error(self, message: str) -> None:
        self.query_one("#error", Static).update(escape(message))

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _browse(self) -> None:
        self.app.push_screen(
            FilePicker(self.query_one("#out-dir", Input).value, pick_mode="dirs",
                       heading="选择输出目录"),
            self._apply_out_dir,
        )

    def _apply_out_dir(self, result) -> None:
        if result:
            self.query_one("#out-dir", Input).value = str(result)

    def _reset_names(self) -> None:
        for index, value in enumerate(self.defaults):
            self.query_one(f"#name-{index}", Input).value = value
        self.query_one("#error", Static).update("")

    def _start(self) -> None:
        output_dir = expand_user(self.query_one("#out-dir", Input).value)
        if not output_dir:
            self._error("请填写输出目录")
            return

        names: list[str] = []
        seen: set[str] = set()
        for index in range(self.total):
            name = replace_invalid_chars(self.query_one(f"#name-{index}", Input).value).strip()
            if not name:
                self._error(f"第 {index + 1} 个文件名不能为空")
                return
            if name.casefold() in seen:
                self._error(f"文件名重复：{name}")
                return
            seen.add(name.casefold())
            names.append(name)

        self.dismiss(
            {
                "files": self.files,
                "output_dir": output_dir,
                "names": names,
                "album": self.query_one("#album-sub", Checkbox).value,
                "processes": self.settings.effective_processes(),
                "wav_mode": self.settings.wav_mode,
            }
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "browse-out": self._browse,
            "reset": self._reset_names,
            "cancel": self.action_cancel,
            "start": self._start,
        }
        handler = mapping.get(event.button.id or "")
        if handler:
            handler()


# --------------------------------------------------------------------------- #
# 整目录：数量确认 + 子目录 / 并行数
# --------------------------------------------------------------------------- #
class DirPlanScreen(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(self, directory: str, settings: Settings):
        super().__init__()
        self.directory = directory
        self.settings = settings
        self.files: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-small", id="dir-dialog"):
            yield Static(f"目录：{escape(self.directory)}", classes="muted")
            yield Static("", id="count-line", classes="muted")
            with Horizontal(classes="field-row"):
                yield Label("输出目录")
                yield Input(self.settings.resolved_output_dir(), id="out-dir")
                yield Button("浏览", id="browse-out")
            yield BoxCheckbox("包含子目录", value=self.settings.include_subdirs, id="include-subdirs")
            with Horizontal(classes="field-row"):
                yield Label("并行进程")
                yield Input(str(self.settings.effective_processes()), id="processes", type="integer")
            yield Static("输出规则：<输出目录>/<专辑>/<曲序 - 标题>.<扩展名>", classes="muted")
            yield Static("", id="error", classes="error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("取消", id="cancel")
                yield Button("开始解密", id="start", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#dir-dialog").border_title = "确认目录解密参数"
        self._refresh_count()

    def _recursive(self) -> bool:
        return self.query_one("#include-subdirs", Checkbox).value

    def _refresh_count(self) -> None:
        self.files = scan_xm_files(self.directory, recursive=self._recursive())
        scope = "含子目录" if self._recursive() else "仅当前目录"
        line = self.query_one("#count-line", Static)
        if self.files:
            line.update(f"找到 [b]{len(self.files)}[/b] 个 .xm 文件（{scope}）")
        else:
            line.update(f"[yellow]没有找到 .xm 文件（{scope}）[/yellow]")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "include-subdirs":
            self._refresh_count()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _browse(self) -> None:
        self.app.push_screen(
            FilePicker(self.query_one("#out-dir", Input).value, pick_mode="dirs",
                       heading="选择输出目录"),
            self._apply_out_dir,
        )

    def _apply_out_dir(self, result) -> None:
        if result:
            self.query_one("#out-dir", Input).value = str(result)

    def _start(self) -> None:
        error = self.query_one("#error", Static)
        if not self.files:
            error.update("当前范围内没有可解密的文件")
            return
        output_dir = expand_user(self.query_one("#out-dir", Input).value)
        if not output_dir:
            error.update("请填写输出目录")
            return
        raw = self.query_one("#processes", Input).value
        try:
            processes = int(raw)
        except ValueError:
            error.update("并行进程数必须是整数")
            return
        limit = max(1, os.cpu_count() or 1) * 4
        if processes < 1 or processes > limit:
            error.update(f"并行进程数需在 1 - {limit} 之间")
            return

        self.dismiss(
            {
                "files": self.files,
                "output_dir": output_dir,
                "names": None,
                "album": True,
                "processes": processes,
                "wav_mode": self.settings.wav_mode,
            }
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {"browse-out": self._browse, "cancel": self.action_cancel, "start": self._start}
        handler = mapping.get(event.button.id or "")
        if handler:
            handler()


# --------------------------------------------------------------------------- #
# 设置
# --------------------------------------------------------------------------- #
class SettingsScreen(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "取消")]

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-small", id="settings-dialog"):
            with Horizontal(classes="field-row"):
                yield Label("默认输入目录")
                yield Input(self.settings.input_dir, id="input-dir")
                yield Button("浏览", id="browse-input")
            with Horizontal(classes="field-row"):
                yield Label("默认输出目录")
                yield Input(self.settings.output_dir, id="output-dir")
                yield Button("浏览", id="browse-output")
            yield BoxCheckbox("扫描目录时包含子目录", value=self.settings.include_subdirs,
                           id="include-subdirs")
            with Horizontal(classes="field-row"):
                yield Label("WAV 处理")
                yield Select(WAV_OPTIONS, value=self.settings.wav_mode, allow_blank=False,
                             id="wav-mode")
            with Horizontal(classes="field-row"):
                yield Label("并行进程数")
                yield Input(str(self.settings.processes), id="processes", type="integer")
            yield Static(
                f"并行数填 0 表示自动（当前 CPU 默认 {default_process_count()}）。\n"
                f"设置文件：{escape(str(settings_path()))}",
                classes="muted",
            )
            yield Static("", id="error", classes="error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("恢复默认", id="defaults")
                yield Button("取消", id="cancel")
                yield Button("保存", id="save", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#settings-dialog").border_title = "设置"
        self.query_one("#save", Button).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _browse(self, target_id: str) -> None:
        start = self.query_one(f"#{target_id}", Input).value or os.getcwd()
        self.app.push_screen(
            FilePicker(start, pick_mode="dirs", heading="选择目录"),
            lambda result: self._apply_dir(target_id, result),
        )

    def _apply_dir(self, target_id: str, result) -> None:
        if result:
            self.query_one(f"#{target_id}", Input).value = str(result)

    def _reset_defaults(self) -> None:
        defaults = Settings()
        self.query_one("#input-dir", Input).value = defaults.input_dir
        self.query_one("#output-dir", Input).value = defaults.output_dir
        self.query_one("#include-subdirs", Checkbox).value = defaults.include_subdirs
        self.query_one("#wav-mode", Select).value = defaults.wav_mode
        self.query_one("#processes", Input).value = str(defaults.processes)
        self.query_one("#error", Static).update("")

    def _save(self) -> None:
        error = self.query_one("#error", Static)
        try:
            processes = int(self.query_one("#processes", Input).value)
        except ValueError:
            error.update("并行进程数必须是整数")
            return
        if processes < 0 or processes > 64:
            error.update("并行进程数需在 0 - 64 之间（0 = 自动）")
            return

        input_dir = expand_user(self.query_one("#input-dir", Input).value)
        if input_dir and not Path(input_dir).is_dir():
            error.update(f"默认输入目录不存在：{input_dir}")
            return
        output_dir = expand_user(self.query_one("#output-dir", Input).value) or "output"

        updated = Settings(
            input_dir=input_dir,
            output_dir=output_dir,
            include_subdirs=self.query_one("#include-subdirs", Checkbox).value,
            wav_mode=str(self.query_one("#wav-mode", Select).value),
            processes=processes,
        )
        try:
            updated.save()
        except OSError as exc:
            error.update(f"写入设置失败：{exc}")
            return
        self.dismiss(updated)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "browse-input": lambda: self._browse("input-dir"),
            "browse-output": lambda: self._browse("output-dir"),
            "defaults": self._reset_defaults,
            "cancel": self.action_cancel,
            "save": self._save,
        }
        handler = mapping.get(event.button.id or "")
        if handler:
            handler()


# --------------------------------------------------------------------------- #
# 运行进度
# --------------------------------------------------------------------------- #
class RunScreen(ModalScreen):
    BINDINGS = [Binding("escape", "stop_or_close", "停止/完成")]

    def __init__(self, tasks: list, processes: int, heading: str):
        super().__init__()
        self.tasks = list(tasks)
        self.processes = processes
        self.heading = heading
        self.results: list[tuple] = []
        self._stop_requested = False
        self._finished = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog", id="run-dialog"):
            yield Static(self.heading, classes="muted")
            yield ProgressBar(total=len(self.tasks), id="bar")
            yield Static("准备中…", id="status", classes="muted")
            yield RichLog(id="log", wrap=True, markup=True, max_lines=1000)
            with Horizontal(classes="dialog-buttons"):
                yield Button("停止", id="stop")
                yield Button("完成", id="done", variant="primary", disabled=True)

    def on_mount(self) -> None:
        self.query_one("#run-dialog").border_title = "解密进度"
        self.query_one("#log", RichLog).write(
            f"[b]共 {len(self.tasks)} 个文件，并行 {self.processes}[/b]"
        )
        self.run_tasks()

    @work(thread=True, exclusive=True)
    def run_tasks(self) -> None:
        def on_result(ok, src, out, err):
            self.app.call_from_thread(self._handle_result, ok, src, out, err)

        run_batch(
            self.tasks,
            self.processes,
            on_result=on_result,
            should_stop=lambda: self._stop_requested,
        )
        self.app.call_from_thread(self._handle_finished)

    def _handle_result(self, ok: bool, src: str, out: str, err: str) -> None:
        log = self.query_one("#log", RichLog)
        self.results.append((ok, src, out, err))
        if ok:
            log.write(f"[green]✓[/green] {escape(Path(src).name)} → [b]{escape(Path(out).name)}[/b]")
        else:
            log.write(f"[red]✗[/red] {escape(Path(src).name)}  [red]{escape(err)}[/red]")

        done = len(self.results)
        ok_count = sum(1 for item in self.results if item[0])
        self.query_one("#bar", ProgressBar).update(progress=done)
        self.query_one("#status", Static).update(
            f"已完成 {done}/{len(self.tasks)}　成功 [green]{ok_count}[/green]　"
            f"失败 [red]{done - ok_count}[/red]"
        )

    def _handle_finished(self) -> None:
        self._finished = True
        ok_count = sum(1 for item in self.results if item[0])
        fail_count = len(self.results) - ok_count
        prefix = "已停止" if self._stop_requested else "完成"
        self.query_one("#log", RichLog).write(
            f"\n[b]{prefix}[/b]：成功 {ok_count} 个，失败 {fail_count} 个"
        )
        self.query_one("#status", Static).update(
            f"{prefix}　成功 [green]{ok_count}[/green]　失败 [red]{fail_count}[/red]"
        )
        self.query_one("#stop", Button).disabled = True
        done_button = self.query_one("#done", Button)
        done_button.disabled = False
        done_button.focus()

    def action_stop_or_close(self) -> None:
        if self._finished:
            self._close()
        else:
            self._stop()

    def _stop(self) -> None:
        if self._finished or self._stop_requested:
            return
        self._stop_requested = True
        self.query_one("#status", Static).update("正在停止：等待当前文件结束…")
        self.query_one("#log", RichLog).write("[yellow]已请求停止[/yellow]")

    def _close(self) -> None:
        ok_count = sum(1 for item in self.results if item[0])
        self.dismiss(
            {
                "ok": ok_count,
                "fail": len(self.results) - ok_count,
                "total": len(self.tasks),
                "stopped": self._stop_requested,
            }
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stop":
            self._stop()
        elif event.button.id == "done":
            self._close()
