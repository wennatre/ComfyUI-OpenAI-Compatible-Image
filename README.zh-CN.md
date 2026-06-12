# ComfyUI OpenAI Compatible Image

[English README](README.md)

这是一个轻量级 ComfyUI 自定义节点项目，用于调用 OpenAI-compatible 图片生成和图片编辑接口。

它的定位不是“又一个 GPT Image 节点”，而是一个通用适配器：适合直连 OpenAI-compatible API、自建网关、第三方聚合 API，以及字段略有差异的图片服务。节点 UI 中可以自定义 endpoint path、multipart 图片字段名、额外 header、额外 body 字段。

## 功能

- 通过 OpenAI-compatible JSON 接口做文生图。
- 通过 OpenAI-compatible multipart 接口做图片编辑 / 图生图。
- 可配置 `api_base`、`endpoint_path`、模型名、headers、body 字段。
- 参考图支持固定输入槽，也支持链式参考图列表。
- 每张参考图可以单独写提示词，并默认合并进主 prompt。
- 如果你的自定义端点支持每图提示词字段，可以配置额外 multipart 字段。
- 默认读取 `OPENAI_API_KEY`，也支持在节点中临时填写 key。
- 支持读取 `data[].b64_json` 或 `data[].url` 图片响应。

## 节点

| 节点 | 用途 |
| --- | --- |
| `OpenAI Compatible Image Generate` | 默认调用 `/images/generations` 做文生图。 |
| `OpenAI Compatible Image Edit With References` | 默认调用 `/images/edits`，上传参考图做编辑 / 图生图。 |
| `OpenAI Compatible Reference Image` | 把一张图片和一段参考图提示词加入可链式连接的参考图列表。 |

初版 GPT Image 2 原型中的旧节点 ID 仍然保留，旧 workflow 可以继续加载。

## 安装

把仓库 clone 到 ComfyUI 的 `custom_nodes` 目录：

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/wennatre/ComfyUI-OpenAI-Compatible-Image.git
```

在 ComfyUI 使用的 Python 环境里安装依赖：

```bash
pip install -r ComfyUI-OpenAI-Compatible-Image/requirements.txt
```

启动 ComfyUI 前设置 API key：

```bash
export OPENAI_API_KEY="your_api_key"
```

Windows PowerShell：

```powershell
$env:OPENAI_API_KEY="your_api_key"
```

安装后重启 ComfyUI。

## 文生图

默认请求：

```text
POST {api_base}/images/generations
Content-Type: application/json
Authorization: Bearer {api_key}
```

默认 body：

```json
{
  "model": "gpt-image-2",
  "prompt": "...",
  "n": 1,
  "size": "1024x1024"
}
```

用 `extra_headers_json` 添加服务商 header：

```json
{"x-provider-key": "value"}
```

用 `extra_body_json` 添加服务商 body 字段：

```json
{"user": "comfyui"}
```

`timeout_seconds` 默认是 `600`。带参考图的编辑请求在代理服务商上可能很慢；如果请求超时，先把这个值调大再重试。

## 参考图

编辑节点默认请求：

```text
POST {api_base}/images/edits
Content-Type: multipart/form-data
Authorization: Bearer {api_key}
```

参考图有两种输入方式：

- 固定输入槽：直接连接 `image_1 ... image_8`。
- 列表模式：串联多个 `OpenAI Compatible Reference Image` 节点，把最后一个节点的 `references` 输出接到编辑节点。

`reference_image_count` 控制实际发送多少张参考图。设置为 `0` 表示发送所有已连接的固定槽图片或整个参考图列表。

每张参考图都可以写提示词。默认会把参考图提示词按顺序追加进主 prompt：

```text
Reference image 1: use this as the subject identity.
Reference image 2: use this as the lighting and style.
```

官方 OpenAI 图片编辑接口没有单独定义“每张图的提示词字段”。如果你的自定义端点支持，可以设置 `reference_prompt_field`，例如：

```text
reference_prompt[]
```

默认 multipart 图片字段是：

```text
image[]
```

如果你的端点需要重复的 `image` 字段，把 `image_field` 改成：

```text
image
```

## 示例工作流

仓库内包含两个示例：

- `workflows/openai_compatible_text_to_image_workflow.json`
- `workflows/openai_compatible_reference_images_workflow.json`

安装节点后，在 ComfyUI 中导入即可。

## 兼容说明

`model` 是自由文本字段。默认值是 `gpt-image-2`，因为不少自定义端点会使用这个模型名；你可以改成自己的端点支持的任意模型名。

节点期望 OpenAI 风格响应：

```json
{
  "data": [
    {"b64_json": "..."}
  ]
}
```

也支持 URL 响应：

```json
{
  "data": [
    {"url": "https://..."}
  ]
}
```

## 目录结构

当前仓库结构：

```text
ComfyUI-OpenAI-Compatible-Image/
├── __init__.py
├── README.md
├── README.zh-CN.md
├── requirements.txt
├── pyproject.toml
├── LICENSE
├── workflows/
└── docs/
```

后续节点和 workflow 的组织建议见：

```text
docs/repo-layout.zh-CN.md
```

## 安全建议

优先使用 `OPENAI_API_KEY` 环境变量，不建议把 key 写进 workflow。workflow 可能会被分享，节点 widget 值也可能保存在 workflow JSON 中。

## 排查问题

### 第二次生成一直超时

有些 OpenAI-compatible 代理会错误地保持 HTTP 连接，导致第二次请求复用旧连接时卡住。节点现在默认发送 `Connection: close`，避免复用这种不稳定连接。

如果仍然超时：

- 把 `timeout_seconds` 调到 `900` 或 `1200`。
- 把 `n` 降到 `1`。
- 减少参考图数量或参考图分辨率。
- 确认服务商是不是异步任务接口，而不是直接返回 `data[].b64_json` 或 `data[].url`。
- 如果服务商需要自定义轮询接口，这个节点需要额外适配 provider-specific async polling。

## 开发校验

基础检查：

```bash
python -m py_compile __init__.py
python -m json.tool workflows/openai_compatible_text_to_image_workflow.json
python -m json.tool workflows/openai_compatible_reference_images_workflow.json
```

## 许可证

MIT
