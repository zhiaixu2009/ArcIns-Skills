# ARC Image Gen 技能

`arc-imagegen` 是 `arcins-skills` Codex 插件中的第一个技能，用于通过 sub2api 或其他 OpenAI 兼容 Images API 生成和编辑位图图片。它面向 Codex 使用场景封装了提示词组织、流式生图、批量任务、失败重试和本地文件保存。

## 安装方式

本仓库通过公开 GitHub marketplace 安装插件，不再把 `arc-imagegen/` 作为单独目录手动复制到 Codex skills 目录。

在支持插件 marketplace 的 Codex CLI 中执行：

```bash
codex plugin marketplace add zhiaixu2009/ArcIns-Skills --ref main
codex plugin add arcins-skills@arcins
```

如果当前 Codex CLI 没有 `plugin` 子命令，请在 Codex App 的插件目录中添加 GitHub marketplace `zhiaixu2009/ArcIns-Skills`，选择 `main` 分支，然后安装 `ArcIns Skills`。

安装依赖：

```bash
python -m pip install "httpx>=0.27" "pillow>=10.0"
```

按照下方“配置”一节写入用户级配置后，新开一个 Codex 线程，验证 `$arc-imagegen` 可以被加载。

## 依赖

如果已经克隆本仓库，也可以从依赖文件安装：

```bash
python -m pip install -r plugins/arcins-skills/skills/arc-imagegen/requirements.txt
```

`httpx` 用于真实 API 请求。`pillow` 用于可选的图片缩放和色键背景移除。

## 配置

真实 API 配置不放进插件目录，避免插件更新覆盖密钥。请创建以下用户级配置文件：

- 已设置 `CODEX_HOME`：`$CODEX_HOME/arc-imagegen/config.json`
- Windows 默认位置：`%USERPROFILE%\.codex\arc-imagegen\config.json`
- macOS/Linux 默认位置：`~/.codex/arc-imagegen/config.json`

配置内容示例：

```json
{
  "base_url": "<YOUR_IMAGES_API_BASE_URL>",
  "api_key": "<YOUR_API_KEY>",
  "default_model": "gpt-image-2",
  "timeout_seconds": 300
}
```

如果已经克隆本仓库，也可以使用交互式配置脚本：

```bash
python plugins/arcins-skills/scripts/setup-arc-imagegen-config.py
```

脚本默认写入：

- 已设置 `CODEX_HOME`：`$CODEX_HOME/arc-imagegen/config.json`
- 未设置 `CODEX_HOME`：`~/.codex/arc-imagegen/config.json`

配置查找顺序：

1. `--config <path>`
2. `ARC_IMAGEGEN_CONFIG`
3. `$CODEX_HOME/arc-imagegen/config.json`
4. `%USERPROFILE%\.codex\arc-imagegen\config.json` 或 `~/.codex/arc-imagegen/config.json`
5. `<skill-root>/config.json`
6. `ARC_IMAGEGEN_*` 环境变量覆盖文件值

可用环境变量：

```bash
ARC_IMAGEGEN_BASE_URL
ARC_IMAGEGEN_API_KEY
ARC_IMAGEGEN_DEFAULT_MODEL
ARC_IMAGEGEN_TIMEOUT_SECONDS
```

不要把 API key 写进提示词、shell 历史记录、共享日志或插件目录。

## 在 Codex 中使用

在新线程中按名称调用技能：

```text
使用 $arc-imagegen 生成一个笔记应用的方形图标。
```

生成和编辑图片时都只走流式请求。CLI 会自动发送 `stream=true`、`response_format=b64_json` 和 `Accept: text/event-stream`，即使没有显式传入 `--stream` 也不会走同步生成路径。这样更适合 sub2api 等中转服务：服务端可以在长耗时生图或改图过程中持续返回 event-stream 数据，降低同步请求在代理层超时的概率。

## 直接运行 CLI

单图生成：

```bash
python plugins/arcins-skills/skills/arc-imagegen/scripts/image_gen.py generate \
  --prompt "一个简单的蓝色圆形图标" \
  --quality medium \
  --size 1024x1024 \
  --out plugins/arcins-skills/skills/arc-imagegen/output/icon.png \
  --stream \
  --quiet
```

编辑图片：

```bash
python plugins/arcins-skills/skills/arc-imagegen/scripts/image_gen.py edit \
  --image input.png \
  --prompt "将背景替换为温暖的日落场景，同时保持产品主体不变" \
  --quality medium \
  --out plugins/arcins-skills/skills/arc-imagegen/output/edit.png \
  --stream \
  --quiet
```

批量生成时，建议把每张图写成独立 JSONL 任务，不要把多张图都放进同一个 `--n 5` 请求。批量任务默认每个任务最多请求 2 次：第一次失败或超时后立即重试 1 次；第二次仍失败就放弃该任务，不再等待冷却或继续重试。

```bash
python plugins/arcins-skills/skills/arc-imagegen/scripts/image_gen.py generate-batch \
  --input prompts.jsonl \
  --out-dir plugins/arcins-skills/skills/arc-imagegen/output/batch \
  --concurrency 5 \
  --max-attempts 2 \
  --stream \
  --quiet
```

## 验证

运行 dry-run，不发起真实 API 请求：

```bash
python plugins/arcins-skills/skills/arc-imagegen/scripts/image_gen.py generate \
  --prompt "一个简单的蓝色圆形图标" \
  --dry-run \
  --quiet
```

`generate`、`generate-batch` 和 `edit` 的 dry-run 输出中都应包含 `stream: true` 和 `response_format: b64_json`。

运行本地测试：

```bash
python -m unittest discover -s plugins/arcins-skills/skills/arc-imagegen/tests
```

验证技能目录：

```bash
python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/arcins-skills/skills/arc-imagegen
```
