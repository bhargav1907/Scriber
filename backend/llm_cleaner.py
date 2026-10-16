"""
Scriber — LLM Text Cleanup via Ollama
Cleans up raw transcriptions: removes filler words, fixes punctuation, etc.
"""

import httpx

CLEANUP_PROMPT = """Clean up this speech transcription. Follow these rules strictly:
1. Remove filler words (um, uh, like, you know, basically, actually, so, well, I mean)
2. Fix punctuation and capitalization
3. Fix obvious speech-to-text errors
4. Keep the original meaning, tone, and intent exactly
5. Do NOT add any new content, commentary, or explanation
6. Return ONLY the cleaned text — nothing else, no quotes, no preamble

Transcription: {text}

Cleaned text:"""


class LLMCleaner:
    def __init__(self, model: str = "llama3.2:3b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    async def cleanup(self, raw_text: str) -> str:
        """
        Send raw transcription to Ollama for cleanup.
        Returns cleaned text, or the original if cleanup fails.
        """
        if not raw_text or not raw_text.strip():
            return ""

        prompt = CLEANUP_PROMPT.format(text=raw_text)

        max_tokens = max(int(len(raw_text.split()) * 2) + 20, 50)
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

                # Strip quotes the LLM might wrap the output in
                if len(cleaned) >= 2:
                    if (cleaned[0] == '"' and cleaned[-1] == '"') or \
                       (cleaned[0] == "'" and cleaned[-1] == "'"):
                        cleaned = cleaned[1:-1].strip()

                return cleaned if cleaned else raw_text

        except Exception as e:
            print(f"[Scriber] LLM cleanup failed (falling back to raw text): {e}")
            return raw_text

    async def check_connection(self) -> bool:
        """Check if Ollama is running and reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.host}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
