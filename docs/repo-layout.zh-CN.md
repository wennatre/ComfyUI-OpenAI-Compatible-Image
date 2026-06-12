# 后续节点和工作流的目录规划

建议采用“两类仓库”的结构：节点仓库负责可安装的 ComfyUI custom nodes，工作流仓库负责可直接导入的完整 workflow。

## 1. 每个节点项目一个独立仓库

适合提交到 ComfyUI Manager，也方便用户只安装自己需要的节点。

推荐结构：

```text
ComfyUI-Your-Node-Name/
├── __init__.py
├── nodes/
│   ├── api.py
│   └── utils.py
├── web/
│   └── js/
├── workflows/
│   ├── basic_example.json
│   └── advanced_example.json
├── docs/
│   ├── api-compatibility.zh-CN.md
│   └── troubleshooting.zh-CN.md
├── assets/
│   └── screenshot.png
├── README.md
├── README.zh-CN.md
├── requirements.txt
├── pyproject.toml
├── LICENSE
└── .gitignore
```

如果节点很小，可以像当前项目一样只保留 `__init__.py`，不强行拆 `nodes/`。

## 2. 单独建一个工作流集合仓库

当你后续开源多个节点后，复杂 workflow 往往会跨多个节点仓库。不要把这些大型 workflow 塞进某个节点仓库里，建议单独开一个集合仓库。

推荐仓库名：

```text
ComfyUI-Workflows-by-wennatre
```

推荐结构：

```text
ComfyUI-Workflows-by-wennatre/
├── README.md
├── README.zh-CN.md
├── image/
│   ├── openai-compatible/
│   │   ├── text-to-image.json
│   │   ├── reference-edit.json
│   │   └── README.zh-CN.md
│   └── flux/
├── video/
│   ├── hunyuan/
│   └── wan/
├── audio/
├── templates/
├── assets/
│   ├── screenshots/
│   └── thumbnails/
└── docs/
    ├── installation.zh-CN.md
    └── dependency-matrix.zh-CN.md
```

## 3. README 语言策略

每个仓库保留两份 README：

```text
README.md
README.zh-CN.md
```

建议 `README.md` 用英文，因为 GitHub、ComfyUI Manager、搜索索引和海外用户更容易读到。中文用户入口放在第一屏：

```md
[中文说明](README.zh-CN.md)
```

中文 README 第一屏放：

```md
[English README](README.md)
```

## 4. 命名规则

节点仓库：

```text
ComfyUI-OpenAI-Compatible-Image
ComfyUI-Provider-Name
ComfyUI-Video-Tool-Name
```

节点显示名：

```text
OpenAI Compatible Image Generate
OpenAI Compatible Image Edit With References
```

自定义类型名尽量稳定，不要频繁改：

```text
OPENAI_COMPATIBLE_IMAGE_REFERENCES
```

workflow 文件名用小写加下划线：

```text
openai_compatible_text_to_image_workflow.json
openai_compatible_reference_images_workflow.json
```

## 5. 开源前检查清单

- `README.md` 和 `README.zh-CN.md` 都能独立说明安装和使用。
- `requirements.txt` 不写不必要的大依赖。
- 示例 workflow 不包含 API key、私有路径、私有 endpoint。
- 节点能在干净 ComfyUI 环境导入。
- `python -m py_compile __init__.py` 通过。
- `python -m json.tool workflows/*.json` 通过。
- 截图不包含 key、账号、私有图片。
- License 明确，默认建议 MIT。

## 6. 当前项目定位

当前仓库适合作为后续节点仓库模板：

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

后续如果单文件变大，再拆成：

```text
nodes/
├── generate.py
├── edit.py
└── references.py
```

不要为了“看起来专业”过早拆文件。小节点保持简单更好维护。
