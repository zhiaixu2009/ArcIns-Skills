# ArcIns Skills

ArcIns Skills 是一个可通过 GitHub marketplace 安装的 Codex 插件。当前包含 `arc-imagegen` 技能，用于通过 sub2api 或其他 OpenAI-compatible Images API 生成和编辑图片。

## 快速安装

### 1. 确认 Codex 支持插件命令

```bash
codex plugin --help
```

如果能看到 `add`、`list` 和 `marketplace` 等子命令，即可继续使用 CLI 安装。

### 2. 添加 ArcIns marketplace

```bash
codex plugin marketplace add zhiaixu2009/ArcIns-Skills --ref main
```

该命令会从 GitHub 的 `main` 分支添加名为 `arcins` 的 marketplace。

### 3. 安装插件

```bash
codex plugin add arcins-skills@arcins
```

安装后可检查状态：

```bash
codex plugin list
```

列表中应显示 `arcins-skills@arcins` 为 `installed, enabled`。

### 4. 安装 Python 依赖

```bash
python -m pip install "httpx>=0.27" "pillow>=10.0"
```

### 5. 配置 Images API

在 Codex 用户目录创建 `arc-imagegen/config.json`：

- 设置了 `CODEX_HOME`：`$CODEX_HOME/arc-imagegen/config.json`
- Windows 默认路径：`%USERPROFILE%\.codex\arc-imagegen\config.json`
- macOS/Linux 默认路径：`~/.codex/arc-imagegen/config.json`

配置示例：

```json
{
  "base_url": "https://sub-api.example.com",
  "api_key": "YOUR_API_KEY",
  "default_model": "gpt-image-2",
  "timeout_seconds": 300
}
```

请勿把真实 API key 放入插件目录、Git 仓库、提示词或共享日志。

## 在 Codex App 中安装

如果当前 Codex CLI 没有 `plugin` 子命令，可以在 Codex App 的插件界面添加 GitHub marketplace：

```text
zhiaixu2009/ArcIns-Skills
```

选择 `main` 分支，然后安装 `ArcIns Skills`。安装完成后新建一个 Codex 对话，使插件中的技能被重新加载。

## 验证安装

新建 Codex 对话后输入：

```text
使用 $arc-imagegen 生成一个简洁的应用图标。
```

能够识别并调用 `$arc-imagegen`，即表示插件已正确加载。真实生图前请确保依赖和 API 配置已经完成。

## 升级

```bash
codex plugin marketplace upgrade arcins
codex plugin add arcins-skills@arcins
```

升级完成后新建 Codex 对话。用户级 `config.json` 位于插件目录之外，不会被升级覆盖。

## 详细文档

- [ArcIns Skills 插件说明](arcins-skills.README.md)
- [ARC Image Gen 技能说明](arc-imagegen.README.md)

