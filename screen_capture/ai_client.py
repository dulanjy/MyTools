"""Simple AI client wrapper for chat & image analysis integrated with screen_capture.

Dependencies: assumes 'zai' (ZhipuAiClient) already installed in environment.
Falls back gracefully if missing or API key absent.
"""
from __future__ import annotations
import os, base64, io, threading
from typing import List, Dict, Optional

from .logging_utils import get_logger  # type: ignore
logger = get_logger()

try:
    from zai import ZhipuAiClient  # type: ignore
except Exception:  # pragma: no cover
    ZhipuAiClient = None  # type: ignore

DEFAULT_MODEL_TEXT = "glm-4"
DEFAULT_MODEL_VISION = "glm-4.5v"
SERVICE_NAME = "zhipu"
KEY_ENV = "ZHIPU_API_KEY"

try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover
    keyring = None  # type: ignore


def _load_api_key() -> Optional[str]:
    v = os.getenv(KEY_ENV)
    if v:
        return v.strip().strip('\"').strip("'")
    if keyring:
        try:
            stored = keyring.get_password(SERVICE_NAME, 'api_key')
            if stored:
                return stored.strip()
        except Exception:
            pass
    return None


class AIClient:
    def __init__(self, model_text: str = DEFAULT_MODEL_TEXT, model_vision: str = DEFAULT_MODEL_VISION):
        self.model_text = model_text
        self.model_vision = model_vision
        self._api_key = _load_api_key()
        self._client = None
        if self._api_key and ZhipuAiClient:
            try:
                self._client = ZhipuAiClient(api_key=self._api_key)
            except Exception:
                self._client = None

    @property
    def ready(self) -> bool:
        return self._client is not None

    def chat(self, messages: List[Dict], *, timeout: Optional[float] = 30.0) -> Dict:
        if not self.ready:
            try:
                logger.warning("AI client not ready (missing key or sdk).")
            except Exception:
                pass
            return {"error": "AI client not ready (missing key or sdk)."}
        try:
            try:
                resp = self._client.chat.completions.create(
                    model=self.model_text,
                    messages=messages,
                    stream=False,
                    request_timeout=timeout
                )
            except TypeError:
                resp = self._client.chat.completions.create(
                    model=self.model_text,
                    messages=messages,
                    stream=False
                )
            return {"content": resp.choices[0].message.content}
        except Exception as e:
            return {"error": str(e)}

    def analyze_image(self, pil_image, question: str, *, image_format: str = 'PNG', quality: int = 85, max_side: int = 1600, timeout: Optional[float] = 30.0) -> Dict:
        if not self.ready:
            try:
                logger.warning("AI client not ready (missing key or sdk).")
            except Exception:
                pass
            return {"error": "AI client not ready (missing key or sdk)."}
        try:
            # Resize if too large to reduce payload and latency
            orig_w, orig_h = pil_image.size
            try:
                w, h = pil_image.size
                if max(w, h) > max_side:
                    ratio = max_side / float(max(w, h))
                    new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
                    pil_image = pil_image.resize(new_size)
                else:
                    ratio = 1.0
            except Exception:
                ratio = 1.0
                w, h = pil_image.size
            buf = io.BytesIO()
            fmt = image_format.upper().strip()
            mime = 'image/png'
            save_kwargs = {}
            if fmt == 'JPEG' or fmt == 'JPG':
                fmt = 'JPEG'
                mime = 'image/jpeg'
                save_kwargs = {'quality': quality, 'optimize': True}
                if pil_image.mode in ('RGBA', 'LA'):
                    try:
                        from PIL import Image
                        bg = Image.new('RGB', pil_image.size, (255, 255, 255))
                        bg.paste(pil_image, mask=pil_image.split()[-1])
                        pil_image = bg
                    except Exception:
                        pil_image = pil_image.convert('RGB')
            else:
                fmt = 'PNG'
                mime = 'image/png'
            pil_image.save(buf, format=fmt, **save_kwargs)
            data_bytes = buf.getvalue()
            b64 = base64.b64encode(data_bytes).decode()
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": question}
                ]
            }]
            meta = {
                "orig": {"w": orig_w, "h": orig_h},
                "resized": {"w": pil_image.size[0], "h": pil_image.size[1]},
                "ratio": ratio,
                "format": fmt,
                "mime": mime,
                "bytes": len(data_bytes),
            }
            try:
                logger.info(f"Vision request: {meta}")
            except Exception:
                pass
            # Try to pass a timeout if SDK supports it
            try:
                resp = self._client.chat.completions.create(
                    model=self.model_vision,
                    messages=messages,
                    stream=False,
                    request_timeout=timeout
                )
            except TypeError:
                resp = self._client.chat.completions.create(
                    model=self.model_vision,
                    messages=messages,
                    stream=False
                )
            return {"content": resp.choices[0].message.content, "meta": meta}
        except Exception as e:
            try:
                logger.exception(f"Vision analyze_image failed: {e}")
            except Exception:
                pass
            return {"error": str(e)}

    # --- Key management helpers ---
    def set_api_key(self, key: str, persist: bool = True) -> Dict:
        """Update API key in memory and optionally persist to keyring.
        Returns a dict with {ok: bool, persisted: bool, error?: str}.
        """
        key = (key or '').strip()
        if not key:
            return {"ok": False, "persisted": False, "error": "空的 API Key"}
        persisted = False
        if persist and keyring:
            try:
                keyring.set_password(SERVICE_NAME, 'api_key', key)
                persisted = True
            except Exception as e:
                persisted = False
        # Update env for current process as fallback/session-level
        try:
            os.environ[KEY_ENV] = key
        except Exception:
            pass
        # Re-init client
        self._api_key = key
        self._client = None
        if ZhipuAiClient:
            try:
                self._client = ZhipuAiClient(api_key=self._api_key)
            except Exception as e:
                return {"ok": False, "persisted": persisted, "error": str(e)}
        return {"ok": self._client is not None, "persisted": persisted}

    def clear_api_key(self) -> Dict:
        """Clear key from keyring (if available) and memory."""
        removed = False
        if keyring:
            try:
                keyring.delete_password(SERVICE_NAME, 'api_key')
                removed = True
            except Exception:
                pass
        try:
            if KEY_ENV in os.environ:
                del os.environ[KEY_ENV]
        except Exception:
            pass
        self._api_key = None
        self._client = None
        return {"ok": True, "removed": removed}


# Simple async helper
class AsyncCall:
    def __init__(self, fn, callback):
        self.fn = fn; self.callback = callback
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
    def _run(self):
        res = self.fn()
        try:
            self.callback(res)
        except Exception:
            pass

__all__ = ["AIClient", "AsyncCall"]
