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


MAX_REFERENCE_IMAGES = 8
REFERENCE_LIST_TYPE = "OPENAI_COMPATIBLE_IMAGE_REFERENCES"
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
        "Image APIs and proxy endpoints can take several minutes, especially for reference-image edits. "
        "Increase timeout_seconds, reduce n/reference image count, or check whether the provider requires async polling."
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


def _post_multipart(url, headers, data, files, timeout_seconds, operation):
    try:
        return requests.post(
            url,
            headers=headers,
            data=data,
            files=files,
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


def _tensor_to_png_bytes(image_tensor):
    tensor = image_tensor.detach().cpu()
    if tensor.ndim == 4:
        tensor = tensor[0]
    if tensor.ndim != 3:
        raise ValueError(f"Expected IMAGE tensor with 3 or 4 dimensions, got shape {tuple(tensor.shape)}")

    array = (tensor.clamp(0, 1).numpy() * 255.0).astype(np.uint8)
    image = Image.fromarray(array).convert("RGBA")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def _reference_prompt_lines(reference_prompts, reference_image_count):
    lines = []
    for index in range(reference_image_count):
        reference_prompt = (reference_prompts[index] or "").strip()
        if reference_prompt:
            lines.append(f"Reference image {index + 1}: {reference_prompt}")
    return lines


def _references_from_reference_list(references, reference_image_count):
    if not references:
        return []
    if not isinstance(references, list):
        raise ValueError("references must be an OPENAI_COMPATIBLE_IMAGE_REFERENCES list.")

    if reference_image_count > 0 and len(references) < reference_image_count:
        raise ValueError(
            f"reference_image_count is {reference_image_count}, but the connected reference list only has {len(references)} image(s)."
        )

    selected = references[:reference_image_count] if reference_image_count > 0 else references
    normalized = []
    for index, reference in enumerate(selected, start=1):
        if not isinstance(reference, dict) or reference.get("image") is None:
            raise ValueError(f"Reference list item {index} is invalid.")
        normalized.append(
            {
                "image": reference["image"],
                "prompt": reference.get("prompt", "") or "",
            }
        )
    return normalized


def _references_from_slots(reference_images, reference_prompts, reference_image_count):
    if reference_image_count > MAX_REFERENCE_IMAGES:
        raise ValueError(
            f"reference_image_count > {MAX_REFERENCE_IMAGES} requires the OpenAI Compatible Reference Image list node."
        )

    if reference_image_count > 0:
        selected_images = reference_images[:reference_image_count]
        missing = [str(index + 1) for index, image in enumerate(selected_images) if image is None]
        if missing:
            raise ValueError(
                "Missing connected reference image input(s): "
                + ", ".join(f"image_{index}" for index in missing)
            )
        return [
            {
                "image": image,
                "prompt": reference_prompts[index] or "",
            }
            for index, image in enumerate(selected_images)
        ]

    references = []
    for image, reference_prompt in zip(reference_images, reference_prompts):
        if image is not None:
            references.append(
                {
                    "image": image,
                    "prompt": reference_prompt or "",
                }
            )
    return references


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


class OpenAICompatibleImageEditWithReferences:
    @classmethod
    def INPUT_TYPES(cls):
        reference_prompts = {
            f"reference_prompt_{index}": (
                "STRING",
                {
                    "multiline": True,
                    "default": "",
                },
            )
            for index in range(1, MAX_REFERENCE_IMAGES + 1)
        }
        reference_images = {
            f"image_{index}": ("IMAGE",)
            for index in range(1, MAX_REFERENCE_IMAGES + 1)
        }

        return {
            "required": {
                "prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "Use the reference images to create a polished, realistic final image.",
                    },
                ),
                "reference_image_count": (
                    "INT",
                    {"default": 0, "min": 0, "max": 64, "step": 1},
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
                "append_reference_prompts": (
                    "BOOLEAN",
                    {"default": True},
                ),
                **reference_prompts,
            },
            "optional": {
                "references": (REFERENCE_LIST_TYPE,),
                **reference_images,
                "api_key": (
                    "STRING",
                    {"default": "", "multiline": False},
                ),
                "endpoint_path": (
                    "STRING",
                    {"default": "/images/edits"},
                ),
                "image_field": (
                    "STRING",
                    {"default": "image[]"},
                ),
                "reference_prompt_field": (
                    "STRING",
                    {"default": ""},
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
    FUNCTION = "edit"
    CATEGORY = "OpenAI Compatible/Image"

    def edit(
        self,
        prompt,
        reference_image_count,
        api_base,
        model,
        size,
        quality,
        n,
        timeout_seconds,
        append_reference_prompts,
        reference_prompt_1="",
        reference_prompt_2="",
        reference_prompt_3="",
        reference_prompt_4="",
        reference_prompt_5="",
        reference_prompt_6="",
        reference_prompt_7="",
        reference_prompt_8="",
        references=None,
        image_1=None,
        image_2=None,
        image_3=None,
        image_4=None,
        image_5=None,
        image_6=None,
        image_7=None,
        image_8=None,
        api_key="",
        endpoint_path="/images/edits",
        image_field="image[]",
        reference_prompt_field="",
        extra_headers_json="{}",
        extra_body_json="{}",
        save_raw_response=False,
    ):
        api_key = _api_key_from_input(api_key)
        url = _endpoint_url(api_base, endpoint_path)

        reference_images = [image_1, image_2, image_3, image_4, image_5, image_6, image_7, image_8]
        slot_reference_prompts = [
            reference_prompt_1,
            reference_prompt_2,
            reference_prompt_3,
            reference_prompt_4,
            reference_prompt_5,
            reference_prompt_6,
            reference_prompt_7,
            reference_prompt_8,
        ]

        selected_references = _references_from_reference_list(references, reference_image_count)
        if not selected_references:
            selected_references = _references_from_slots(
                reference_images,
                slot_reference_prompts,
                reference_image_count,
            )
        if not selected_references:
            raise ValueError("Connect at least one reference image or an OPENAI_COMPATIBLE_IMAGE_REFERENCES list.")

        selected_reference_prompts = [reference["prompt"] for reference in selected_references]
        prompt_lines = [prompt.strip()]
        reference_lines = _reference_prompt_lines(selected_reference_prompts, len(selected_references))
        if append_reference_prompts and reference_lines:
            prompt_lines.extend(["", "Reference image instructions:", *reference_lines])
        final_prompt = "\n".join(line for line in prompt_lines if line != "")

        data = [
            ("model", model),
            ("prompt", final_prompt),
            ("n", str(n)),
        ]
        if size != "auto":
            data.append(("size", size))
        if quality != "auto":
            data.append(("quality", quality))

        for key, value in _parse_json_object(extra_body_json, "extra_body_json").items():
            data.append((key, str(value)))

        reference_prompt_field = reference_prompt_field.strip()
        if reference_prompt_field:
            for reference_prompt in selected_reference_prompts:
                data.append((reference_prompt_field, reference_prompt or ""))

        files = []
        image_field = image_field.strip() or "image[]"
        for index, reference in enumerate(selected_references, start=1):
            files.append((image_field, (f"reference_{index}.png", _tensor_to_png_bytes(reference["image"]), "image/png")))

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Connection": "close",
        }
        headers.update(_parse_json_object(extra_headers_json, "extra_headers_json"))

        response = _post_multipart(url, headers, data, files, timeout_seconds, "Image edit")
        if response.status_code >= 400:
            raise RuntimeError(f"Image edit API request failed ({response.status_code}): {response.text}")

        payload = response.json()
        _maybe_save_debug_response(save_raw_response, "Image edit", payload)
        return (_response_to_tensor_batch(payload, timeout_seconds), _response_json_text(payload))


class OpenAICompatibleReferenceImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "reference_prompt": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "Describe how this reference image should be used.",
                    },
                ),
                "enabled": (
                    "BOOLEAN",
                    {"default": True},
                ),
            },
            "optional": {
                "references": (REFERENCE_LIST_TYPE,),
            },
        }

    RETURN_TYPES = (REFERENCE_LIST_TYPE,)
    RETURN_NAMES = ("references",)
    FUNCTION = "add"
    CATEGORY = "OpenAI Compatible/Image"

    def add(self, image, reference_prompt, enabled, references=None):
        result = list(references or [])
        if enabled:
            result.append(
                {
                    "image": image,
                    "prompt": reference_prompt,
                }
            )
        return (result,)


NODE_CLASS_MAPPINGS = {
    "OpenAICompatibleImageGenerate": OpenAICompatibleImageGenerate,
    "OpenAICompatibleImageEditWithReferences": OpenAICompatibleImageEditWithReferences,
    "OpenAICompatibleReferenceImage": OpenAICompatibleReferenceImage,
    "GPTImage2CustomEndpoint": OpenAICompatibleImageGenerate,
    "GPTImage2EditWithReferencesCustomEndpoint": OpenAICompatibleImageEditWithReferences,
    "GPTImage2ReferenceImage": OpenAICompatibleReferenceImage,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OpenAICompatibleImageGenerate": "OpenAI Compatible Image Generate",
    "OpenAICompatibleImageEditWithReferences": "OpenAI Compatible Image Edit With References",
    "OpenAICompatibleReferenceImage": "OpenAI Compatible Reference Image",
    "GPTImage2CustomEndpoint": "GPT Image 2 (Custom Endpoint, Legacy)",
    "GPTImage2EditWithReferencesCustomEndpoint": "GPT Image 2 Edit With References (Legacy)",
    "GPTImage2ReferenceImage": "GPT Image 2 Reference Image (Legacy)",
}
