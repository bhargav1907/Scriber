# Antigravity & Gemini Agent Instructions for Scriber

Refer to [`AGENTS.md`](./AGENTS.md) for full architectural guidelines, navigation rules, and technical invariants.

## Core Directives
1. **Always inspect `REPO_MAP.md` first**: Do not use broad `grep` or file reads; `REPO_MAP.md` contains the full class, signature, and IPC map in ~1,600 tokens.
2. **Update Map on Signature Changes**: Run `npm run map` after adding or modifying functions, endpoints, or IPC bridges.
3. **Use LSP (`code-lsp`) for Precision**: Use `go_to_definition` and `find_references` instead of raw text regex.
4. **Local & Private**: Everything runs locally on Apple Silicon (MLX Metal GPU Whisper + Ollama).
