# ARC Image Gen 技能

`arc-imagegen` 是一个 Codex 技能，用于通过可配置的 OpenAI 兼容 Images API 生成和编辑位图图片，也适用于 sub2api 风格的中转服务。

## 安装

将 `arc-imagegen/` 目录安装或复制到你的 Codex skills 目录：

- Windows 默认位置：`%USERPROFILE%\.codex\skills\arc-imagegen`
- macOS/Linux 默认位置：`~/.codex/skills/arc-imagegen`
- 自定义 Codex 主目录：`$CODEX_HOME/skills/arc-imagegen`

安装后重启 Codex，让新技能被加载。

如果通过 Codex 从 GitHub 安装，请让 Codex 从这个仓库安装路径为 `arc-imagegen` 的技能。

## 依赖

安装随技能提供的 Python 依赖：

```bash
python -m pip install -r arc-imagegen/requirements.txt
```

`httpx` 用于真实 API 请求。`pillow` 用于可选的图片缩放和色键背景移除。

## 配置

复制示例配置文件：

```bash
cp arc-imagegen/config.json.example arc-imagegen/config.json
```

编辑 `arc-imagegen/config.json`：

```json
{
  "base_url": "https://your-openai-compatible-images-api.example.com",
  "api_key": "YOUR_API_KEY",
  "default_model": "gpt-image-2",
  "timeout_seconds": 300
}
```

脚本会为未带版本路径的兼容 API 地址追加 `/v1`。不要把 API key 写进提示词、shell 历史记录或共享日志。

也可以使用环境变量配置：

```bash
ARC_IMAGEGEN_BASE_URL
ARC_IMAGEGEN_API_KEY
ARC_IMAGEGEN_DEFAULT_MODEL
ARC_IMAGEGEN_TIMEOUT_SECONDS
```

## 使用

在 Codex 中按名称调用这个技能：

```text
使用 $arc-imagegen 生成一个笔记应用的方形图标。
```

技能生成图片时只使用流式请求。CLI 会自动发送 `stream=true` 和 `response_format=b64_json`，即使没有显式传入 `--stream` 也不会走同步生成路径。这个模式适合 sub2api：服务端可以在长耗时生图过程中返回 event-stream 数据，避免客户端在等待最终图片时因为下游连接长时间无数据而读超时。`--stream` 参数仍然保留，主要用于兼容旧命令。

也可以直接运行 CLI：

```bash
python arc-imagegen/scripts/image_gen.py generate \
  --prompt "一个简单的蓝色圆形图标" \
  --quality medium \
  --size 1024x1024 \
  --out arc-imagegen/output/icon.png \
  --stream \
  --quiet
```

编辑图片时，请提供本地图片路径和要修改的内容：

```text
使用 $arc-imagegen 编辑 ./input.png，将背景替换为温暖的日落场景，同时保持产品主体不变。
```

## 验证

运行 dry-run，不发起真实 API 请求：

```bash
python arc-imagegen/scripts/image_gen.py generate --prompt "一个简单的蓝色圆形图标" --stream --dry-run
```

如果真实生图经常超时，先确认配置里的 API key 可用，再降低批量并发或缩小尺寸复测。生成命令已强制使用流式请求，不再提供同步生成模式；流式请求会解析最终的 `image_generation.completed` 事件并保存图片。

生成多张图片时，建议使用 `generate-batch`，并把每张图写成一个独立 JSONL 任务，不要把多张图都放进同一个 `--n 5` 请求。批量任务默认每个任务最多请求 2 次：第一次失败或超时后立即重试 1 次；第二次仍失败就放弃该任务，不再等待冷却或继续重试。

```bash
python arc-imagegen/scripts/image_gen.py generate-batch \
  --input prompts.jsonl \
  --out-dir arc-imagegen/output/batch \
  --concurrency 5 \
  --max-attempts 2 \
  --stream \
  --quiet
```

运行本地测试：

```bash
python -m unittest discover -s arc-imagegen/tests
```

使用 Codex 的 skill creator 校验工具验证技能目录：

```bash
python <path-to-skill-creator>/scripts/quick_validate.py arc-imagegen
```
