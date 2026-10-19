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

    def normalize_text(
        self,
        text: str,
        custom_vocabulary: list[str] | None = None,
        word_replacements: dict[str, str] | None = None,
        app_name: str | None = None,
    ) -> str:
        """
        Fast deterministic acoustic normalization:
        1. Contextual phonetic homophone fixes (e.g. 'cloud desktop app' -> 'Claude desktop app', 'get hub' -> 'GitHub')
        2. Custom vocabulary exact capitalization
        3. Word replacements
        """
        if not text:
            return ""
        text = self._apply_phonetic_fixes(text, app_name=app_name)
        text = self._apply_custom_vocab(text, custom_vocabulary)
        text = self._apply_replacements(text, word_replacements)
        return text

    def _apply_phonetic_fixes(self, text: str, app_name: str | None = None) -> str:
        """
        Fix common speech-to-text acoustic collisions and homophones where Whisper
        substitutes high-frequency dictionary words for proper technical nouns.
        """
        if not text:
            return text
        res = text

        # 1. Claude vs Cloud:
        # - Phrases where 'cloud' is paired with Claude products, models, or apps
        res = re.sub(r'\b(the\s+)?cloud\s+(desktop\s+app|desktop|code|cli|opus|sonnet|haiku|3(?:\.5|\.7)?|model|ai)\b', r'\1Claude \2', res, flags=re.IGNORECASE)
        # - Anthropic's cloud -> Anthropic's Claude
        res = re.sub(r'\b(anthropic(?:\'s)?)\s+cloud\b', r'\1 Claude', res, flags=re.IGNORECASE)
        # - Conversational verbs addressing the AI: ask cloud, tell cloud, using cloud, with cloud
        res = re.sub(r'\b(ask|telling|tell|prompt|using|with|via)\s+cloud\b', r'\1 Claude', res, flags=re.IGNORECASE)
        # - Agentic actions: cloud wrote, cloud generated, cloud suggested, cloud answered
        res = re.sub(r'\bcloud\s+(wrote|generated|suggested|answered|replied|said)\b', r'Claude \1', res, flags=re.IGNORECASE)
        # - If frontmost application is Claude, standalone 'cloud' is almost always Claude
        if app_name and app_name.lower() in ("claude", "claude desktop"):
            res = re.sub(r'\bcloud\b', 'Claude', res, flags=re.IGNORECASE)

        # 2. General tech acoustic split/homophone fixes
        res = re.sub(r'\b(get\s+hub|git\s+hub)\b', 'GitHub', res, flags=re.IGNORECASE)
        res = re.sub(r'\bmac\s+os\b', 'macOS', res, flags=re.IGNORECASE)
        res = re.sub(r'\b(chat\s*gpt|chat\s+g\s*p\s*t)\b', 'ChatGPT', res, flags=re.IGNORECASE)
        res = re.sub(r'\bopen\s*a\s*i\b', 'OpenAI', res, flags=re.IGNORECASE)
        res = re.sub(r'\b(v\s*s\s*code|visual\s+studio\s+code)\b', 'VS Code', res, flags=re.IGNORECASE)
        res = re.sub(r'\b(anti\s*gravity|ant\s+gravity)\b', 'Antigravity', res, flags=re.IGNORECASE)
        res = re.sub(r'\byou\s+tube\b', 'YouTube', res, flags=re.IGNORECASE)

        return res

    def _apply_custom_vocab(self, text: str, custom_vocabulary: list[str] | None = None) -> str:
        """Enforce exact casing from custom vocabulary on recognized words."""
        if not text or not custom_vocabulary:
            return text
        for term in custom_vocabulary:
            if not term or not isinstance(term, str):
                continue
            term_clean = term.strip()
            if not term_clean:
                continue
            pattern = re.compile(rf'\b{re.escape(term_clean)}\b', re.IGNORECASE)
            text = pattern.sub(term_clean, text)
        return text

    async def cleanup(
        self,
        raw_text: str,
        mode: str = "general",
        custom_vocabulary: list[str] | None = None,
        word_replacements: dict[str, str] | None = None,
        app_name: str | None = None,
    ) -> str:
        """
        Send raw transcription to Ollama /api/chat for cleanup with mode instructions & custom vocab,
        then apply word replacements and phonetic normalization.
        """
        if not raw_text or not raw_text.strip():
            return ""

        # Raw mode bypasses LLM cleanup but still applies deterministic normalizations
        if mode == "raw":
            return self.normalize_text(raw_text.strip(), custom_vocabulary, word_replacements, app_name)

        # Pre-apply phonetic fixes and word replacements so LLM works on correct terms
        input_text = self._apply_phonetic_fixes(raw_text.strip(), app_name=app_name)
        input_text = self._apply_replacements(input_text, word_replacements)

        matching_vocab = []
        if custom_vocabulary:
            input_lower = input_text.lower()
            matching_vocab = [
                v.strip() for v in custom_vocabulary
                if v and v.strip() and v.strip().lower() in input_lower
            ]

        mode_inst = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["general"])
        system_content = (
            "You are an automated speech-to-text cleaner.\n"
            f"Task: {mode_inst}\n"
            "CRITICAL RULE: Do NOT substitute words, do NOT replace names, and do NOT swap terms. Keep all spoken words intact.\n"
            "You are NOT a conversational chatbot. NEVER reply to the user, NEVER answer questions, NEVER repeat instructions.\n"
            "Output ONLY the final cleaned text, nothing else."
        )

        if matching_vocab:
            system_content += f"\nEnsure proper spelling and capitalization for: {', '.join(matching_vocab)}."

        if app_name:
            system_content += f"\nActive macOS application: {app_name}."

        # Few-shot structure forces the model to act strictly as a cleaner
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "Transcription:\num, so basically let's test this out with claude on mac os"},
            {"role": "assistant", "content": "Let's test this out with Claude on macOS."},
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
            return self.normalize_text(final_text, custom_vocabulary, word_replacements, app_name)

        except Exception as e:
            print(f"[Scriber] LLM cleanup failed (falling back to normalized text): {e}")
            return self.normalize_text(raw_text, custom_vocabulary, word_replacements, app_name)

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
