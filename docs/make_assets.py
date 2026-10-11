"""Regenerate the README's images.

    pip install -r requirements.txt -r requirements-dev.txt
    python docs/make_assets.py

Writes to docs/assets/:

    demo.gif            a terminal session: the example is built, an old-style email is refused, the tests run
    pack.gif            the example pack, scrolled
    social-preview.png  1280x640, for the repository's social preview (Settings, then Social preview)

Nothing here is staged. The terminal text is the real output of the three commands, captured when
this script runs, and the pack is the page `examples/make_example.py` writes. All of it is fictional
data: no real business appears in any image.
"""
from __future__ import annotations

import asyncio
import html
import io
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
COMMANDS = [
    "python examples/make_example.py",
    "python src/lint_drafts.py examples/rejected.example.md",
    "python -m pytest -q",
]
TERMINAL = """<!doctype html><meta charset=utf-8><style>
html,body{margin:0;background:#0b1220}
#win{width:920px;height:560px;margin:20px;border-radius:14px;background:#0f172a;border:1px solid #1e293b;
     box-shadow:0 18px 50px rgba(0,0,0,.45);overflow:hidden;font:14px/1.6 'Cascadia Mono','Cascadia Code',Consolas,Menlo,monospace}
#bar{height:40px;background:#131c31;border-bottom:1px solid #1e293b;display:flex;align-items:center;padding:0 16px;gap:8px}
#bar i{width:12px;height:12px;border-radius:50%;display:inline-block}
#bar span{color:#64748b;font-size:13px;margin-left:12px}
pre{margin:0;padding:16px 22px;color:#cbd5e1;white-space:pre-wrap;font:inherit}
.p{color:#fbbf24}.c{color:#f8fafc}.ok{color:#34d399}.bad{color:#f87171}.dim{color:#64748b}.cur{background:#f8fafc;color:#0f172a}
</style><div id=win><div id=bar><i style="background:#ef4444"></i><i style="background:#f59e0b"></i>
<i style="background:#22c55e"></i><span>leadforge · fictional example data</span></div><pre id=out></pre></div>"""


def run(command: str) -> list[str]:
    """Run one command from the repository root and return its output lines, as a terminal would show them."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "COLUMNS": "100", "NO_COLOR": "1"}
    parts = [sys.executable] + command.split()[1:]
    done = subprocess.run(parts, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
    lines = [ln.rstrip() for ln in (done.stdout + done.stderr).splitlines() if ln.strip()]
    return [re.sub(r"=+ | =+", "", ln) for ln in lines]  # pytest pads its summary line with '='


def paint(line: str) -> str:
    """Colour a line of output the way the tools colour it on a real terminal."""
    line = html.escape(line)
    line = re.sub(r"^(ok)\b", r"<span class=ok>\1</span>", line)
    line = re.sub(r"^(FAIL)\b", r"<span class=bad>\1</span>", line)
    line = re.sub(r"^(\s+- retired signal wording:)", r"<span class=dim>\1</span>", line)
    line = re.sub(r"(\d+ passed)", r"<span class=ok>\1</span>", line)
    return line


def storyboard() -> list[tuple[str, int]]:
    """(terminal HTML, milliseconds) for every frame of the demo."""
    frames: list[tuple[str, int]] = []
    done: list[str] = []

    def show(extra: str, ms: int) -> None:
        frames.append(("\n".join(done + [extra]), ms))

    for number, command in enumerate(COMMANDS):
        output = run(command)
        prompt = "<span class=p>$</span> "
        show(prompt + "<span class=cur> </span>", 500 if number else 900)
        for cut in range(3, len(command) + 3, 3):  # typed three characters at a time
            show(prompt + f"<span class=c>{html.escape(command[:cut])}</span><span class=cur> </span>", 55)
        done.append(prompt + f"<span class=c>{html.escape(command)}</span>")
        show("", 450)
        for line in output:
            done.append(paint(line))
            show("", 110)
        done.append("")
        show("<span class=p>$</span> <span class=cur> </span>", 1700)
    frames[-1] = (frames[-1][0], 4200)
    return frames


def to_gif(shots: list[tuple[bytes, int]], path: Path, colours: int) -> None:
    images = [Image.open(io.BytesIO(png)).convert("RGB") for png, _ in shots]
    # One palette for every frame, taken from the busiest one, so colours do not shimmer between frames.
    palette = images[-1].quantize(colors=colours, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    frames = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[ms for _, ms in shots], loop=0, optimize=True)
    print(f"wrote {path.relative_to(ROOT).as_posix()}  {len(frames)} frames, {path.stat().st_size / 1024:.0f} KB")


async def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    board = storyboard()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel=os.getenv("LEADFORGE_BROWSER", "msedge"), headless=True)

        page = await browser.new_page(viewport={"width": 960, "height": 600})
        await page.set_content(TERMINAL)
        shots = []
        for text, ms in board:
            await page.evaluate("t => document.getElementById('out').innerHTML = t", text)
            shots.append((await page.screenshot(), ms))
        to_gif(shots, ASSETS / "demo.gif", colours=128)
        await page.close()

        page = await browser.new_page(viewport={"width": 880, "height": 600})
        await page.goto((ROOT / "examples" / "northlight-growth.example.html").as_uri())
        height = await page.evaluate("document.documentElement.scrollHeight")
        stops = [0, 0, 560, 560, 1180, 1180, 1820, 1820, min(2480, height - 600)]
        shots, steps = [], 14
        for start, end in zip(stops, stops[1:]):
            if start == end:
                shots.append((await page.screenshot(), 1500))
                continue
            for step in range(1, steps + 1):
                eased = 0.5 - 0.5 * math.cos(math.pi * step / steps)
                await page.evaluate("y => window.scrollTo(0, y)", start + (end - start) * eased)
                shots.append((await page.screenshot(), 45))
        shots[-1] = (shots[-1][0], 3200)
        to_gif(shots, ASSETS / "pack.gif", colours=64)
        await page.close()

        page = await browser.new_page(viewport={"width": 1280, "height": 640})
        banner = (ASSETS / "banner.svg").read_text(encoding="utf-8").replace('width="1280" height="420"', 'width="1180"')
        await page.set_content(
            "<body style='margin:0;background:#070c16;display:flex;align-items:center;justify-content:center;height:640px'>"
            f"<div style='width:1180px'>{banner}</div>")
        await page.wait_for_timeout(6_000)  # let the ticks and the strike-through finish drawing
        (ASSETS / "social-preview.png").write_bytes(await page.screenshot())
        print("wrote docs/assets/social-preview.png")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
