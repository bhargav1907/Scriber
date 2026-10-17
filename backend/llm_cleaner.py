"""
Scriber — LLM Text Cleanup via Ollama
Cleans up raw transcriptions: removes filler words, fixes punctuation, etc.
"""
import re
import httpx

MODE_PROMPTS = {
    "general": """Clean up this spoken audio transcription for general use:
1. Remove filler words (um, uh, like, you know, basically, actually, so, well, I mean).
2. Fix punctuation, capitalization, numbers, and grammar.
3. Keep the original meaning, tone, and intent exactly.
4. Do NOT add preamble, markdown fences, or explanations.
5. Return ONLY the cleaned text.""",

    "email": """Clean up this spoken dictation into a polished, professional email draft:
1. Format into clean, professional paragraphs with proper punctuation and business tone.
2. Remove all filler words, false starts, and repetitions.
3. If greeting or sign-off is spoken, format them cleanly on their own lines.
4. Do NOT invent dates, names, or fake details.
5. Return ONLY the drafted email text.""",

    "code": """Clean up this spoken dictation for a software engineer / developer:
1. Format variable names, functions, and files into code formatting (camelCase, snake_case, or backticks where appropriate).
2. Remove filler words and speech stumbles.
3. Keep commit messages, code comments, or code explanations crisp and technically accurate.
4. Return ONLY the cleaned developer text.""",

    "notes": """Clean up this spoken dictation into structured, organized notes:
1. Format into clear sentences or clean bullet points if lists were spoken.
2. Remove filler words and redundancies.
3. Keep key points distinct, scannable, and concise.
4. Return ONLY the structured notes.""",

    "chat": """Clean up this spoken dictation for a casual chat message (Slack, Discord, Messages):
1. Keep it natural, punchy, and conversational.
2. Remove filler words (um, uh, like).
3. Keep modern phrasing and casual tone; avoid sounding like a formal letter.
4. Return ONLY the cleaned message.""",
}


class LLMCleaner:
    def __init__(self, model: str = "llama3.2:3b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    async def cleanup(
        self,
        raw_text: str,
        mode: str = "general",
        custom_vocabulary: list[str] | None = None,
        word_replacements: dict[str, str] | None = None,
    ) -> str:
        """
        Send raw transcription to Ollama for cleanup with context mode & custom vocab,
        then apply word replacements.
        """
        if not raw_text or not raw_text.strip():
            return ""

        # Raw mode bypasses LLM cleanup
        if mode == "raw":
            return self._apply_replacements(raw_text.strip(), word_replacements)

        base_instructions = MODE_PROMPTS.get(mode, MODE_PROMPTS["general"])
        vocab_hint = ""
        if custom_vocabulary:
            valid_vocabs = [v.strip() for v in custom_vocabulary if v and v.strip()]
            if valid_vocabs:
                vocab_hint = f"\nAlways spell, format, and capitalize these terms/names exactly as: {', '.join(valid_vocabs)}."

        prompt = f"""{base_instructions}{vocab_hint}

Transcription: {raw_text}

Cleaned text:"""

        max_tokens = max(int(len(raw_text.split()) * 2) + 30, 60)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "keep_alive": "24h",
                        "options": {
                            "temperature": 0.1,
                            "num_predict": max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                result = response.json()
                cleaned = result.get("response", raw_text).strip()

                # Strip surrounding quotes if wrapped
                if len(cleaned) >= 2:
                    if (cleaned[0] == '"' and cleaned[-1] == '"') or \
                       (cleaned[0] == "'" and cleaned[-1] == "'"):
                        cleaned = cleaned[1:-1].strip()

                final_text = cleaned if cleaned else raw_text
                return self._apply_replacements(final_text, word_replacements)

        except Exception as e:
            print(f"[Scriber] LLM cleanup failed (falling back to raw text): {e}")
            return self._apply_replacements(raw_text, word_replacements)

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
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
