---
name: auto-update
description: AI采集助手专家包的自动更新与本地刷新。用户开始服务前先检查 GitHub 生产分支是否有新版本，有则自动下载覆盖本地专家包，并刷新本地 WorkBuddy 注册信息，随后按最新指令继续服务。当用户说「更新专家」「检查更新」「有新版本吗」「刷新专家」时使用。
---

# auto-update — 专家包自动更新与本地刷新

非作者用户使用本专家包时，**先检查 GitHub 生产分支（main）是否有新版本**，有则自动更新到本地，**再刷新本地注册信息**，然后才开始采集配置服务。

## 硬性规则（写死，不可违反）

- **作者 userId**：`e266ae24-3f86-4af8-9ca6-b9218cd6845f`（作者本人不触发更新，本地即源码仓库）
- **默认分支锁定**：非作者用户**默认仅可获取生产环境（main）**，严禁切换其他分支
- 更新来源固定为 `https://github.com/SuperCup/ai-collection-assistant` 的 main 分支
- **体验通道例外**：仅当用户 userId 在 `preview_member_ids` 白名单（仅读取专家包根 `config.json`，**不读环境变量**，防用户自设绕过）时，可使用 `--channel test` 从 test 开发分支获取体验版；白名单外一律拒绝
- **非白名单用户自动切回 main**：请求 `--channel test` 被拒绝时，专家**立即默认切回 main（生产）**继续服务，不得中断、不得反复重试

## 使用方式

```bash
# 检查是否有更新（默认生产通道 main）
python3 skills/auto-update/scripts/auto_update.py check

# 检查并执行更新（自动下载解压覆盖本地专家包 + 刷新本地注册）
python3 skills/auto-update/scripts/auto_update.py update

# 仅刷新本地注册信息（不下载，用于展示信息同步）
python3 skills/auto-update/scripts/auto_update.py refresh

# 体验通道（仅白名单用户，从 test 开发分支获取最新体验版）
python3 skills/auto-update/scripts/auto_update.py check  --channel test
python3 skills/auto-update/scripts/auto_update.py update --channel test
```

## 输出状态码

| 状态码 | 含义 | 处理 |
|--------|------|------|
| `AUTHOR_MODE` | 作者本人使用 | 不更新，本地自行 git 管理 |
| `UP_TO_DATE` | 已是最新版本 | 直接开始服务 |
| `UPDATE_AVAILABLE: x -> y` | 检测到新版本 | 执行 `update` 更新 |
| `UPDATED` | 更新完成（含注册刷新） | 按最新指令继续服务；提醒用户新开会话获取完整指令 |
| `LOCAL_REGISTRATION: 已刷新` | 本地注册信息已同步 | 正常继续 |
| `REFRESHED` | 本地注册信息已刷新 | 正常继续 |
| `NO_USER_ID` | 无法识别当前用户 | 保守不更新，正常服务 |
| `LOCAL_NEWER` | 本地版本高于远程 | 不更新（防降级），确认通道 |
| `ERROR:...` | 网络/解析等错误 | 继续使用当前版本，提示网络异常未自动更新 |

## 启动时的标准流程（不可跳过）

```
第 1 步：运行 check
  ├─ AUTHOR_MODE      → 跳过更新，直接服务
  ├─ NO_USER_ID       → 跳过更新，直接服务
  ├─ UP_TO_DATE       → 直接服务
  ├─ UPDATE_AVAILABLE → 进入第 2 步
  └─ ERROR:...        → 静默跳过，直接服务（不打扰用户）

第 2 步：运行 update
  ├─ UPDATED              → 进入第 3 步
  ├─ UP_TO_DATE           → 直接服务
  ├─ LOCAL_NEWER          → 不更新，直接服务
  └─ ERROR:...            → 告知用户更新失败原因，用当前版本继续服务

第 3 步：检查是否输出 INSTRUCTION_UPDATED 块
  ├─ 有 → 当前会话立即读取最新 agents/ai-collection-assistant.md 全文，
  │       按最新流程继续执行；同时提醒用户新开会话获取完整最新指令
  └─ 无 → 直接服务

第 4 步：开始采集配置服务（进入主流程 Step 1 环境体检）
```

> ⚠️ **更新失败绝不阻塞服务**。网络异常、下载失败、文件占用等情况，一律静默降级为"使用当前版本继续服务"，仅在有明确输出时简要告知。

## 更新覆盖逻辑

- 从候选下载源获取 `<branch>` 分支 zip（`archive/refs/heads/<branch>.zip`，公开仓库免登录）
- **多源下载（国内网络友好，无需代理）**：按「上次成功源 → GitHub 直连 → 国内加速镜像」顺序依次尝试，任一成功即用、失败自动换下一个源：
  - 内置镜像：`ghfast.top`、`gh-proxy.com` 等，每源 15s 短超时，zip 完整性校验，损坏视为该源失败
  - 成功源写入缓存 `~/.workbuddy/aca_update_mirror.json`（host 白名单校验，防篡改），下次优先
  - 作者追加镜像：在专家包根 `config.json` 的 `update_mirrors` 数组加前缀，随包分发即可，无需改脚本
  - 全部失败才报 `ERROR`（提示检查网络），正常服务当前版本不中断
- **只覆盖+新增，永不删除本地文件**：防止误删用户文件（旧版曾因删除逻辑误删技能目录，已彻底移除删除能力）
- 排除 `.git`、`__pycache__`、`.git-credentials`，不动用户本地数据
- 更新后同步 `marketplace.json` 的索引信息（名称/描述），保证专家中心展示与最新一致

## 安全防呆

- **根标记校验**：更新前校验专家包根目录存在 `.expert-root-marker`，不存在则**拒绝执行**（防止脚本被放置到异常路径时误删用户文件）
- **防降级保护**：本地版本高于远程时拒绝更新（`LOCAL_NEWER`），避免通道混用导致误覆盖
- **镜像白名单**：镜像缓存文件的 host 必须在白名单内，防止缓存被改写为任意 URL 引导下载恶意包
- **不读环境变量授权**：体验通道白名单只认包内 `config.json`，防用户自设环境变量绕过

## 依赖

- Python 3.8+（纯标准库：urllib / zipfile / sqlite3 / difflib，无第三方依赖）
- 国内网络访问 GitHub 直连失败时自动切换国内加速镜像；全部源失败才视为"未更新"，不影响正常使用
