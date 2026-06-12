import base64
import io
import json
import os
import tempfile
import time
from urllib.parse import urlparse

import numpy as np
import requests
import torch
from PIL import Image


DEFAULT_TIMEOUT_SECONDS = 600
CONNECT_TIMEOUT_SECONDS = 30
IMAGE_B64_KEYS = ("b64_json", "image_b64", "b64", "base64", "image_base64")
IMAGE_URL_KEYS = ("url", "image_url", "output_url", "result_url", "download_url")
NESTED_IMAGE_KEYS = ("image", "output", "result")


def _parse_json_object(value, field_name):
    value = (value or "").strip()
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    return parsed


def _api_key_from_input(api_key):
    api_key = api_key.strip() or os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Missing API key. Set OPENAI_API_KEY or fill the api_key input.")
    return api_key


def _endpoint_url(api_base, endpoint_path):
    api_base = api_base.rstrip("/")
    endpoint_path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
    return f"{api_base}{endpoint_path}"


def _request_timeout(timeout_seconds):
    read_timeout = max(int(timeout_seconds), CONNECT_TIMEOUT_SECONDS)
    return (CONNECT_TIMEOUT_SECONDS, read_timeout)


def _format_timeout_message(operation, timeout_seconds):
    return (
        f"{operation} timed out after {timeout_seconds}s. "
        "Image APIs and proxy endpoints can take several minutes. "
        "Increase timeout_seconds, reduce n, or check whether the provider requires async polling."
    )


def _post_json(url, headers, body, timeout_seconds, operation):
    try:
        return requests.post(
            url,
            headers=headers,
            json=body,
            timeout=_request_timeout(timeout_seconds),
        )
    except requests.exceptions.Timeout as exc:
        raise TimeoutError(_format_timeout_message(operation, timeout_seconds)) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"{operation} request failed before receiving a response: {exc}") from exc


def _get_image_url(image_url, timeout_seconds):
    try:
        response = requests.get(
            image_url,
            headers={"Connection": "close"},
            timeout=_request_timeout(timeout_seconds),
        )
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout as exc:
        raise TimeoutError(_format_timeout_message("Image URL download", timeout_seconds)) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Image URL download failed: {exc}") from exc


def _looks_like_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_data_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return [payload]

    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]

    for key in ("images", "outputs", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]

    return [payload]


def _get_first_value(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def _extract_image_value(item):
    if isinstance(item, str):
        if _looks_like_url(item):
            return "url", item
        return "b64", item

    if not isinstance(item, dict):
        return None, None

    b64_image = _get_first_value(item, IMAGE_B64_KEYS)
    if b64_image:
        return "b64", b64_image

    image_url = _get_first_value(item, IMAGE_URL_KEYS)
    if image_url:
        return "url", image_url

    for key in NESTED_IMAGE_KEYS:
        value = item.get(key)
        if isinstance(value, dict):
            image_type, image_value = _extract_image_value(value)
            if image_value:
                return image_type, image_value
        if isinstance(value, str):
            if _looks_like_url(value):
                return "url", value
            return "b64", value

    return None, None


def _b64_to_tensor(b64_image):
    if "," in b64_image and b64_image.strip().startswith("data:"):
        b64_image = b64_image.split(",", 1)[1]
    image_bytes = base64.b64decode(b64_image)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    array = np.asarray(image).astype(np.float32) / 255.0
    return torch.from_numpy(array)


def _response_to_tensor_batch(payload, timeout_seconds):
    items = _normalize_data_items(payload)
    if not items:
        raise RuntimeError(f"Image API response has no image items: {payload}")

    images = []
    for item in items:
        image_type, image_value = _extract_image_value(item)
        if image_type == "b64":
            images.append(_b64_to_tensor(image_value))
            continue

        if image_type == "url":
            response = _get_image_url(image_value, timeout_seconds)
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            array = np.asarray(image).astype(np.float32) / 255.0
            images.append(torch.from_numpy(array))
            continue

        raise RuntimeError(
            "Image item has no recognized image field. "
            f"Supported base64 keys: {IMAGE_B64_KEYS}; supported URL keys: {IMAGE_URL_KEYS}. "
            f"Full item: {item}"
        )

    return torch.stack(images, dim=0)


def _response_json_text(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _maybe_save_debug_response(enabled, operation, payload):
    if not enabled:
        return
    safe_operation = operation.lower().replace(" ", "_")
    filename = f"comfyui_openai_compatible_{safe_operation}_{int(time.time())}.json"
    path = os.path.join(tempfile.gettempdir(), filename)
    with open(path, "w", encoding="utf-8") as file:
        file.write(_response_json_text(payload))
    print(f"[OpenAI Compatible Image] Saved raw {operation} response to: {path}")


class OpenAICompatibleImageGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "A clean product photo of a translucent glass teapot on a walnut table, soft daylight, realistic.",
                    },
                ),
                "api_base": (
                    "STRING",
                    {"default": "https://api.openai.com/v1"},
                ),
                "model": (
                    "STRING",
                    {"default": "gpt-image-2"},
                ),
                "size": (
                    "STRING",
                    {"default": "1024x1024"},
                ),
                "quality": (
                    ["auto", "low", "medium", "high"],
                    {"default": "auto"},
                ),
                "n": (
                    "INT",
                    {"default": 1, "min": 1, "max": 10, "step": 1},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": DEFAULT_TIMEOUT_SECONDS, "min": 30, "max": 3600, "step": 30},
                ),
            },
            "optional": {
                "api_key": (
                    "STRING",
                    {"default": "", "multiline": False},
                ),
                "endpoint_path": (
                    "STRING",
                    {"default": "/images/generations"},
                ),
                "extra_headers_json": (
                    "STRING",
                    {"multiline": True, "default": "{}"},
                ),
                "extra_body_json": (
                    "STRING",
                    {"multiline": True, "default": "{}"},
                ),
                "save_raw_response": (
                    "BOOLEAN",
                    {"default": False},
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "response_json")
    FUNCTION = "generate"
    CATEGORY = "OpenAI Compatible/Image"

    def generate(
        self,
        prompt,
        api_base,
        model,
        size,
        quality,
        n,
        timeout_seconds,
        api_key="",
        endpoint_path="/images/generations",
        extra_headers_json="{}",
        extra_body_json="{}",
        save_raw_response=False,
    ):
        api_key = _api_key_from_input(api_key)
        url = _endpoint_url(api_base, endpoint_path)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Connection": "close",
        }
        headers.update(_parse_json_object(extra_headers_json, "extra_headers_json"))

        body = {
            "model": model,
            "prompt": prompt,
            "n": n,
        }
        if size != "auto":
            body["size"] = size
        if quality != "auto":
            body["quality"] = quality
        body.update(_parse_json_object(extra_body_json, "extra_body_json"))

        response = _post_json(url, headers, body, timeout_seconds, "Image generation")
        if response.status_code >= 400:
            raise RuntimeError(f"Image API request failed ({response.status_code}): {response.text}")

        payload = response.json()
        _maybe_save_debug_response(save_raw_response, "Image generation", payload)
        return (_response_to_tensor_batch(payload, timeout_seconds), _response_json_text(payload))


NODE_CLASS_MAPPINGS = {
    "OpenAICompatibleImageGenerate": OpenAICompatibleImageGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenAICompatibleImageGenerate": "OpenAI Compatible Image Generate",
}
