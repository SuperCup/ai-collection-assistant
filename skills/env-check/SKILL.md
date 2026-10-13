---
name: env-check
description: 检测用户本机环境，判定适合的 AI 采集方案。检查操作系统、浏览器、已装 AI 工具、网络连通性，输出环境体检报告与路线推荐（ChatGPT Computer Use / WorkBuddy 浏览器链路）。当用户询问「我的电脑能不能跑采集」「环境检测」「配置前检查」「网络能不能翻墙」「支持什么方案」时使用。
---

# 环境检测与环境体检报告

帮用户搞清楚**这台电脑当前是什么状态**，从而决定走哪条采集路线。检测必须**实测**，不能靠猜。

## 输出物

一份给用户看的**环境体检报告**（不要甩原始日志），以及**路线推荐 + 理由**。

---

## 检测流程

### 1. 操作系统与硬件

```bash
# Windows (Git Bash)
uname -a
systeminfo | head -5
echo "ARCH: $PROCESSOR_ARCHITECTURE"

# macOS
sw_vers
uname -m
```

### 2. 浏览器检测（决定扩展安装方式）

**Windows：**
```bash
# 检测 Chrome、Edge 的常见安装路径
for p in \
  "/c/Program Files/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
  "$LOCALAPPDATA/Google/Chrome/Application/chrome.exe" \
  "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  "/c/Program Files/Microsoft/Edge/Application/msedge.exe" ; do
  [ -f "$p" ] && echo "FOUND: $p"
done

# 取版本号
"/c/Program Files/Google/Chrome/Application/chrome.exe" --version 2>/dev/null
```

**macOS：**
```bash
[ -d "/Applications/Google Chrome.app" ] && echo "Chrome FOUND"
[ -d "/Applications/Microsoft Edge.app" ] && echo "Edge FOUND"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version 2>/dev/null
```

> ⚠️ **Windows 上的坑**：Chrome 在很多机器上**不在** `%LOCALAPPDATA%`，实际在 `C:\Program Files\Google\Chrome\Application\`。必须多路径探测，探测顺序：`Program Files → Program Files (x86) → LOCALAPPDATA → Chrome SxS → Edge`。

### 3. 已装 AI 工具检测（决定跳过哪些安装步骤）

```bash
# 命令行工具
which node npm claude codex 2>/dev/null
node -v 2>/dev/null
npm -v 2>/dev/null
claude --version 2>/dev/null
codex --version 2>/dev/null

# cc-switch（桌面应用，检查安装痕迹）
# Windows
ls "$LOCALAPPDATA/Programs" 2>/dev/null | grep -i "cc-switch\|ccswitch"
ls "$APPDATA/cc-switch" 2>/dev/null
ls "$USERPROFILE/.cc-switch" 2>/dev/null
# macOS
ls "/Applications" 2>/dev/null | grep -i "cc-switch\|ccswitch"
ls "$HOME/Library/Application Support/cc-switch" 2>/dev/null

# ChatGPT 桌面版
# Windows（Microsoft Store 安装的包）
ls "$LOCALAPPDATA/Packages" 2>/dev/null | grep -i "openai\|chatgpt"
ls "$LOCALAPPDATA/Programs" 2>/dev/null | grep -i "chatgpt\|openai"
# macOS
ls "/Applications" 2>/dev/null | grep -i "chatgpt"
```

### 4. 网络连通性检测（**最关键的一项**）

**必须实测，不能问用户"你能不能翻墙"**——用户的自我判断经常不准。

```bash
# 境外站点连通性（超时设为 5 秒，避免长时间卡住）
curl -s -o /dev/null -w "chatgpt.com: %{http_code} (%{time_total}s)\n" \
  --max-time 5 https://chatgpt.com 2>/dev/null || echo "chatgpt.com: FAILED"

curl -s -o /dev/null -w "google.com: %{http_code} (%{time_total}s)\n" \
  --max-time 5 https://www.google.com 2>/dev/null || echo "google.com: FAILED"

curl -s -o /dev/null -w "api.openai.com: %{http_code} (%{time_total}s)\n" \
  --max-time 5 https://api.openai.com 2>/dev/null || echo "api.openai.com: FAILED"

# 境内源连通性（对比用）
curl -s -o /dev/null -w "baidu.com: %{http_code}\n" --max-time 5 https://www.baidu.com 2>/dev/null
curl -s -o /dev/null -w "npmjs: %{http_code}\n" --max-time 5 https://registry.npmjs.org 2>/dev/null
curl -s -o /dev/null -w "npmmirror: %{http_code}\n" --max-time 5 https://registry.npmmirror.com 2>/dev/null
```

**判定规则：**

| 现象 | 判定 | 影响 |
|------|------|------|
| chatgpt.com 返回 200/301/403 且耗时 < 3s | ✅ 可直连境外 | 可走路线 A，软件从官方源下载 |
| chatgpt.com 超时/连接被拒，但 baidu 正常 | ⚠️ 无法访问境外站点 | 只能走路线 B，软件从国内镜像获取 |
| 全部超时 | ❌ 网络异常 | 先排查网络基础问题 |
| 耗时 > 5s 但成功 | ⚠️ 网络质量差 | 建议配代理，否则后续会频繁超时 |

> **注意**：返回 403 也算"能连上"（说明网络通，只是被服务端拒绝）。真正的"不通"是**超时**或**连接被重置**。

---

## 路线判定逻辑（严格按此执行）

```
步骤 1：网络能否访问境外站点？
  ├─ 否 → 路线 B（WorkBuddy 浏览器链路）
  └─ 是 → 步骤 2

步骤 2：是否有 ChatGPT 付费订阅（Plus/Pro/Team/Business/Edu）？
  ├─ 不确定 → 先问用户，或默认推荐路线 B
  ├─ 否 → 路线 B（可提示：路线 A 需要订阅）
  └─ 是 → 两条都可用，默认推荐路线 B（零额外成本），尊重用户选择
```

**路线说明：**

| 路线 | 方案 | 前提 | 特点 |
|------|------|------|------|
| **A** | ChatGPT Computer Use | 可访问境外站点 + ChatGPT 付费订阅 | AI 直接操控浏览器；**Windows 上前台接管**，任务时无法做别的事 |
| **B** | WorkBuddy 浏览器链路 | 无需翻墙 | 零额外成本；用 WorkBuddy 浏览器扩展操控浏览器 |

---

## 体检报告模板（给用户看的）

```
📋 环境体检报告
═══════════════════════════
【系统环境】
  操作系统：Windows 11 (x64) ✅
  浏览器：Chrome 131 ✅ / Edge 存在

【网络环境】
  境外站点：❌ 无法访问（chatgpt.com 超时）
  境内源：✅ 正常
  → 结论：纯国内网络环境

【已装工具】
  Node.js：✅ v22.x
  Claude Code：✅ 已装
  cc-switch：❌ 未装
  ChatGPT 桌面版：❌ 未装
═══════════════════════════

🎯 推荐方案：路线 B（WorkBuddy 浏览器链路）

理由：当前网络无法访问境外站点，ChatGPT 桌面版无法登录使用；
      WorkBuddy 浏览器链路完全国内可用，无需翻墙。

接下来我会带你完成：
  Step 1 安装 WorkBuddy 浏览器扩展
  Step 2 配置中转站（可选，用于命令行工具）
  Step 3 验证链路
  Step 4 开始采集
```

---

## 注意事项

1. **不要跳过网络检测**：这是路线分流的唯一依据，凭用户口述判断经常出错。
2. **超时设短**：`--max-time 5`，否则用户会以为程序卡死。
3. **区分"能连上"和"能用"**：能连上 chatgpt.com，不代表账号能登录（可能被风控）。体检报告里只陈述事实，不打包票。
4. **不要在体检阶段就要求用户填 API Key**：先看环境，再谈配置。
5. **体检结果异常时不要下结论说"你电脑有问题"**：只描述检测到的事实，然后给解决方向。
6. **体检完必须给明确的下一步**：用户看完报告应该知道"我现在该做什么"。
