#!/usr/bin/env python3
"""
环境检测脚本 - 检测本机 AI 采集工具链环境状态
支持 Windows 与 macOS

用法:
    python env_check.py            # 完整检测
    python env_check.py --json     # 输出 JSON（供程序解析）
    python env_check.py --quick    # 跳过网络检测（快速模式）
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith('win')
IS_MACOS = sys.platform == 'darwin'


def run(cmd, timeout=10, shell=None):
    """安全执行命令，返回 (ok, output)。"""
    if shell is None:
        shell = IS_WINDOWS
    try:
        r = subprocess.run(
            cmd, capture_output=True, timeout=timeout,
            shell=shell, encoding='utf-8', errors='ignore'
        )
        out = (r.stdout or '').strip() or (r.stderr or '').strip()
        return r.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, 'TIMEOUT'
    except Exception as e:
        return False, str(e)


def probe_version(cmd, timeout=15):
    """探测命令版本号。Windows 上 npm/npx 等 .cmd 包装器需要 shell 执行。"""
    exe = shutil.which(cmd)
    if not exe:
        return None

    # Windows 上 .cmd/.bat 包装器必须通过 shell 执行
    if exe.lower().endswith(('.cmd', '.bat')):
        ok, out = run(f'"{exe}" --version', timeout=timeout, shell=True)
    else:
        ok, out = run([exe, '--version'], timeout=timeout, shell=False)

    if not ok:
        # 回退尝试 -v
        if exe.lower().endswith(('.cmd', '.bat')):
            ok, out = run(f'"{exe}" -v', timeout=timeout, shell=True)
        else:
            ok, out = run([exe, '-v'], timeout=timeout, shell=False)

    if not ok or not out or out == 'TIMEOUT':
        return 'unknown'
    return out.splitlines()[0].strip()


# ---------------------------------------------------------------- 系统信息

def check_system():
    info = {
        'os': platform.system(),
        'os_release': platform.release(),
        'os_version': platform.version(),
        'arch': platform.machine(),
        'python': platform.python_version(),
    }
    if IS_MACOS:
        ok, ver = run(['sw_vers', '-productVersion'], shell=False)
        if ok:
            info['macos_version'] = ver
    # Windows 上不调用 `ver`：其输出为 OEM 编码（GBK），
    # 在 UTF-8 环境下会乱码；platform 模块已提供 os_version。
    return info


# ---------------------------------------------------------------- 浏览器

CHROME_PATHS_WIN = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Google\Chrome\Application\chrome.exe'),
    os.path.join(os.environ.get('PROGRAMFILES', ''), r'Google\Chrome\Application\chrome.exe'),
    os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), r'Google\Chrome\Application\chrome.exe'),
]

EDGE_PATHS_WIN = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), r'Microsoft\Edge\Application\msedge.exe'),
]

CHROME_PATHS_MAC = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    os.path.expanduser('~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
]

EDGE_PATHS_MAC = [
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    os.path.expanduser('~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
]


def _version_from_dir(exe_path):
    """Windows 下从安装目录探测浏览器版本。

    Chrome/Edge 在 Windows 不支持 --version 输出（会返回乱码），
    但其安装目录下有以版本号命名的子目录，如 Application\\131.0.6778.86\\
    """
    try:
        app_dir = os.path.dirname(exe_path)
        if not os.path.isdir(app_dir):
            return None
        candidates = []
        for name in os.listdir(app_dir):
            parts = name.split('.')
            if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                candidates.append((tuple(int(p) for p in parts[:4] if p.isdigit()), name))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    except Exception:
        pass
    return None


def probe_browser(paths, name):
    """多路径探测浏览器，返回 (found, path, version)。"""
    for p in paths:
        if p and os.path.isfile(p):
            version = 'unknown'

            # Windows：优先从目录结构探测版本（--version 在 Windows 上不可用）
            if IS_WINDOWS:
                version = _version_from_dir(p) or 'unknown'
            else:
                try:
                    r = subprocess.run(
                        [p, '--version'], capture_output=True, timeout=10,
                        encoding='utf-8', errors='ignore'
                    )
                    raw = (r.stdout or '') or (r.stderr or '')
                    if raw:
                        raw = (raw.strip()
                               .replace('Google Chrome', '')
                               .replace('Microsoft Edge', '').strip())
                        version = raw.splitlines()[0].strip() or 'unknown'
                except Exception:
                    version = 'unknown'

            return True, p, version
    return False, None, None


def check_browsers():
    result = {}
    for name, win_paths, mac_paths in [
        ('chrome', CHROME_PATHS_WIN, CHROME_PATHS_MAC),
        ('edge', EDGE_PATHS_WIN, EDGE_PATHS_MAC),
    ]:
        paths = win_paths if IS_WINDOWS else mac_paths
        found, path, ver = probe_browser(paths, name)
        result[name] = {'found': found, 'path': path, 'version': ver}
    return result


# ---------------------------------------------------------------- 已装工具

def check_tools():
    tools = {}

    # 命令行工具：node / npm / claude / codex / git
    for cmd in ['node', 'npm', 'claude', 'codex', 'git']:
        exe = shutil.which(cmd)
        if exe:
            ver = probe_version(cmd)
            tools[cmd] = {'found': True, 'path': exe, 'version': ver}
        else:
            tools[cmd] = {'found': False, 'path': None, 'version': None}

    # cc-switch（桌面应用，多路径探测）
    cc_paths = []
    if IS_WINDOWS:
        local = os.environ.get('LOCALAPPDATA', '')
        appdata = os.environ.get('APPDATA', '')
        home = os.path.expanduser('~')
        cc_paths = [
            os.path.join(local, 'Programs', 'cc-switch', 'cc-switch.exe'),
            os.path.join(local, 'Programs', 'CC-Switch', 'CC-Switch.exe'),
            os.path.join(appdata, 'cc-switch'),
            os.path.join(home, '.cc-switch'),
        ]
        # Microsoft Store / 包管理器安装痕迹
        pkgs = os.path.join(local, 'Packages')
        if os.path.isdir(pkgs):
            for d in os.listdir(pkgs):
                if 'cc-switch' in d.lower() or 'ccswitch' in d.lower():
                    cc_paths.append(os.path.join(pkgs, d))
    else:
        home = os.path.expanduser('~')
        cc_paths = [
            '/Applications/cc-switch.app',
            '/Applications/CC Switch.app',
            os.path.join(home, 'Library', 'Application Support', 'cc-switch'),
            os.path.join(home, '.cc-switch'),
        ]

    cc_found = any(os.path.exists(p) for p in cc_paths)
    tools['cc-switch'] = {
        'found': cc_found,
        'path': next((p for p in cc_paths if os.path.exists(p)), None),
        'version': None,
    }

    # ChatGPT 桌面版
    chatgpt_paths = []
    if IS_WINDOWS:
        local = os.environ.get('LOCALAPPDATA', '')
        chatgpt_paths = [
            os.path.join(local, 'Programs', 'ChatGPT', 'ChatGPT.exe'),
            os.path.join(local, 'Programs', 'chatgpt', 'ChatGPT.exe'),
        ]
        pkgs = os.path.join(local, 'Packages')
        if os.path.isdir(pkgs):
            for d in os.listdir(pkgs):
                if 'openai' in d.lower() or 'chatgpt' in d.lower():
                    chatgpt_paths.append(os.path.join(pkgs, d))
    else:
        chatgpt_paths = [
            '/Applications/ChatGPT.app',
            os.path.expanduser('~/Applications/ChatGPT.app'),
        ]

    cg_found = any(os.path.exists(p) for p in chatgpt_paths)
    tools['chatgpt'] = {
        'found': cg_found,
        'path': next((p for p in chatgpt_paths if os.path.exists(p)), None),
        'version': None,
    }

    # WorkBuddy 用户配置目录（判断是否在用 WorkBuddy）
    wb_dir = Path(os.environ.get('WORKBUDDY_CONFIG_DIR') or os.path.expanduser('~/.workbuddy'))
    tools['workbuddy'] = {'found': wb_dir.exists(), 'path': str(wb_dir), 'version': None}

    return tools


# ---------------------------------------------------------------- 网络

NET_TARGETS = [
    ('chatgpt.com',    'https://chatgpt.com'),
    ('google.com',     'https://www.google.com'),
    ('api.openai.com', 'https://api.openai.com'),
    ('baidu.com',      'https://www.baidu.com'),
    ('npmjs.org',      'https://registry.npmjs.org'),
    ('npmmirror.com',  'https://registry.npmmirror.com'),
]

OVERSEAS = {'chatgpt.com', 'google.com', 'api.openai.com'}


def check_network(timeout=5):
    """实测网络连通性。超时=不通。返回每个目标的探测结果。"""
    results = {}
    for name, url in NET_TARGETS:
        # 使用 curl（跨平台可用性最好）
        cmd = ['curl', '-s', '-o', os.devnull, '-w', '%{http_code} %{time_total}',
               '--max-time', str(timeout), url]
        ok, out = run(cmd, timeout=timeout + 5, shell=False)
        if ok and out and not out.startswith('TIMEOUT'):
            parts = out.split()
            code = parts[0] if parts else '000'
            elapsed = parts[1] if len(parts) > 1 else '?'
            reachable = code not in ('000', '')
            results[name] = {
                'reachable': reachable,
                'http_code': code,
                'elapsed': elapsed,
                'overseas': name in OVERSEAS,
            }
        else:
            results[name] = {
                'reachable': False,
                'http_code': None,
                'elapsed': None,
                'overseas': name in OVERSEAS,
            }
    return results


# ---------------------------------------------------------------- 判定

def judge(sys_info, browsers, tools, net, skip_net=False):
    """根据检测结果给出路线推荐。"""
    reasons = []

    if skip_net or not net:
        overseas_ok = None
        reasons.append('未执行网络检测（快速模式），无法判定境外连通性')
    else:
        overseas_results = [v for k, v in net.items() if v.get('overseas')]
        overseas_ok = any(v.get('reachable') for v in overseas_results)
        domestic_results = [v for k, v in net.items() if not v.get('overseas')]
        domestic_ok = any(v.get('reachable') for v in domestic_results)

        if overseas_ok:
            reasons.append('检测到可访问境外站点')
        else:
            reasons.append('检测到无法访问境外站点（纯国内网络环境）')
        if not domestic_ok:
            reasons.append('⚠️ 境内站点也不通，请先排查基础网络问题')

    chrome_ok = browsers.get('chrome', {}).get('found')
    edge_ok = browsers.get('edge', {}).get('found')
    if not chrome_ok and not edge_ok:
        reasons.append('⚠️ 未检测到 Chrome 或 Edge，浏览器扩展无法安装')

    has_chatgpt = tools.get('chatgpt', {}).get('found')
    has_ccswitch = tools.get('cc-switch', {}).get('found')
    has_node = tools.get('node', {}).get('found')

    # 路线判定
    if skip_net or overseas_ok is None:
        route = 'UNKNOWN'
        route_name = '待定（需网络检测）'
    elif overseas_ok:
        route = 'A_OR_B'
        route_name = '路线 A 可用（需 ChatGPT 付费订阅）；路线 B 也始终可用'
    else:
        route = 'B'
        route_name = '路线 B（WorkBuddy 浏览器链路）'

    # 待办事项
    todos = []
    if not chrome_ok and not edge_ok:
        todos.append('安装 Chrome 或 Edge 浏览器')
    if route == 'B' or route == 'A_OR_B':
        todos.append('安装 WorkBuddy 浏览器扩展（设置 → 智能体 → 浏览器操控）')
    if route == 'A_OR_B' and not has_chatgpt:
        todos.append('安装 ChatGPT 桌面版（需付费订阅才能用 Computer Use）')
    if not has_ccswitch:
        todos.append('（可选）安装 cc-switch，用于命令行工具接入中转站')
    if not has_node:
        todos.append('（可选）安装 Node.js 22+，用于 Codex CLI / Claude Code')

    return {
        'route': route,
        'route_name': route_name,
        'reasons': reasons,
        'todos': todos,
        'overseas_ok': overseas_ok,
    }


# ---------------------------------------------------------------- 输出

def print_report(sys_info, browsers, tools, net, verdict, skip_net=False):
    line = '─' * 46
    print('\n📋 环境体检报告')
    print('═' * 48)

    print('\n【系统环境】')
    print(f"  操作系统：{sys_info['os']} {sys_info.get('os_release', '')} ({sys_info['arch']})")
    if sys_info.get('macos_version'):
        print(f"  macOS 版本：{sys_info['macos_version']}")
    print(f"  Python：{sys_info['python']}")

    print('\n【浏览器】')
    for name in ('chrome', 'edge'):
        b = browsers.get(name, {})
        mark = '✅' if b.get('found') else '❌'
        detail = f" {b['version']}" if b.get('version') else ''
        print(f"  {name.capitalize()}：{mark}{detail}")
        if b.get('path'):
            print(f"     路径：{b['path']}")

    print('\n【已装工具】')
    labels = {
        'node': 'Node.js', 'npm': 'npm', 'git': 'Git',
        'claude': 'Claude Code', 'codex': 'Codex CLI',
        'cc-switch': 'cc-switch', 'chatgpt': 'ChatGPT 桌面版',
        'workbuddy': 'WorkBuddy',
    }
    for key, label in labels.items():
        t = tools.get(key, {})
        mark = '✅' if t.get('found') else '❌'
        ver = f" {t['version']}" if t.get('version') else ''
        print(f"  {label}：{mark}{ver}")

    if not skip_net and net:
        print('\n【网络连通性】')
        for name, v in net.items():
            mark = '✅' if v.get('reachable') else '❌'
            tag = '（境外）' if v.get('overseas') else '（境内）'
            extra = f" HTTP {v['http_code']} {v['elapsed']}s" if v.get('reachable') else ' 超时/不可达'
            print(f"  {name}{tag}：{mark}{extra}")

    print('\n' + line)
    print(f"🎯 推荐方案：{verdict['route_name']}")
    print(line)
    if verdict['reasons']:
        print('\n判定理由：')
        for r in verdict['reasons']:
            print(f'  · {r}')
    if verdict['todos']:
        print('\n建议待办：')
        for i, t in enumerate(verdict['todos'], 1):
            print(f'  {i}. {t}')
    print('\n' + '═' * 48 + '\n')


def main():
    ap = argparse.ArgumentParser(description='AI 采集工具链环境检测')
    ap.add_argument('--json', action='store_true', help='输出 JSON')
    ap.add_argument('--quick', action='store_true', help='跳过网络检测')
    args = ap.parse_args()

    # Windows 控制台默认 GBK，中文输出会乱码，强制切 UTF-8
    if IS_WINDOWS:
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    sys_info = check_system()
    browsers = check_browsers()
    tools = check_tools()
    net = {} if args.quick else check_network()
    verdict = judge(sys_info, browsers, tools, net, skip_net=args.quick)

    if args.json:
        print(json.dumps({
            'system': sys_info,
            'browsers': browsers,
            'tools': tools,
            'network': net,
            'verdict': verdict,
        }, ensure_ascii=False, indent=2))
    else:
        print_report(sys_info, browsers, tools, net, verdict, skip_net=args.quick)


if __name__ == '__main__':
    main()
