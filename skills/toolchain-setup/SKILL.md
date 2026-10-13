---
name: toolchain-setup
description: 引导用户安装并配置 AI 采集工具链。涵盖 ChatGPT 桌面版安装、cc-switch 安装、中转站（OpenAI 兼容 API 网关）配置、Codex CLI / Claude Code 安装与配置、浏览器扩展安装。当用户需要「安装 ChatGPT」「装 cc-switch」「配置中转站」「接入公司 API」「配置 model base url」「装 Codex CLI」时使用。
---

# 工具链安装与配置

把 AI 采集所需的工具装好、配好、验证好。**核心原则：一次只装一个，装完验证再装下一个。**

---

## 一、ChatGPT 桌面版（路线 A）

### 前置条件

- **必须能访问境外站点**（先跑 `env-check` 的网络检测）
- **需要 ChatGPT 付费订阅**（Plus / Pro / Team / Business / Edu）——Computer Use 功能需要 ChatGPT Work 或 Codex 入口
- Windows 10/11，或 macOS 14+（Apple Silicon M1 及以上 / Intel）

### 安装方式（优先官方源）

**Windows：**
1. **推荐**：Microsoft Store 搜索 "ChatGPT"，确认**开发者显示为 OpenAI**，点击安装
   - 官方商店页：`https://apps.microsoft.com/detail/9plm9xgg6vks`
2. 备选：访问 `https://chatgpt.com/download`，页面会自动识别系统给出对应版本

**macOS：**
- 访问 `https://chatgpt.com/download` 下载 `.dmg`

> ⚠️ **安全红线**：不要为了"下载快"去找汉化版、绿色版、整合包。来路不明的安装器风险极高。
> 国内网络下载慢时，引导用户**从公司/组织内部正规途径获取安装包**，或先解决网络访问问题。

### 安装后验证

1. 打开 ChatGPT 桌面版，登录账号
2. 左侧切换到 **Work** 或 **Codex** 入口（Computer Use 在这两个视图下可用）
3. 进入 `Plugins → Computer Use`，点击 Install plugin
4. 打开 Computer Use server 和 skill 两个开关
5. 进入 `Settings → Computer use`，确认应用访问权限列表

### 系统权限（macOS 专用）

macOS 需要授予两项权限，缺一不可：
- **屏幕录制（Screen Recording）**：让 ChatGPT 看到目标应用
- **辅助功能（Accessibility）**：让 ChatGPT 能点击、输入、导航

> **Windows 无需这两项权限**，但**目标应用必须保持在活动桌面可见**——Computer Use 会在前台接管鼠标键盘，任务运行时用户无法同时做别的事。**必须提前告知用户这一点。**

---

## 二、cc-switch（命令行工具的中转站切换器）

### cc-switch 是什么（给用户的解释）

> "它是一个小工具，让你在 Claude Code、Codex 这些命令行 AI 工具之间一键切换 API 服务商。比如你想让 Claude Code 用公司的中转站而不是官方地址，用它点一下就切好了，不用手改配置文件。"

> ⚠️ **重要技术边界**：cc-switch **不能**给 ChatGPT 桌面版换后端。ChatGPT 桌面版只能走 OpenAI 官方账号登录。cc-switch 管的是 **Claude Code / Codex CLI / Gemini CLI / OpenCode** 这类命令行工具的供应商配置。

### 支持的平台

| 平台 | 安装方式 |
|------|---------|
| Windows | 从 Releases 下载 `CC-Switch-v{版本}-Windows.msi`（安装包）或 `-Windows-Portable.zip`（绿色版）；ARM 设备下载 `-Windows-arm64.msi` |
| macOS | `brew install --cask cc-switch`（推荐，已签名公证）；或下载 `-macOS.dmg` |
| Linux | `.deb` / `.rpm` / `.AppImage` |

- 官方仓库：`https://github.com/farion1231/cc-switch`
- 官网：`https://ccswitch.io`

**系统要求**：Windows 10+ / macOS 12+ / Ubuntu 22.04+ 等

### 安装后验证

1. 启动 cc-switch，能看到主界面和供应商列表
2. 托盘图标存在（可在托盘快捷切换供应商）

---

## 三、中转站配置

### 中转站是什么（给用户的解释）

> "中转站是一个 API 网关，它和 OpenAI 的接口格式完全兼容。把 AI 工具的接口地址从官方换成中转站地址，就能在国内网络下直接用上模型能力，不用翻墙。"

### 配置三项信息

从**企业/组织内部途径**获取：

| 字段 | 说明 | 示例格式 |
|------|------|---------|
| 接口地址（Base URL） | 必须以 `/v1` 结尾 | `https://your-relay.example.com/v1` |
| API Key | 通常以 `sk-` 开头 | `sk-xxxxxxxxxxxx` |
| 模型名称 | 必须精确匹配网关支持的模型名 | `deepseek-v4-flash` |

> ⚠️ **密钥安全**：API Key 只写入用户本机配置文件，**绝不写入专家包、脚本、README 或任何会分享的文件**。
> 如果用户提供了配置文档链接但读取失败（需内部鉴权），**请用户粘贴关键内容**，不要编造地址。

### 配置方式 A：通过 cc-switch 图形界面（推荐给普通用户）

1. 打开 cc-switch，顶部切换到目标应用（如 **Claude Code**）
2. 点击右上角 **+ 添加供应商**
3. 类型选择与中转站匹配的协议：
   - 中转站提供 **Anthropic 兼容**接口 → 选「Anthropic 兼容」
   - 中转站提供 **OpenAI 兼容**接口 → 选「OpenAI 兼容」
4. 填写：
   - **名称**：随意，建议标注"中转站"
   - **Base URL**：中转站的接口地址（注意 `/v1` 后缀）
   - **API Key**：中转站的密钥
5. 保存后**点击卡片激活**（卡片前出现勾选标记才生效）

> **常见坑**：保存 ≠ 激活。cc-switch 的逻辑是"主动选中才生效"。用户报"配置了但还是报 Invalid API key"，八成是没激活。

### 配置方式 B：直接编辑配置文件（Agent 自助配置）

**给 Claude Code 配置**（改 `~/.claude/settings.json`）：
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://your-relay.example.com/v1",
    "ANTHROPIC_AUTH_TOKEN": "<完整 API Key>"
  },
  "model": "<模型名>"
}
```

**给 Codex CLI 配置**（改 `~/.codex/config.toml`）：
```toml
model_provider = "relay"
model = "<模型名>"

[model_providers.relay]
name = "relay"
base_url = "https://your-relay.example.com/v1"
wire_api = "responses"
requires_openai_auth = true
```

> ⚠️ **改前必须先备份**：`cp config.toml config.toml.bak`

### 连通性实测（不可跳过）

```bash
curl -s https://your-relay.example.com/v1/models \
  -H "Authorization: Bearer <API_KEY>" \
  --max-time 10
```

| 结果 | 判定 | 处理 |
|------|------|------|
| 返回模型列表 JSON | ✅ 通了 | 继续验证 CLI |
| 401 / 403 | ❌ 认证失败 | 检查 Key 是否正确、有无多余空格 |
| 404 | ❌ 地址错 | 检查 Base URL 是否漏了 `/v1` |
| 超时 | ❌ 网络不通 | 检查网络、地址拼写、是否需要内网 |

---

## 四、CLI 工具安装（配合 cc-switch 使用）

### Codex CLI

**前置**：Node.js 18+（推荐 22+）、npm

```bash
# 国内网络先切镜像源（重要，否则安装会超时）
npm config set registry https://registry.npmmirror.com

# 全局安装
npm install -g @openai/codex

# 验证
codex --version
```

**Windows 常见坑**：如果报"禁止运行脚本"，用管理员 PowerShell 执行：
```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Claude Code

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

### 验证 cc-switch + CLI 全链路

```bash
# 配置并激活 cc-switch 供应商后
claude "用一句话回复：已连通"

# 或
codex "用一句话回复：已连通"
```

- 返回中文回复 → ✅ 全链路通（CLI → cc-switch → 中转站 → 模型）
- 报 `Invalid API key` → 检查 cc-switch 是否**已激活**该供应商
- 报连接错误 → 检查中转站地址与网络

---

## 五、浏览器扩展安装

### 5.1 ChatGPT 官方浏览器扩展（路线 A）

**支持的浏览器**：Chrome、Edge、Brave、Opera、Vivaldi

**安装方式**：
1. 在 ChatGPT 桌面版中：`Plugins → Chrome → Install`（按流程提示操作）
2. 或从浏览器扩展商店安装：
   - Chrome：Chrome Web Store 搜索官方扩展，**确认发布者是 OpenAI**
   - Edge / Brave / Vivaldi：同样从 Chrome Web Store 安装（Chromium 内核兼容）

**安装后验证**：
1. 浏览器工具栏出现 ChatGPT 图标
2. ChatGPT 桌面版 `Settings → Computer use` 里，Google Chrome 显示 **Manage**（而不是 Install）
3. 打开浏览器，确认侧边栏 ChatGPT 面板能加载

> **注意**：部分浏览器不支持侧边聊天（如 Opera），但仍支持桌面端操控。浏览器可用性可能受账号权限与灰度发布影响。

### 5.2 WorkBuddy 浏览器扩展（路线 B）

**安装方式**：
1. 打开 WorkBuddy → **设置 → 智能体**
2. 在**浏览器操控**区域找到自己的浏览器（Chrome / Edge / QQ 浏览器）
3. 点击**前往安装**，按提示安装扩展
4. 安装后**确认扩展已启用**

**安装后验证**：
- 回到 WorkBuddy 对话，尝试获取浏览器列表，能返回浏览器信息即成功
- 若报 `extension_disconnected`，检查扩展是否被禁用、浏览器是否在运行

> **注意**：WorkBuddy 浏览器扩展是 WorkBuddy 内置能力的入口，安装位置在 WorkBuddy 设置里，不在扩展商店。

### 5.3 扩展安装安全提醒（必说）

- **只装官方发布**的扩展，安装前确认**发布者名称**
- 不要靠"名字里带 ChatGPT / AI"来判断官方性——大量第三方扩展用相似名称
- 安装时留意权限提示，权限过大（如"读取所有网站数据"）时谨慎

---

## 执行顺序建议

```
路线 A（ChatGPT）：
  ChatGPT 桌面版 → 登录验证 → Computer Use 插件 → ChatGPT 浏览器扩展 → 采集

路线 B（WorkBuddy）：
  WorkBuddy 浏览器扩展 → 验证 → 采集
  （可选进阶）cc-switch → 中转站配置 → CLI 工具 → 链路验证

混合场景：
  两条链路都可装。先装能立刻跑通的那条，让用户先看到成果。
```

---

## 注意事项

1. **一次只装一个**，装完验证再继续。用户同时装三个东西必然出错。
2. **每步给验证方法**，让用户能自己确认成功。
3. **改配置前先备份**。
4. **国内网络必加镜像参数**：npm 用 `--registry=https://registry.npmmirror.com`，pip 用 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
5. **不确定就说不确定**：下载地址、命令参数如果不确定，明确告知并去查，不要猜。
6. **绝不硬编码密钥**：所有涉及密钥的操作都从用户处获取，只写本机配置。
