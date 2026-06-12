# ComfyUI OpenAI Compatible Image

[中文说明](README.zh-CN.md)

Lightweight ComfyUI custom node for OpenAI-compatible text-to-image endpoints.

This project is an adapter for direct OpenAI-compatible APIs, self-hosted gateways, and third-party providers with small field differences. It keeps endpoint paths, extra headers, and extra body fields editable from the node UI.

## Features

- Text-to-image through an OpenAI-compatible JSON endpoint.
- Configurable `api_base`, `endpoint_path`, model string, headers, and body fields.
- Reads `OPENAI_API_KEY` by default, with optional node-level key override.
- Supports common image response fields such as `data[].b64_json`, `data[].url`, `image_url`, `output_url`, `result_url`, `images`, `outputs`, and `results`.
- Returns the raw API response JSON as a second output for debugging.

## Nodes

| Node | Purpose |
| --- | --- |
| `OpenAI Compatible Image Generate` | Sends a text-to-image request to `/images/generations` by default. |

## Installation

Clone or copy this repository into your ComfyUI custom nodes directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/wennatre/ComfyUI-OpenAI-Compatible-Image.git
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

`timeout_seconds` defaults to `600`. Proxy providers can be slow; if a request times out, increase this value before retrying.

## Workflows

Example workflows are included:

- `workflows/openai_compatible_text_to_image_workflow.json`

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
│   └── openai_compatible_text_to_image_workflow.json
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

Many proxy APIs use slightly different field names. The node also checks common URL keys such as `image_url`, `output_url`, `result_url`, and `download_url`, plus top-level `images`, `outputs`, and `results` arrays.

Enable `save_raw_response` to write the raw response JSON to your system temp directory. The path is printed in the ComfyUI console.

## Security

Prefer `OPENAI_API_KEY` over pasting keys into workflows. Workflows can be shared accidentally, and node widget values may be saved in workflow JSON.

## Troubleshooting

### A generation times out

Some OpenAI-compatible proxies keep HTTP connections open incorrectly. The nodes send `Connection: close` by default to avoid reusing a stale connection.

If it still times out:

- Increase `timeout_seconds` to `900` or `1200`.
- Reduce `n` to `1`.
- Check whether your provider uses an async job API instead of returning `data[].b64_json` or `data[].url` directly.
- If your provider has a custom polling endpoint, this node needs provider-specific async polling support.
- Connect or inspect the second output, `response_json`, to see the exact response shape.
- Enable `save_raw_response` and check the printed JSON path in the ComfyUI console.

## Development

Basic local checks:

```bash
python -m py_compile __init__.py
python -m json.tool workflows/openai_compatible_text_to_image_workflow.json
```

## License

MIT
