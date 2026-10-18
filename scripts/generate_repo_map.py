#!/usr/bin/env python3
"""
Scriber — Lightweight Architectural Repo Map Generator
Parses Python AST and JavaScript codebases to generate a compact, token-efficient
structural map (classes, function signatures, IPC channels, WebSocket routes)
for AI pair programmers without ingesting full file contents.
"""

import os
import ast
import re
from pathlib import Path


def generate_repo_map(repo_root: Path) -> str:
    lines = [
        "# 🗺️ Scriber Codebase Architecture Map",
        "> Auto-generated AST & structural symbol map for token-efficient agent navigation.",
        "> Keep this map updated to provide instant whole-repo awareness in ~1,000 tokens.",
        "",
    ]

    # 1. Python Backend Files
    py_files = sorted(repo_root.glob("backend/*.py"))
    if py_files:
        lines.append("## 🐍 Python Backend (`backend/`)")
        for f in py_files:
            rel = f.relative_to(repo_root)
            if f.name.startswith("."):
                continue
            try:
                content = f.read_text(encoding="utf-8")
                tree = ast.parse(content)
                lines.append(f"\n### `{rel}`")
                
                # Module docstring
                doc = ast.get_docstring(tree)
                if doc:
                    first_line = doc.strip().split("\n")[0]
                    lines.append(f"  > {first_line}")

                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                        base_str = f"({', '.join(bases)})" if bases else ""
                        lines.append(f"  - **class `{node.name}{base_str}`**")
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                if not item.name.startswith("__") or item.name == "__init__":
                                    args = [a.arg for a in item.args.args]
                                    prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                                    lines.append(f"    - `{prefix} {item.name}({', '.join(args)})`")

                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [a.arg for a in node.args.args]
                        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                        # Check for FastAPI decorators
                        decs = []
                        for d in node.decorator_list:
                            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
                                decs.append(f"@{d.func.value.id}.{d.func.attr}")
                        dec_str = f" [{' '.join(decs)}]" if decs else ""
                        lines.append(f"  - `{prefix} {node.name}({', '.join(args)})`{dec_str}")

            except Exception as e:
                lines.append(f"  - *(Could not parse: {e})*")

    # 2. JavaScript / Electron Main & Preload
    lines.append("\n## ⚡ Electron & Frontend (`main.js`, `preload.js`, `src/`)")
    js_files = [repo_root / "main.js", repo_root / "preload.js"] + sorted(repo_root.glob("src/*.js"))
    for f in js_files:
        if not f.exists() or "node_modules" in str(f):
            continue
        rel = f.relative_to(repo_root)
        content = f.read_text(encoding="utf-8")
        lines.append(f"\n### `{rel}`")

        # Extract top comment
        first_comment = re.search(r"/\*\*\s*\n\s*\*\s*([^\n*]+)", content)
        if first_comment:
            lines.append(f"  > {first_comment.group(1).strip()}")

        # IPC listeners in main.js
        ipcs = re.findall(r"ipcMain\.on\(['\"]([^'\"]+)['\"]", content)
        for ipc in sorted(set(ipcs)):
            lines.append(f"  - *IPC Receive:* `ipcMain.on('{ipc}')`")

        # IPC send in preload.js
        exposed = re.findall(r"([a-zA-Z0-9_$]+)\s*:\s*\([^)]*\)\s*=>\s*ipcRenderer\.(?:send|on)\(['\"]([^'\"]+)['\"]", content)
        for method, channel in sorted(set(exposed)):
            lines.append(f"  - *Bridge:* `scriber.{method}()` ↔ `{channel}`")

        # Top-level Functions
        funcs = re.findall(r"(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(([^)]*)\)", content)
        for name, args in funcs:
            lines.append(f"  - `function {name}({args.strip()})`")

    return "\n".join(lines)


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    map_text = generate_repo_map(repo_root)
    out_file = repo_root / "REPO_MAP.md"
    out_file.write_text(map_text, encoding="utf-8")

    char_count = len(map_text)
    est_tokens = char_count // 4
    print(f"✓ Generated {out_file} ({char_count} chars, ~{est_tokens} tokens)")
