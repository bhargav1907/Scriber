# Antigravity & Gemini Agent Instructions for Scriber

Refer to [`AGENTS.md`](./AGENTS.md) for full architectural guidelines, navigation rules, and technical invariants.

## Core Directives
1. **Always inspect `REPO_MAP.md` first**: Do not use broad `grep` or file reads; `REPO_MAP.md` contains the full class, signature, and IPC map in ~1,600 tokens.
2. **Update Map on Signature Changes**: Run `npm run map` after adding or modifying functions, endpoints, or IPC bridges.
3. **Use LSP (`code-lsp`) for Precision**: Use `go_to_definition` and `find_references` instead of raw text regex.
4. **Local & Private**: Everything runs locally on Apple Silicon (MLX Metal GPU Whisper + Ollama).
5. **Keep `README.md` Synchronized**: Update `README.md` whenever significant architectural, security, performance, or UI improvements occur.
6. **Attentional Anchoring & Question-First**: Resolve the user's immediate question or visual artifact first before executing any secondary work. Never initiate unasked refactorings.
7. **Targeted Scope Slicing**: Files > 150 lines MUST use `StartLine`/`EndLine` around target functions found in `REPO_MAP.md`. No blind full-file dumps.
8. **Quiet Test Invariant**: Run tests in quiet mode (`-q`) targeting specific methods to prevent stdout context bloat.
9. **Token Breakdown Invariant**: Conclude EVERY assistant message with a clean token summary at the very bottom (e.g., `> 📊 **Input Tokens:** ~15.5k | **Output Tokens:** ~380`), reporting the turn's prompt context tokens and generated output tokens. No timing or timestamps.
