# ArcIns Skills 插件

`arcins-skills` 是一个可通过公开 GitHub marketplace 安装的 Codex 插件，用来集中管理 ArcIns 的可复用技能。当前内置的第一个技能是 `arc-imagegen`，用于通过 sub2api 或其他 OpenAI 兼容 Images API 进行流式生图和图片编辑。后续新增的自动化、内容生产或工作流技能都应继续放在同一个插件下，方便统一安装、更新和分发。

## 目录结构

```text
plugins/
  arcins-skills/
    .codex-plugin/
      plugin.json
    assets/
      imagegen.png
    scripts/
      setup-arc-imagegen-config.py
    skills/
      arc-imagegen/
        SKILL.md
        agents/
        assets/
        references/
        scripts/
        tests/
.agents/
  plugins/
    marketplace.json
arc-imagegen.README.md
arcins-skills.README.md
```

约定：

- 插件总入口固定为 `plugins/arcins-skills`。
- 每个技能放在 `plugins/arcins-skills/skills/<skill-name>/`。
- 技能目录内只放 Codex 使用技能所需的 `SKILL.md`、脚本、引用资料、资源和测试。
- 面向用户的 README 放在仓库根目录，命名为 `<skill-name>.README.md`。
- 插件总说明放在仓库根目录的 `arcins-skills.README.md`。
- 真实 API key、用户配置、输出图片、缓存和 `__pycache__` 不进入插件包，也不提交仓库。

## 公开安装

仓库地址：`https://github.com/zhiaixu2009/ArcIns-Skills`

在支持插件 marketplace 的 Codex CLI 中执行：

```bash
codex plugin marketplace add zhiaixu2009/ArcIns-Skills --ref main
codex plugin add arcins-skills@arcins
```

如果当前 Codex CLI 没有 `plugin` 子命令，请在 Codex App 的插件目录中添加 GitHub marketplace `zhiaixu2009/ArcIns-Skills`，选择 `main` 分支，然后安装 `ArcIns Skills`。

安装或升级插件后，请新开 Codex 线程，使最新技能和工具被加载。

## 安装后配置

先安装 `arc-imagegen` 使用的 Python 依赖：

```bash
python -m pip install "httpx>=0.27" "pillow>=10.0"
```

真实 API 配置必须放在 Codex 用户目录，而不是插件目录：

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

也可以克隆仓库后运行交互式配置脚本：

```bash
git clone https://github.com/zhiaixu2009/ArcIns-Skills.git
cd ArcIns-Skills
python plugins/arcins-skills/scripts/setup-arc-imagegen-config.py
```

配置脚本会把密钥写入 Codex 用户目录，而不是插件目录：

- 已设置 `CODEX_HOME`：`$CODEX_HOME/arc-imagegen/config.json`
- 未设置 `CODEX_HOME`：`~/.codex/arc-imagegen/config.json`

配置完成后，请在新线程中验证 `$arc-imagegen` 能被加载。

## 升级插件

当 marketplace 或插件发布了新版本时，可在支持插件命令的 Codex CLI 中执行：

```bash
codex plugin marketplace upgrade arcins
codex plugin add arcins-skills@arcins
```

升级完成后新开 Codex 线程。用户级 `config.json` 不在插件目录中，不会被插件升级覆盖。

## 当前技能

### `arc-imagegen`

用途：

- 生成图片、图标、海报、封面、背景、产品图、页面视觉稿等位图资源。
- 编辑已有本地图片。
- 通过 JSONL 批量生成多张图片。
- 使用 `stream=true`、`response_format=b64_json` 和 `Accept: text/event-stream` 进行流式生成与编辑。
- 对批量任务使用独立请求和并发控制，单个任务失败不会影响已经完成的图片。

详细说明见根目录的 `arc-imagegen.README.md`。

## 新增技能约定

新增技能时按以下方式扩展：

1. 在 `plugins/arcins-skills/skills/` 下创建新技能目录，例如 `plugins/arcins-skills/skills/example-skill/`。
2. 技能目录必须包含 `SKILL.md`，并按需包含 `agents/`、`scripts/`、`references/`、`assets/`、`tests/`。
3. 不在技能目录内新增 README、安装指南或变更日志。
4. 在仓库根目录新增 `<skill-name>.README.md`，并使用中文编写。
5. 如需用户密钥或本地配置，优先写入 `$CODEX_HOME/<skill-name>/` 或 `~/.codex/<skill-name>/`，不要写入插件目录。
6. 更新 `plugins/arcins-skills/.codex-plugin/plugin.json` 的 `interface.longDescription` 或关键词，让插件说明反映新增能力。
7. 为新增技能补充最小必要测试，并运行技能验证。

## 本地验证

验证插件结构：

```bash
python C:/Users/Administrator/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/arcins-skills
```

验证 `arc-imagegen` 技能：

```bash
python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/arcins-skills/skills/arc-imagegen
```

运行 `arc-imagegen` 单元测试：

```bash
python -m unittest discover -s plugins/arcins-skills/skills/arc-imagegen/tests
```

验证 dry-run 会强制流式生成/编辑参数：

```bash
python plugins/arcins-skills/skills/arc-imagegen/scripts/image_gen.py generate \
  --prompt "test" \
  --dry-run \
  --quiet
```

输出 JSON 中应包含：

```json
{
  "stream": true,
  "response_format": "b64_json"
}
```

## 发布与提交注意事项

提交前检查：

- 不提交 `config.json`。
- 不提交 `output/` 下的生成图片。
- 不提交 `__pycache__/`。
- 不提交真实 API key。
- README 和面向用户的说明保持中文。
- `plugin.json` 中的插件名保持 `arcins-skills`。
- `.agents/plugins/marketplace.json` 中的 marketplace 名保持 `arcins`。
- 发布新版本时更新 `plugin.json` 的语义化版本号，并确保 `main` 分支包含对应提交。

建议发布流程：

```bash
python C:/Users/Administrator/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/arcins-skills
python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/arcins-skills/skills/arc-imagegen
python -m unittest discover -s plugins/arcins-skills/skills/arc-imagegen/tests
git push origin main
git tag v0.1.2
git push origin v0.1.2
```

当前仓库提供的是可公开分享的 GitHub 自定义 marketplace。它不代表插件已经进入 OpenAI 官方维护的公共插件目录。
