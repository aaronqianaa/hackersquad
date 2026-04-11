import base64
from pathlib import Path
from typing import Any

from app.core.config import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional import path for offline/test setups
    OpenAI = None


class OpenAIProvider:
    def __init__(self) -> None:
        pass

    def _client(self) -> Any:
        if not settings.openai_api_key or OpenAI is None:
            return None
        return OpenAI(api_key=settings.openai_api_key)

    def _get_output_text(self, response: Any) -> str:
        text = getattr(response, "output_text", "")
        if text:
            return text.strip()
        # Fallback for SDK shape changes.
        try:
            output = getattr(response, "output", [])
            parts: list[str] = []
            for item in output:
                for content in getattr(item, "content", []):
                    candidate = getattr(content, "text", None)
                    if candidate:
                        parts.append(candidate)
            return "\n".join(parts).strip()
        except Exception:
            return ""

    def generate_text(self, prompt: str, *, model: str | None = None) -> str:
        client = self._client()
        if client is None:
            return ""
        response = client.responses.create(
            model=model or settings.openai_model,
            input=prompt,
        )
        return self._get_output_text(response)

    def analyze_image(self, image_path: str, prompt: str, *, model: str | None = None) -> str:
        client = self._client()
        if client is None:
            return ""
        path = Path(image_path)
        if not path.exists():
            return ""

        suffix = path.suffix.lower()
        media_type = "image/jpeg"
        if suffix == ".png":
            media_type = "image/png"
        elif suffix == ".webp":
            media_type = "image/webp"

        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
        data_url = f"data:{media_type};base64,{b64}"
        response = client.responses.create(
            model=model or settings.openai_vision_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": data_url},
                    ],
                }
            ],
        )
        return self._get_output_text(response)
