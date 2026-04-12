import base64
import os
import subprocess
import tempfile
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

    def _client(self, api_key: str | None = None) -> Any:
        effective_key = api_key or settings.openai_api_key
        if not effective_key or OpenAI is None:
            return None
        return OpenAI(api_key=effective_key)

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

    def _extract_error_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if "api.videos.write" in message:
            return "The video API key does not have video-generation permission. It needs the scope `api.videos.write`."
        if "string too long" in message and "prompt" in message:
            return "The generated media prompt was too long for the provider."
        if message:
            return message
        return exc.__class__.__name__

    def _prepare_image_for_edit(self, image_path: str) -> str:
        path = Path(image_path)
        if not path.exists():
            raise RuntimeError("The uploaded product image could not be found.")
        if path.suffix.lower() == ".png" and path.stat().st_size < 4 * 1024 * 1024:
            return str(path)

        temp_dir = Path(tempfile.mkdtemp(prefix="hackersquad-image-"))
        converted_path = temp_dir / f"{path.stem}.png"
        resize_targets = [1536, 1280, 1024, 768, 512]
        last_error = ""

        for target in resize_targets:
            command = [
                "sips",
                "-s",
                "format",
                "png",
                "-Z",
                str(target),
                str(path),
                "--out",
                str(converted_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                last_error = result.stderr.strip() or result.stdout.strip() or "sips conversion failed"
                continue
            if converted_path.exists() and converted_path.stat().st_size < 4 * 1024 * 1024:
                return str(converted_path)

        if converted_path.exists() and converted_path.stat().st_size < 4 * 1024 * 1024:
            return str(converted_path)
        if last_error:
            raise RuntimeError(f"Image conversion failed: {last_error}")
        raise RuntimeError("The uploaded image could not be converted to a PNG under 4 MB.")

    def generate_text(self, prompt: str, *, model: str | None = None) -> str:
        client = self._client(settings.openai_api_key)
        if client is None:
            return ""
        response = client.responses.create(
            model=model or settings.openai_model,
            input=prompt,
        )
        return self._get_output_text(response)

    def analyze_image(self, image_path: str, prompt: str, *, model: str | None = None) -> str:
        client = self._client(settings.openai_api_key)
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

    def generate_image(self, prompt: str, output_path: str, *, reference_image_path: str | None = None) -> str:
        client = self._client(settings.openai_image_api_key or settings.openai_api_key)
        if client is None:
            raise RuntimeError("No image-generation API key is configured.")
        try:
            if reference_image_path:
                try:
                    prepared_path = Path(self._prepare_image_for_edit(reference_image_path))
                    with prepared_path.open("rb") as image_file:
                        response = client.images.edit(
                            model=settings.openai_image_model,
                            image=image_file,
                            prompt=prompt,
                            response_format="b64_json",
                            size="1024x1024",
                        )
                except Exception:
                    # Fall back to text-only image generation when the uploaded image
                    # cannot satisfy the provider's edit/inpaint requirements.
                    response = client.images.generate(
                        model=settings.openai_image_model,
                        prompt=prompt,
                        response_format="b64_json",
                        size="1024x1024",
                    )
            else:
                response = client.images.generate(
                    model=settings.openai_image_model,
                    prompt=prompt,
                    response_format="b64_json",
                    size="1024x1024",
                )
        except Exception as exc:
            raise RuntimeError(self._extract_error_message(exc)) from exc

        image_b64 = ""
        data = getattr(response, "data", None) or []
        if data:
            image_b64 = getattr(data[0], "b64_json", "") or ""
        if not image_b64:
            raise RuntimeError("The image API returned no image data.")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(image_b64))
        return str(path)

    def generate_video(
        self,
        prompt: str,
        output_path: str,
        *,
        reference_image_path: str | None = None,
        seconds: int = 4,
        size: str = "720x1280",
    ) -> str:
        client = self._client(settings.openai_video_api_key or settings.openai_api_key)
        if client is None:
            raise RuntimeError("No video-generation API key is configured.")
        input_reference: Any = None
        if reference_image_path:
            path = Path(reference_image_path)
            if path.exists():
                input_reference = path
        try:
            video = client.videos.create_and_poll(
                model=settings.openai_video_model,
                prompt=prompt,
                **({"input_reference": input_reference} if input_reference is not None else {}),
                seconds=seconds,
                size=size,
                poll_interval_ms=3000,
            )
        except Exception:
            try:
                # Fall back to prompt-only video generation when the reference image
                # triggers strict inpaint/input constraints.
                video = client.videos.create_and_poll(
                    model=settings.openai_video_model,
                    prompt=prompt,
                    seconds=seconds,
                    size=size,
                    poll_interval_ms=3000,
                )
            except Exception as exc:
                raise RuntimeError(self._extract_error_message(exc)) from exc
        video_id = getattr(video, "id", "")
        if not video_id:
            raise RuntimeError("The video API returned no job id.")
        try:
            content = client.videos.download_content(video_id)
            video_bytes = content.read() if hasattr(content, "read") else bytes(content)
        except Exception as exc:
            raise RuntimeError(self._extract_error_message(exc)) from exc
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(video_bytes)
        return str(path)
