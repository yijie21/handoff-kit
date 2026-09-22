#!/usr/bin/env python3
"""SessionStart hook: inject the project's handoff notes into a fresh session.

Injects STATE.md in full (it is capped by the /handoff command) and only the
headings of DECISIONS.md plus its path, so an append-only decision log that
grows for months never re-inflates the context we just paid to clear.

Silent no-op when the project has no STATE.md.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE = "STATE.md"
DECISIONS = "DECISIONS.md"

MAX_WALK_UP = 5
STATE_BYTE_CAP = 32_000  # safety valve; /handoff enforces the real 150-line limit
STALE_AFTER_SECONDS = 6 * 3600
SOURCE_SUFFIXES = {
    ".py", ".sh", ".c", ".cc", ".cpp", ".h", ".hpp", ".cu", ".rs", ".go",
    ".js", ".ts", ".tsx", ".lua", ".yaml", ".yml", ".toml", ".json", ".cfg",
}
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "wandb", "runs",
    "outputs", "checkpoints", "ckpt", "logs", "data", ".hf_home", ".cache",
}


def find_project_root(start: Path) -> Path | None:
    """Walk up a bounded number of levels looking for STATE.md."""
    cur = start.resolve()
    for depth, path in enumerate([cur, *cur.parents]):
        if depth > MAX_WALK_UP or path == path.parent:
            break
        if (path / STATE).is_file():
            return path
    return None


def newest_source_mtime(root: Path) -> float:
    """Most recent mtime among source files, preferring git for speed."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True, timeout=5, check=True, text=True,
        ).stdout
        names = [n for n in out.split("\0") if n]
    except (subprocess.SubprocessError, OSError):
        names = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            names.extend(str(Path(dirpath, f).relative_to(root)) for f in filenames)
            if len(names) > 20_000:
                break

    newest = 0.0
    for name in names:
        if Path(name).suffix not in SOURCE_SUFFIXES:
            continue
        try:
            newest = max(newest, (root / name).stat().st_mtime)
        except OSError:
            continue
    return newest


def decision_headings(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [ln.rstrip() for ln in lines if ln.startswith("#")]


def build_context(root: Path) -> str:
    state_path = root / STATE
    try:
        state = state_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    truncated = len(state.encode("utf-8")) > STATE_BYTE_CAP
    if truncated:
        state = state.encode("utf-8")[:STATE_BYTE_CAP].decode("utf-8", errors="ignore")

    parts = [f"# 项目交接上下文 — {root}", ""]

    newest = newest_source_mtime(root)
    try:
        state_mtime = state_path.stat().st_mtime
    except OSError:
        state_mtime = 0.0
    if newest and state_mtime and newest - state_mtime > STALE_AFTER_SECONDS:
        age_h = int((newest - state_mtime) / 3600)
        parts += [
            f"> ⚠️ **STATE.md 可能已过期** — 它比最新改动的源文件早 {age_h} 小时。",
            "> 若本目录是从别处复制而来，这份状态可能属于另一个实验。动手前先与用户确认。",
            "",
        ]

    parts += [f"## {STATE}（完整）", "", state.rstrip()]
    if truncated:
        parts += ["", f"_[已截断，完整内容见 {state_path}]_"]

    dec_path = root / DECISIONS
    if dec_path.is_file():
        heads = decision_headings(dec_path)
        parts += ["", f"## {DECISIONS} — 仅目录（按需自行读取全文）", ""]
        parts += heads if heads else ["_（无标题）_"]
        parts += [
            "",
            f"完整决策记录在 `{dec_path}`。需要某条决策的理由或被否决的方案时，"
            "用 Read 自行读取——不要假设你已经知道内容。",
        ]

    parts += [
        "",
        "---",
        "**开局要求**：先说明以上交接里哪些地方不明确或缺少必要信息，等用户确认后再动手。",
    ]
    return "\n".join(parts)


def main() -> int:
    try:
        sys.stdin.read()
    except Exception:
        pass

    root = find_project_root(Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())))
    if root is None:
        return 0

    context = build_context(root)
    if not context:
        return 0

    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # A hook must never break session startup.
        sys.exit(0)
