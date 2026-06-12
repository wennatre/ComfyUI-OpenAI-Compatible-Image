# ComfyUI OpenAI Compatible Image

[中文说明](README.zh-CN.md)

Lightweight ComfyUI custom nodes for OpenAI-compatible image generation and image editing endpoints.

This project is an adapter for direct OpenAI-compatible APIs, self-hosted gateways, and third-party providers with small field differences. It keeps endpoint paths, multipart image field names, extra headers, and extra body fields editable from the node UI.

## Features

- Text-to-image through an OpenAI-compatible JSON endpoint.
- Image edit / image-to-image through an OpenAI-compatible multipart endpoint.
- Configurable `api_base`, `endpoint_path`, model string, headers, and body fields.
- Reference images via fixed slots or a chainable reference list.
- Per-reference prompts appended into the main prompt.
- Optional provider-specific per-reference prompt multipart field.
- Reads `OPENAI_API_KEY` by default, with optional node-level key override.
- Supports image responses as `data[].b64_json` or `data[].url`.

## Nodes

| Node | Purpose |
| --- | --- |
| `OpenAI Compatible Image Generate` | Sends a text-to-image request to `/images/generations` by default. |
| `OpenAI Compatible Image Edit With References` | Sends reference images to `/images/edits` by default. |
| `OpenAI Compatible Reference Image` | Adds one image and one reference prompt to a chainable reference list. |

Legacy node IDs from the initial GPT Image 2 prototype are still registered so older workflows can load.

## Installation

Clone or copy this repository into your ComfyUI custom nodes directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/wenxl/ComfyUI-OpenAI-Compatible-Image.git
```

Install dependencies in the same Python environment used by ComfyUI:

```bash
pip install -r ComfyUI-OpenAI-Compatible-Image/requirements.txt
```

Set your API key before starting ComfyUI:

```bash
export OPENAI_API_KEY="your_api_key"
```

On Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="your_api_key"
```

Restart ComfyUI after installation.

## Text To Image

Default request:

```text
POST {api_base}/images/generations
Content-Type: application/json
Authorization: Bearer {api_key}
```

Default body:

```json
{
  "model": "gpt-image-2",
  "prompt": "...",
  "n": 1,
  "size": "1024x1024"
}
```

Use `extra_headers_json` for provider headers:

```json
{"x-provider-key": "value"}
```

Use `extra_body_json` for provider body fields:

```json
{"user": "comfyui"}
```

## Reference Images

The edit node defaults to:

```text
POST {api_base}/images/edits
Content-Type: multipart/form-data
Authorization: Bearer {api_key}
```

Reference image input modes:

- Fixed slots: connect `image_1 ... image_8`.
- List mode: chain `OpenAI Compatible Reference Image` nodes and connect the final `references` output.

`reference_image_count` controls how many references are sent. Set it to `0` to send all connected fixed-slot images or all list items.

Each reference can have a prompt. By default, reference prompts are appended to the main prompt:

```text
Reference image 1: use this as the subject identity.
Reference image 2: use this as the lighting and style.
```

Official OpenAI image edit requests do not define a separate per-image prompt field. If your custom endpoint supports one, set `reference_prompt_field`, for example:

```text
reference_prompt[]
```

The default multipart image field is:

```text
image[]
```

If your endpoint expects repeated `image` fields instead, set:

```text
image
```

## Workflows

Example workflows are included:

- `workflows/openai_compatible_text_to_image_workflow.json`
- `workflows/openai_compatible_reference_images_workflow.json`

Import them from ComfyUI after installing the node.

## Repository Layout

This repository follows a small, repeatable layout for future ComfyUI node projects:

```text
ComfyUI-OpenAI-Compatible-Image/
├── __init__.py
├── README.md
├── README.zh-CN.md
├── requirements.txt
├── pyproject.toml
├── LICENSE
├── workflows/
│   ├── openai_compatible_text_to_image_workflow.json
│   └── openai_compatible_reference_images_workflow.json
└── docs/
    └── repo-layout.zh-CN.md
```

For future work, keep each installable ComfyUI custom node as its own repository. Keep cross-node, ready-to-use workflows in a separate workflow collection repository.

## Compatibility Notes

The model field is intentionally free text. `gpt-image-2` is the default because many custom endpoints use that string, but you can set any model your endpoint accepts.

The node expects an OpenAI-style response:

```json
{
  "data": [
    {"b64_json": "..."}
  ]
}
```

It also accepts URL responses:

```json
{
  "data": [
    {"url": "https://..."}
  ]
}
```

## Security

Prefer `OPENAI_API_KEY` over pasting keys into workflows. Workflows can be shared accidentally, and node widget values may be saved in workflow JSON.

## Development

Basic local checks:

```bash
python -m py_compile __init__.py
python -m json.tool workflows/openai_compatible_text_to_image_workflow.json
python -m json.tool workflows/openai_compatible_reference_images_workflow.json
```

## License

MIT
