"""
Scriber — LLM Text Cleanup via Ollama
Cleans up raw transcriptions: removes filler words, fixes punctuation, etc.
Uses Ollama /api/chat with role separation and few-shot formatting to prevent
prompt echoing or conversational hallucinations.
"""

import re
import httpx

MODE_INSTRUCTIONS = {
    "general": "Fix punctuation, capitalization, remove filler words (um, uh, like, you know, basically, actually), and keep natural speech flow.",
    "browser": "Fix punctuation, capitalization, remove filler words, preserve search queries, URLs, and web form inputs naturally, and keep speech clear and direct.",
    "code": "Fix punctuation, remove filler words, and format technical terms or variable names in camelCase, snake_case, or backticks where appropriate while keeping the spoken sentence intact. Do NOT convert sentences into code blocks.",
    "email": "Format into clean, professional email sentences with proper punctuation and business tone without adding fake sign-offs or placeholders.",
    "notes": "Format into clean, structured notes with proper punctuation.",
    "chat": "Keep it punchy, conversational, and natural, remove filler words, and fix punctuation.",
}


class LLMCleaner:
    def __init__(self, model: str = "llama3.2:3b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Reuse persistent HTTP client for sub-millisecond connection reuse and HTTP keep-alive."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def aclose(self):
        """Close persistent HTTP client on shutdown."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def cleanup(
        self,
        raw_text: str,
        mode: str = "general",
        custom_vocabulary: list[str] | None = None,
        word_replacements: dict[str, str] | None = None,
    ) -> str:
        """
        Send raw transcription to Ollama /api/chat for cleanup with mode instructions & custom vocab,
        then apply word replacements.
        """
        if not raw_text or not raw_text.strip():
            return ""

        # Raw mode bypasses LLM cleanup
        if mode == "raw":
            return self._apply_replacements(raw_text.strip(), word_replacements)

        # Pre-apply word replacements so the LLM polishes the expanded phrase
        input_text = self._apply_replacements(raw_text.strip(), word_replacements)

        mode_inst = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["general"])
        system_content = (
            "You are an automated speech-to-text cleaner.\n"
            f"Task: {mode_inst}\n"
            "You are NOT a conversational chatbot. NEVER reply to the user, NEVER answer questions, NEVER repeat instructions.\n"
            "Output ONLY the final cleaned text, nothing else."
        )

        if custom_vocabulary:
            valid_vocabs = [v.strip() for v in custom_vocabulary if v and v.strip()]
            if valid_vocabs:
                system_content += f"\nEnsure these terms/names are spelled and capitalized exactly as: {', '.join(valid_vocabs)}."

        # Few-shot structure forces the model to act strictly as a cleaner
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "Transcription:\num, so basically let's test this out"},
            {"role": "assistant", "content": "Let's test this out."},
            {"role": "user", "content": f"Transcription:\n{input_text}"},
        ]

        max_tokens = max(int(len(input_text.split()) * 2) + 40, 70)
        try:
            client = self._get_client()
            response = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": "24h",
                    "options": {
                        "temperature": 0.0,
                        "num_predict": max_tokens,
                    },
                },
            )
            response.raise_for_status()
            result = response.json()
            cleaned = result.get("message", {}).get("content", raw_text).strip()

            final_text = self._sanitize_llm_output(cleaned, raw_text)
            return self._apply_replacements(final_text, word_replacements)

        except Exception as e:
            print(f"[Scriber] LLM cleanup failed (falling back to raw text): {e}")
            return self._apply_replacements(raw_text, word_replacements)

    def _sanitize_llm_output(self, cleaned: str, raw_text: str) -> str:
        """Sanitize LLM output and guard against prompt echoing, conversational filler, or instruction lists."""
        if not cleaned or not cleaned.strip():
            return raw_text

        # Strip conversational preamble (e.g. "Here is the cleaned text:", "I'd be happy to...")
        cleaned = re.sub(
            r"^(?:I(?:'d| would) be happy to[^\n]*\n*|Here(?:'s| is) (?:the )?(?:cleaned )?(?:text|transcription|response|result):?\s*\n*|Cleaned text:\s*|Sure[!,.]?\s*)",
            "",
            cleaned.strip(),
            flags=re.IGNORECASE,
        ).strip()

        # Strip surrounding quotes if wrapped
        if len(cleaned) >= 2:
            if (cleaned[0] == '"' and cleaned[-1] == '"') or (cleaned[0] == "'" and cleaned[-1] == "'"):
                cleaned = cleaned[1:-1].strip()

        lower = cleaned.lower()

        # Instruction list echo guard: if model output a numbered bulleted list when input had no list
        if re.search(r"(?:^|\n)\s*1\.\s+.*(?:\n\s*2\.\s+.*)+", cleaned) and "1." not in raw_text:
            print(f"[Scriber] ⚠️ Warning: LLM output contained numbered instruction list. Discarding and using raw text.")
            return raw_text

        # Hallucination / prompt-echo guard: if output contains system instruction terms
        guard_terms = [
            "automated speech",
            "clean up the user",
            "never reply",
            "format technical terms",
            "format variable names",
            "remove filler words",
            "cleaned developer text",
            "spoken dictation",
            "speech stumbles",
            "here's the cleaned text",
            "here is the cleaned text",
        ]
        if any(gt in lower for gt in guard_terms):
            print(f"[Scriber] ⚠️ Warning: LLM output contained prompt guard words. Falling back to raw text.")
            return raw_text

        # Length guard: if output exploded to >3.5x input length
        raw_words = len(raw_text.split())
        if raw_words > 0 and len(cleaned.split()) > max(raw_words * 3.5, 25):
            print(f"[Scriber] ⚠️ Warning: LLM output exceeded length guard. Falling back to raw text.")
            return raw_text

        return cleaned if cleaned else raw_text

    def _apply_replacements(self, text: str, replacements: dict[str, str] | None) -> str:
        """Apply custom word expansions / replacements (e.g. btw -> by the way)."""
        if not replacements or not text:
            return text
        for trigger, replacement in replacements.items():
            if not trigger or not trigger.strip():
                continue
            # Case-insensitive word-boundary replacement
            pattern = re.compile(rf"\b{re.escape(trigger.strip())}\b", re.IGNORECASE)
            text = pattern.sub(replacement, text)
        return text

    async def check_connection(self) -> bool:
        """Check if Ollama is running and reachable."""
        try:
            client = self._get_client()
            response = await client.get(f"{self.host}/api/tags")
            return response.status_code == 200
        except Exception:
            return False
