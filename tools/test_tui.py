"""TUI 无头回归测试：用 Textual 的 pilot 驱动真实界面完成一次解密。

用法（项目根目录）：
    python tools/test_tui.py

覆盖：
  1. 主界面渲染
  2. 文件选择器多选 .xm（真实按键：space / ctrl+s）
  3. 命名确认页改名并解密，校验产物文件名与大小
  4. 设置页保存后写入 settings.json
  5. 目录解密页（含子目录开关）计数与执行
"""

import asyncio
import os
import pathlib
import shutil
import sys
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

TMP_ROOT = PROJECT_ROOT / ".workbuddy" / "tmp"
TMP_ROOT.mkdir(parents=True, exist_ok=True)
WORK_DIR = pathlib.Path(tempfile.mkdtemp(prefix="tui_test_", dir=str(TMP_ROOT)))

# 隔离配置目录，避免污染真实用户设置
os.environ["XDG_CONFIG_HOME"] = str(WORK_DIR / "config")

from textual.widgets import Button, Checkbox, Input, ListView, Static  # noqa: E402

from xm_decrypt.settings import Settings, settings_path  # noqa: E402
from xm_decrypt.tui.app import MainScreen, XMDecryptApp  # noqa: E402
from xm_decrypt.tui.screens import (  # noqa: E402
    DirPlanScreen,
    FilePicker,
    PlanScreen,
    RunScreen,
    SettingsScreen,
)

SAMPLE = next(PROJECT_ROOT.glob("*.xm"))
failures = []


def static_text(widget) -> str:
    content = getattr(widget, "content", "")
    return getattr(content, "plain", None) or str(content)


def check(label, condition, detail=""):
    mark = "✓" if condition else "✗"
    print(f"  {mark} {label}{('  ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


async def wait_until(pilot, predicate, timeout=120.0):
    waited = 0.0
    while waited < timeout:
        await pilot.pause(0.1)
        waited += 0.1
        if predicate():
            return True
        if int(waited * 10) % 50 == 0:
            print(f"    ... 等待中 {waited:.0f}s", flush=True)
    return False


async def main():
    out_dir = WORK_DIR / "out"
    settings = Settings(input_dir=str(PROJECT_ROOT), output_dir=str(out_dir), processes=1)
    app = XMDecryptApp(settings)

    async with app.run_test(size=(150, 48)) as pilot:
        await pilot.pause()

        print("1) 主界面")
        check("启动后停在主界面", isinstance(app.screen, MainScreen), type(app.screen).__name__)
        summary = static_text(app.screen.query_one("#summary", Static))
        check("显示默认输入目录", "默认输入目录" in summary)
        check("显示设置文件位置", "settings.json" in summary)

        print("2) 文件选择器")
        await pilot.press("f")
        await pilot.pause()
        picker = app.screen
        check("按 f 打开选择器", isinstance(picker, FilePicker), type(picker).__name__)
        file_index = next(
            (i for i, (kind, path) in enumerate(picker._entries) if path == SAMPLE), None
        )
        check("列表里能找到样本文件", file_index is not None)

        list_view = picker.query_one("#entries", ListView)
        list_view.index = file_index
        await pilot.press("space")
        await pilot.pause()
        check("空格选中 1 个文件", len(picker.selected) == 1)

        await pilot.press("ctrl+s")
        await pilot.pause()
        plan = app.screen
        check("确定后进入命名确认页", isinstance(plan, PlanScreen), type(plan).__name__)

        print("3) 命名与解密")
        default_name = plan.query_one("#name-0", Input).value
        check("默认名取 ID3 标题", bool(default_name), default_name)
        check("输出目录预填设置值",
              plan.query_one("#out-dir", Input).value == str(out_dir))

        custom = "自定义名称 测试"
        plan.query_one("#name-0", Input).value = custom
        plan.query_one("#start", Button).press()
        await pilot.pause()
        run_screen = app.screen
        check("开始后进入运行页", isinstance(run_screen, RunScreen), type(run_screen).__name__)

        finished = await wait_until(pilot, lambda: getattr(app.screen, "_finished", False))
        check("解密任务结束", finished)
        produced = out_dir / f"{custom}.m4a"
        check("产物用自定义名", produced.is_file(), str(produced))
        size = produced.stat().st_size if produced.is_file() else 0
        # 实测：音频本体 928997 字节 + mp4 容器/标签开销 = 931174 字节。
        # 单文件不写 tracknumber 标签（只有 total > 1 时才写），因此比
        # "多文件/专辑"模式的 931206 字节少 32 字节（"1/N" 标签的体积）。
        check("产物大小为音频本体 + 容器开销", 928997 < size < 940000, f"{size} 字节")

        app.screen.query_one("#done", Button).press()
        await pilot.pause()
        check("完成后回到主界面", isinstance(app.screen, MainScreen), type(app.screen).__name__)

        print("4) 设置")
        await pilot.press("s")
        await pilot.pause()
        settings_screen = app.screen
        check("按 s 打开设置", isinstance(settings_screen, SettingsScreen),
              type(settings_screen).__name__)

        new_in = str(PROJECT_ROOT)
        new_out = str(WORK_DIR / "out2")
        settings_screen.query_one("#input-dir", Input).value = new_in
        settings_screen.query_one("#output-dir", Input).value = new_out
        settings_screen.query_one("#processes", Input).value = "2"
        settings_screen.query_one("#save", Button).press()
        await pilot.pause()
        check("保存后回到主界面", isinstance(app.screen, MainScreen), type(app.screen).__name__)
        check("设置已写入磁盘", settings_path().is_file(), str(settings_path()))
        reloaded = Settings.load()
        check("默认输出目录已持久化", reloaded.output_dir == new_out, reloaded.output_dir)
        check("并行数已持久化", reloaded.processes == 2, str(reloaded.processes))
        check("主界面同步刷新", new_out in static_text(app.screen.query_one("#summary", Static)))

        print("5) 目录解密")
        await pilot.press("d")
        await pilot.pause()
        dir_picker = app.screen
        check("按 d 打开目录选择", isinstance(dir_picker, FilePicker), type(dir_picker).__name__)
        dir_picker._goto(PROJECT_ROOT)
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        dir_plan = app.screen
        check("进入目录确认页", isinstance(dir_plan, DirPlanScreen), type(dir_plan).__name__)
        check("识别到 1 个 .xm", len(dir_plan.files) == 1, str(dir_plan.files))

        dir_out = WORK_DIR / "dirout"
        dir_plan.query_one("#out-dir", Input).value = str(dir_out)
        dir_plan.query_one("#start", Button).press()
        await pilot.pause()
        finished = await wait_until(pilot, lambda: getattr(app.screen, "_finished", False))
        check("目录任务结束", finished)
        album_files = list(dir_out.rglob("*.m4a"))
        check("产出 1 个文件（在专辑子目录里）", len(album_files) == 1,
              str([str(p.relative_to(dir_out)) for p in album_files]))
        app.screen.query_one("#done", Button).press()
        await pilot.pause()

        print("6) 子目录开关")
        tree = WORK_DIR / "tree"
        (tree / "sub").mkdir(parents=True)
        shutil.copy2(SAMPLE, tree / "a.xm")
        shutil.copy2(SAMPLE, tree / "sub" / "b.xm")

        await pilot.press("d")
        await pilot.pause()
        app.screen._goto(tree)
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        sub_plan = app.screen
        check("仅当前目录：识别 1 个", len(sub_plan.files) == 1, str(len(sub_plan.files)))
        sub_plan.query_one("#include-subdirs", Checkbox).value = True
        await pilot.pause()
        check("开启包含子目录：识别 2 个", len(sub_plan.files) == 2, str(len(sub_plan.files)))
        await pilot.press("escape")
        await pilot.pause()
        check("取消后回到主界面", isinstance(app.screen, MainScreen), type(app.screen).__name__)

        print("7) 多文件默认编号")
        multi_dir = WORK_DIR / "multi"
        multi_dir.mkdir()
        copies = []
        for index in (1, 2):
            dst = multi_dir / f"t{index}.xm"
            shutil.copy2(SAMPLE, dst)
            copies.append(str(dst))
        app.push_screen(PlanScreen(copies, app.settings))
        await pilot.pause()
        multi = app.screen
        names = [multi.query_one(f"#name-{i}", Input).value for i in range(2)]
        check(
            "编号按列表顺序而非 ID3 的 TRCK",
            names[0].startswith("1 - ") and names[1].startswith("2 - "),
            str(names),
        )
        multi.query_one("#cancel", Button).press()
        await pilot.pause()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：{failures}")
        return 1
    print("全部通过 ✓")
    return 0


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    finally:
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    sys.exit(code)
