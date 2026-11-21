"""TUI 应用与主界面。"""

from __future__ import annotations

import pathlib
import sys

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ..batch import make_task
from ..metadata import scan_xm_files
from ..settings import Settings, settings_path
from .picker import FilePicker, expand_user
from .screens import DirPlanScreen, PlanScreen, RunScreen, SettingsScreen

_STYLE_FILE = pathlib.Path(__file__).with_name("styles.tcss")


def _read_archive_css() -> str:
    """从包资源里读样式文本，供 .pyz 单文件运行时使用。"""
    if _STYLE_FILE.is_file():
        return ""
    try:
        from importlib import resources

        return resources.files(__package__).joinpath("styles.tcss").read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - 样式缺失不应阻断启动，用默认外观
        return ""


_ARCHIVE_CSS = _read_archive_css()


class MainScreen(Screen):
    BINDINGS = [
        Binding("q", "quit_app", "退出"),
        Binding("f", "pick_files", "文件解密"),
        Binding("d", "pick_dir", "目录解密"),
        Binding("s", "open_settings", "设置"),
    ]

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.last_result: dict | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("XM 解密工具", id="logo")
                yield Button("解密 .xm 文件", id="btn-files", variant="primary")
                yield Button("解密整个目录", id="btn-dir")
                yield Button("设置", id="btn-settings")
                yield Button("退出", id="btn-quit")
            with VerticalScroll(id="panel"):
                yield Static("", id="summary")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_summary()
        self.query_one("#btn-files", Button).focus()

    def refresh_summary(self) -> None:
        settings = self.settings
        wav_label = "保留 WAV" if settings.wav_mode == "keep" else "转 ALAC (.m4a)"
        lines = [
            "[b]当前设置[/b]",
            f"默认输入目录：{escape(settings.resolved_input_dir())}",
            f"默认输出目录：{escape(settings.resolved_output_dir())}",
            f"扫描含子目录：{'是' if settings.include_subdirs else '否'}",
            f"WAV 处理：{wav_label}",
            f"并行进程：{settings.effective_processes()}",
            f"设置文件：{escape(str(settings_path()))}",
        ]
        if self.last_result:
            status = "已停止" if self.last_result.get("stopped") else "完成"
            lines += [
                "",
                "[b]上次任务[/b]",
                f"{status}：共 {self.last_result['total']} 个，"
                f"成功 {self.last_result['ok']}，失败 {self.last_result['fail']}",
            ]
        lines += [
            "",
            "[b]快捷键[/b]  F 文件解密　D 目录解密　S 设置　Q 退出",
            "",
            "[dim]本工具仅供学习交流使用，严禁用于商业用途。[/dim]",
        ]
        self.query_one("#summary", Static).update("\n".join(lines))

    # ---------- 导航 ----------
    def action_pick_files(self) -> None:
        self.app.push_screen(
            FilePicker(self.settings.resolved_input_dir(), pick_mode="files"),
            self._on_files_picked,
        )

    def _on_files_picked(self, result) -> None:
        if not result:
            return
        self.app.push_screen(PlanScreen(list(result), self.settings), self._on_plan_ready)

    def action_pick_dir(self) -> None:
        self.app.push_screen(
            FilePicker(self.settings.resolved_input_dir(), pick_mode="dirs",
                       heading="选择要解密的目录"),
            self._on_dir_picked,
        )

    def _on_dir_picked(self, result) -> None:
        if not result:
            return
        files = scan_xm_files(str(result), recursive=self.settings.include_subdirs)
        if not files:
            self.notify("该目录下没有 .xm 文件，可在设置里开启“包含子目录”后重试",
                        severity="warning")
            return
        self.app.push_screen(DirPlanScreen(str(result), self.settings), self._on_plan_ready)

    def action_open_settings(self) -> None:
        self.app.push_screen(SettingsScreen(self.settings), self._on_settings_saved)

    def _on_settings_saved(self, result) -> None:
        if result is None:
            return
        self.settings = result
        self.app.settings = result
        self.refresh_summary()
        self.notify("设置已保存")

    # ---------- 执行 ----------
    def _on_plan_ready(self, plan) -> None:
        if not plan:
            return
        tasks = self.build_tasks(plan)
        # 进程数不超过文件数，避免为 1 个文件拉起 8 个进程。
        processes = max(1, min(plan["processes"], len(tasks)))
        heading = (
            f"解密 {len(tasks)} 个文件 · 并行 {processes} · "
            f"输出 {expand_user(plan['output_dir'])}"
        )
        self.app.push_screen(RunScreen(tasks, processes, heading), self._on_run_finished)

    @staticmethod
    def build_tasks(plan: dict) -> list:
        """把界面上的计划翻译成可序列化的任务元组。

        多文件时按列表顺序（1..N）编号并写入 tracknumber 标签；自定义命名
        模式下不建专辑子目录。
        """
        files = plan["files"]
        names = plan.get("names")
        total = len(files)
        tag_total = total if total > 1 else None
        tasks = []
        for index, path in enumerate(files):
            tasks.append(
                make_task(
                    path,
                    plan["output_dir"],
                    name=names[index] if names else None,
                    album_subdir=bool(plan.get("album")),
                    track_no=index + 1 if tag_total else None,
                    track_total=tag_total,
                    wav_mode=plan.get("wav_mode", "keep"),
                )
            )
        return tasks

    def _on_run_finished(self, result) -> None:
        if result:
            self.last_result = result
            self.refresh_summary()

    def action_quit_app(self) -> None:
        self.app.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "btn-files": self.action_pick_files,
            "btn-dir": self.action_pick_dir,
            "btn-settings": self.action_open_settings,
            "btn-quit": self.action_quit_app,
        }
        handler = mapping.get(event.button.id or "")
        if handler:
            handler()


class XMDecryptApp(App):
    # 磁盘上存在样式文件时走 CSS_PATH（保留开发期热重载）；
    # 打进 .pyz 后磁盘上没有该文件，改为从归档内读取文本。
    # 若仍用 CSS_PATH，Textual 会用 inspect.getfile() 拼出
    # ".../app.pyz/xm_decrypt/tui/styles.tcss" 这种不存在的路径而报错。
    CSS_PATH = "styles.tcss" if _STYLE_FILE.exists() else None
    CSS = "" if _STYLE_FILE.exists() else _ARCHIVE_CSS
    TITLE = "喜马拉雅 XM 解密工具"
    SUB_TITLE = "仅供学习交流使用"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings if settings is not None else Settings.load()

    def on_mount(self) -> None:
        self.push_screen(MainScreen(self.settings))


def run_tui() -> int:
    import multiprocessing

    # 非交互环境（管道、CI、cron）下 Textual 会卡住而不是报错，先显式拦截。
    if not sys.stdout.isatty():
        print("当前环境不是交互式终端，无法启动 TUI。")
        print("可改用命令行模式：python main.py --cli -h")
        return 1

    multiprocessing.freeze_support()
    try:
        XMDecryptApp(Settings.load()).run()
    except Exception as exc:  # noqa: BLE001 - 启动失败时给出可读提示
        print(f"启动失败：{type(exc).__name__}: {exc}")
        return 1
    return 0
