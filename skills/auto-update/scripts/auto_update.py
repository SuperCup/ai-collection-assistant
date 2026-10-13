#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI采集助手 专家包 — 自动更新脚本
================================================
功能:用户使用专家包时,先检查 GitHub 生产分支(main)是否有更新,
有则自动下载最新专家包并覆盖本地安装目录,随后刷新本地注册信息,
使当前会话可直接按最新指令继续服务。

硬性规则(写死,不可配置):
- AUTHOR_USER_ID:作者(包维护者)的 WorkBuddy userId,作者本人不触发更新
- BRANCH:非作者用户仅可获取生产环境 main,不接受任何分支参数,不可切换

机制(纯 zip,不依赖 GitHub API,无匿名限流问题;国内网络友好):
1. 按候选源顺序下载 <branch> 分支 zip(公开仓库免登录):
   GitHub 直连 → 国内加速镜像(ghfast.top 等),任一成功即用,失败自动换下一个源;
   每源 15s 短超时 + zip 完整性校验,损坏视为该源失败
2. 成功源写入缓存(~/.workbuddy/aca_update_mirror.json,host 白名单校验)下次优先;
   镜像列表可经包根 config.json 的 update_mirrors 追加(作者免改代码即可维护)
3. 解压到临时目录,读取新包根目录 .update-version.json 的 version
4. 与本地已安装的 .update-version.json 的 version 比较,不同则覆盖更新
5. 更新成功后同步 marketplace.json 注册信息(保持市场展示与最新一致)

用法:
    python3 auto_update.py check   # 检查更新,输出状态
    python3 auto_update.py update  # 检查并执行更新(含本地注册刷新)
    python3 auto_update.py refresh # 仅刷新本地注册信息(不下载)

输出格式(供 AI/用户解析):
    AUTHOR_MODE            : 作者本人,不更新(本地即源码仓库)
    UP_TO_DATE             : 已是最新
    UPDATE_AVAILABLE       : 有新版本,执行 update 可更新
    UPDATED                : 更新完成(含注册刷新)
    REFRESHED              : 本地注册信息已刷新
    NO_USER_ID             : 无法识别当前用户,保守不更新
    LOCAL_NEWER            : 本地版本高于远程,拒绝降级
    ERROR:<原因>           : 出错(网络/解析等)

指令热加载:update 成功后,若 agents/ai-collection-assistant.md 有内容变化,
额外输出 INSTRUCTION_UPDATED 块(含新旧版本号与变更摘要)。当前会话 Agent 应读取
最新 agents/ai-collection-assistant.md 并按最新流程继续执行(无需等待新开会话);
完整指令仍建议用户新开会话获取。
"""

import difflib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

# ─── 写死的规则 ──────────────────────────────────────────
AUTHOR_USER_ID = "e266ae24-3f86-4af8-9ca6-b9218cd6845f"  # 作者 WorkBuddy userId
DEFAULT_BRANCH = "main"  # 非作者默认仅可获取生产环境
PREVIEW_BRANCH = "test"  # 体验通道分支(白名单用户从 test 开发分支获取体验版)
REPO = "SuperCup/ai-collection-assistant"
AGENT_NAME = "ai-collection-assistant"
EXPERT_NAME = "ai-collection-assistant"
AGENT_MD = f"agents/{AGENT_NAME}.md"

# ─── 多源下载(国内网络友好)──────────────────────────────
DOWNLOAD_TIMEOUT = 15   # 单源下载超时(秒):zip 仅 ~400KB,15s 足够国内镜像
MIRROR_CACHE_FILE = Path.home() / ".workbuddy" / "aca_update_mirror.json"  # 成功源缓存
# 内置备用加速镜像前缀(保底:即使 config.json 缺失/被改坏仍有兜底)
DEFAULT_MIRRORS = ["https://ghfast.top", "https://gh-proxy.com"]

# 本地版本记录文件名(放在专家包根目录,随包分发/覆盖)
VERSION_FILE = ".update-version.json"
# 覆盖时排除(用户本地数据与运行产物,不触碰)
EXCLUDE_NAMES = {".git", "__pycache__", ".git-credentials"}
# 专家包根标记文件:位于专家包根目录,更新前必须校验存在,
# 防止脚本被放置/解析到异常路径时误删用户文件(安全防呆)
ROOT_MARKER = ".expert-root-marker"


def _zip_url(branch: str) -> str:
    return f"https://github.com/{REPO}/archive/refs/heads/{branch}.zip"


def get_expert_root(require_marker: bool = False) -> Path:
    """定位专家包根目录(本脚本位于 <root>/skills/auto-update/scripts/)"""
    root = Path(__file__).resolve().parents[3]
    if require_marker and not (root / ROOT_MARKER).exists():
        raise RuntimeError(
            f"专家包根目录校验失败(缺少 {ROOT_MARKER}): {root} — 已拒绝执行更新,请检查安装完整性"
        )
    return root


def get_marketplace_dir() -> Path | None:
    """定位 marketplace 根目录(专家包根的上两级: plugins/<name> -> my-experts)"""
    try:
        root = get_expert_root()
        # <marketplace>/plugins/<expert-name> -> parents[1] = plugins, parents[2] = marketplace
        plugins_dir = root.parent
        if plugins_dir.name == "plugins":
            return plugins_dir.parent
    except Exception:
        pass
    return None


def _config_field(field: str, default=None):
    """读取包根 config.json 的指定字段(缺失/异常返回 default)"""
    try:
        cfg_path = get_expert_root() / "config.json"
        if not cfg_path.exists():
            return default
        return json.loads(cfg_path.read_text(encoding="utf-8")).get(field, default)
    except Exception:
        return default


def _config_update_mirrors() -> list:
    """包根 config.json 的 update_mirrors 字段(作者免改代码即可追加镜像,随包分发)"""
    raw = _config_field("update_mirrors", []) or []
    out = []
    for m in raw:
        m = str(m).strip().rstrip("/")
        if m.startswith(("https://", "http://")) and m not in out:
            out.append(m)
    return out


def _allowed_download_hosts() -> set:
    """下载源 host 白名单:github.com + 内置镜像 + config 镜像。
    用于校验镜像缓存文件未被篡改为任意 URL(防引导下载恶意包)。"""
    hosts = {"github.com"}
    for m in DEFAULT_MIRRORS + _config_update_mirrors():
        try:
            hosts.add(urlparse(m).netloc)
        except Exception:
            pass
    return hosts


def _read_mirror_cache() -> str | None:
    """读取上次成功下载源 URL(host 不在白名单则忽略,防止缓存被改写)"""
    try:
        if not MIRROR_CACHE_FILE.exists():
            return None
        url = str(json.loads(MIRROR_CACHE_FILE.read_text(encoding="utf-8")).get("url", "")).strip()
        if url and urlparse(url).netloc in _allowed_download_hosts():
            return url
    except Exception:
        pass
    return None


def _save_mirror_cache(url: str) -> None:
    """记录最近一次成功下载的源 URL(下次优先尝试,直连/镜像通用)"""
    try:
        MIRROR_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        MIRROR_CACHE_FILE.write_text(
            json.dumps({"url": url, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False),
            encoding="utf-8",
        )
        try:
            os.chmod(MIRROR_CACHE_FILE, 0o600)
        except Exception:
            pass
    except Exception:
        pass


def _download_candidates(branch: str) -> list:
    """构造候选下载源列表(去重保序):缓存源 → GitHub 直连 → 国内加速镜像"""
    direct = _zip_url(branch)
    urls = []
    cache = _read_mirror_cache()
    if cache and cache != direct:
        urls.append(cache)
    urls.append(direct)
    seen = set(urls)
    for m in DEFAULT_MIRRORS + _config_update_mirrors():
        u = f"{m.rstrip('/')}/{direct}"
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _version_tuple(v: str) -> tuple:
    """版本字符串 -> 可比较元组(忽略非数字段)"""
    return tuple(int(x) for x in re.split(r"[.\-]", str(v)) if x.isdigit())


def _is_downgrade(local_ver: dict, remote_ver: dict) -> bool:
    """本地版本高于远程版本(可能选错通道/降级)"""
    return _version_tuple(local_ver.get("version", "0")) > _version_tuple(remote_ver.get("version", "0"))


def _preview_member_ids() -> list:
    """体验通道白名单(作者控制): 仅从专家包根目录 config.json 读取。
    不读取环境变量作为授权依据(用户可自设环境变量绕过)。"""
    ids = _config_field("preview_member_ids", []) or []
    return [str(x) for x in ids]


def log(msg: str):
    print(msg, flush=True)


def get_current_user_id() -> str | None:
    """多来源获取当前 WorkBuddy 用户 userId"""
    for k in ("WORKBUDDY_USER_ID", "CODEBUDDY_USER_ID"):
        v = os.environ.get(k)
        if v:
            return v
    db = Path.home() / ".workbuddy" / "workbuddy.db"
    if db.exists():
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            row = conn.execute(
                "SELECT user_id FROM sessions "
                "WHERE deleted_at IS NULL ORDER BY last_activity_at DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
    cp = Path.home() / ".workbuddy" / "connectors"
    if cp.is_dir():
        dirs = [d.name for d in cp.iterdir() if d.is_dir() and len(d.name) >= 16]
        if len(dirs) == 1:
            return dirs[0]
    return None


def get_local_version() -> dict:
    """读取本地已安装版本记录"""
    vf = get_expert_root() / VERSION_FILE
    if vf.exists():
        try:
            return json.loads(vf.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_local_branch(branch: str) -> None:
    """更新成功后, 将实际来源分支写回本地 .update-version.json 的 branch 字段"""
    vf = get_expert_root() / VERSION_FILE
    data = {}
    if vf.exists():
        try:
            data = json.loads(vf.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["branch"] = branch
    try:
        vf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def download_zip(dest: Path, branch: str = DEFAULT_BRANCH) -> Path:
    """按候选源顺序下载分支 zip,返回 zip 路径。任一源成功即返回。"""
    zip_path = dest / "update.zip"
    direct = _zip_url(branch)
    errors = []
    for url in _download_candidates(branch):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ai-collection-assistant-auto-update"})
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                with open(zip_path, "wb") as f:
                    shutil.copyfileobj(resp, f)
            with zipfile.ZipFile(zip_path) as zf:
                if zf.testzip() is not None:
                    raise RuntimeError("zip 完整性校验失败(文件损坏)")
            _save_mirror_cache(url)
            return zip_path
        except Exception as e:
            errors.append(f"{urlparse(url).netloc}->{type(e).__name__}")
    raise RuntimeError(
        f"{len(errors)} 个下载源均失败({'; '.join(errors[:3])})"
        f"{'...' if len(errors) > 3 else ''} — 请检查网络后重试"
    )


def fetch_remote_package(branch: str = DEFAULT_BRANCH) -> tuple:
    """下载并解压远程指定分支包,返回 (src_dir, remote_version_dict)"""
    tmp = Path(tempfile.mkdtemp(prefix="aca-update-"))
    try:
        zip_path = download_zip(tmp, branch)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        src_dir = next(p for p in tmp.iterdir() if p.is_dir())
        ver = {}
        vf = src_dir / VERSION_FILE
        if vf.exists():
            try:
                ver = json.loads(vf.read_text(encoding="utf-8"))
            except Exception:
                pass
        return src_dir, ver
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def apply_update(src_dir: Path) -> int:
    """用新包内容覆盖专家包。

    核心:逐文件复制覆盖(失败才计入致命失败);
    只做"覆盖+新增",永不删除本地文件——防止误删用户文件/技能目录。
    """
    root = get_expert_root(require_marker=True)
    fail_count = 0

    def is_excluded(rel: Path) -> bool:
        return any(part in EXCLUDE_NAMES for part in rel.parts)

    for rel in [p.relative_to(src_dir) for p in src_dir.rglob("*") if p.is_file()]:
        if is_excluded(rel):
            continue
        s, d = src_dir / rel, root / rel
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
        except Exception:
            fail_count += 1
    return fail_count


def refresh_local_registration() -> bool:
    """刷新本地 WorkBuddy 对专家包的注册信息。

    专家包文件由 WorkBuddy 会话启动时直接读取(无独立注册缓存),
    但 marketplace 的索引项(名称/描述)需与最新 plugin.json 保持同步,
    否则专家中心的展示信息会停留在旧版本。

    本函数:读取 plugin.json -> 同步 marketplace.json 中对应条目。
    """
    try:
        root = get_expert_root()
        # 定位 plugin.json（兼容两种目录名）
        pj_path = None
        for meta_dir in (".codebuddy-plugin", ".workbuddy-plugin"):
            cand = root / meta_dir / "plugin.json"
            if cand.exists():
                pj_path = cand
                break
        if not pj_path:
            return False
        plugin_data = json.loads(pj_path.read_text(encoding="utf-8"))

        marketplace_dir = get_marketplace_dir()
        if not marketplace_dir:
            return False
        manifest_path = marketplace_dir / ".codebuddy-plugin" / "marketplace.json"
        if not manifest_path.exists():
            return False

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plugins = manifest.get("plugins", [])
        source = f"./plugins/{root.name}"
        updated = False
        for p in plugins:
            if p.get("source") == source or p.get("name") == plugin_data.get("name"):
                new_desc = plugin_data.get("description", "")
                if p.get("description") != new_desc or p.get("name") != plugin_data.get("name"):
                    p["name"] = plugin_data.get("name", p.get("name"))
                    p["source"] = source
                    p["description"] = new_desc
                    updated = True
        if updated:
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        return True
    except Exception:
        return False


def _resolve_channel(uid: str) -> str:
    """解析更新通道: 默认 main(生产); --channel test 仅体验白名单用户可用。"""
    channel = "main"
    for i, a in enumerate(sys.argv[1:]):
        if a in ("--channel", "-c") and i + 2 < len(sys.argv):
            channel = sys.argv[i + 2].lower()
        elif a.startswith("--channel="):
            channel = a.split("=", 1)[1].lower()
    if channel not in ("main", "test"):
        raise RuntimeError(f"非法通道: {channel}(仅支持 main/test)")
    if channel == "test":
        if str(uid) in _preview_member_ids():
            return PREVIEW_BRANCH
        raise RuntimeError("体验通道未授权: 当前用户不在预览白名单(preview_member_ids), 仅可获取生产环境 main")
    return DEFAULT_BRANCH


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _build_changes_summary(
    old_agent: str, new_agent: str, old_readme: str, new_readme: str,
    old_ver: dict, new_ver: dict, max_lines: int = 40,
) -> str:
    """对比新旧指令文件,生成变更摘要块(更新后热加载指引)。"""
    if old_agent == new_agent:
        return ""
    old_lines = old_agent.splitlines()
    new_lines = new_agent.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=0))
    changes = []
    for l in diff:
        if l.startswith(("+++", "---", "@@", "\\ No newline")):
            continue
        if not (l.startswith("+") or l.startswith("-")):
            continue
        if l.strip() in ("+", "-"):
            continue
        changes.append(l)
    if not changes:
        return ""
    if len(changes) > max_lines:
        changes = changes[:max_lines] + [f"...(共 {len(changes)} 处变更,已截断,请读取最新 agent.md 全文)"]
    old_v = old_ver.get("version", "?")
    new_v = new_ver.get("version", "?")
    readme_note = " (README.md 也有更新)" if old_readme != new_readme else ""
    lines = [
        f"INSTRUCTION_UPDATED: 专家指令已更新 {old_v} -> {new_v}{readme_note}",
        f"当前会话请按最新 {AGENT_MD} 执行;完整指令新开会话生效",
        "DIFF_SUMMARY_START",
    ]
    lines.extend(changes)
    lines.append("DIFF_SUMMARY_END")
    return "\n".join(lines)


def cmd_check() -> int:
    uid = get_current_user_id()
    if not uid:
        log("NO_USER_ID")
        return 0
    if uid == AUTHOR_USER_ID:
        log("AUTHOR_MODE")
        return 0
    try:
        branch = _resolve_channel(uid)
    except RuntimeError as e:
        log(f"ERROR:{e}")
        return 1
    try:
        _, remote_ver = fetch_remote_package(branch)
    except Exception as e:
        log(f"ERROR:更新源均不可达({e})")
        return 1
    local_ver = get_local_version()
    if _is_downgrade(local_ver, remote_ver):
        log(f"LOCAL_NEWER: 本地版本({local_ver.get('version','?')})高于远程({remote_ver.get('version','?')}), 疑似更新通道不符, 不执行更新")
        return 0
    if local_ver.get("version") == remote_ver.get("version"):
        log("UP_TO_DATE")
    else:
        log(f"UPDATE_AVAILABLE: {local_ver.get('version','?')} -> {remote_ver.get('version','?')}")
    return 0


def cmd_update() -> int:
    uid = get_current_user_id()
    if not uid:
        log("NO_USER_ID")
        return 0
    if uid == AUTHOR_USER_ID:
        log("AUTHOR_MODE")
        return 0
    try:
        branch = _resolve_channel(uid)
    except RuntimeError as e:
        log(f"ERROR:{e}")
        return 1
    try:
        get_expert_root(require_marker=True)
    except Exception as e:
        log(f"ERROR:{e}")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="aca-dl-"))
    fail = 0
    try:
        src_dir, remote_ver = fetch_remote_package(branch)
        local_ver = get_local_version()
        if _is_downgrade(local_ver, remote_ver):
            log(f"LOCAL_NEWER: 本地版本({local_ver.get('version','?')})高于远程({remote_ver.get('version','?')}), 已拒绝降级更新(请确认更新通道)")
            return 0
        if local_ver.get("version") == remote_ver.get("version"):
            log("UP_TO_DATE")
            return 0

        root = get_expert_root()
        old_agent = _read_file(root / AGENT_MD)
        old_readme = _read_file(root / "README.md")

        fail = apply_update(src_dir)

        if fail == 0:
            _write_local_branch(branch)
            # 刷新本地注册信息(同步 marketplace 索引)
            refreshed = refresh_local_registration()
            new_agent = _read_file(root / AGENT_MD)
            new_readme = _read_file(root / "README.md")
            summary = _build_changes_summary(
                old_agent, new_agent, old_readme, new_readme, local_ver, remote_ver
            )
            if summary:
                log(summary)
            log(f"LOCAL_REGISTRATION: {'已刷新' if refreshed else '刷新跳过(索引已同步或不可写)'}")
    except Exception as e:
        log(f"ERROR:更新失败({e})")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fail:
        log(f"ERROR:部分文件被占用({fail} 个),请关闭其他 WorkBuddy 窗口后重试更新")
        return 1
    log("UPDATED")
    return 0


def cmd_refresh() -> int:
    """仅刷新本地注册信息(不下载)。用于指令/展示信息变更后的手动同步。"""
    try:
        get_expert_root(require_marker=True)
    except Exception as e:
        log(f"ERROR:{e}")
        return 1
    ok = refresh_local_registration()
    log("REFRESHED" if ok else "ERROR:注册信息刷新失败(索引不存在或不可写)")
    return 0 if ok else 1


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    if action == "check":
        sys.exit(cmd_check())
    elif action == "update":
        sys.exit(cmd_update())
    elif action == "refresh":
        sys.exit(cmd_refresh())
    else:
        log("用法: python3 auto_update.py [check|update|refresh] [--channel main|test]")
        sys.exit(2)
