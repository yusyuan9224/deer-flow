# RFC-001: DeerFlow 基础开源认证模块与用户设计

- **状态 (Status)**: Proposed
- **目标受众 (Audience)**: DeerFlow 核心开发团队、开源社区贡献者
- **核心原则 (TL;DR)**: 采用"核心极简，接口开放"的原则。内置极简的单表 JWT 本地认证以保障开源项目的"开箱即用"，同时通过标准的工厂模式为社区预留 OIDC/OAuth 扩展点。废弃复杂的 Refresh Token 轮换，改用原生 LangGraph Checkpoint Metadata 实现线程级别的租户隔离。
---

## 一、 背景与设计哲学 (Background & Philosophy)

**DeerFlow 2.0** 已经从一个单轮深度研究脚本，演进为一个支持多智能体协同、沙盒文件操作和长期记忆的超级智能体平台。在这个有状态、长生命周期的系统中，引入身份验证模块以隔离用户状态（如本地运行时的不同项目工作区、沙盒挂载卷）是必不可少的。

本 RFC 确立了**"核心极简，接口开放"**的设计原则：初始版本仅提供最轻量级的单表结构和 JWT 令牌，保证通过 `make config` 快速拉起；同时，在系统架构（如拦截器、策略工厂）上预留标准化的钩子（Hooks），将企业级的 OIDC、SAML 等多端登录功能作为插件化模块，交由开源社区去逐步贡献和完善。

## 二、 核心依赖策略 (Dependencies)

为了保持架构依赖的简单和清晰，我们拒绝引入重量级的独立身份代理（如 Keycloak），完全依赖 FastAPI 原生的能力进行构建。在 pyproject.toml 中，仅引入维持系统运转的最少依赖包：
- passlib[bcrypt]：用于对本地用户的密码进行安全的加盐哈希处理，这是任何身份系统的底线。
- pyjwt：用于实现无状态 JSON Web Tokens (JWT) 的签发与校验。
- python-multipart：用于支持 FastAPI 原生的 OAuth2 密码流表单提交。
扩展预留：对于处理 OAuth 或 OIDC 复杂加密流程所需的 `authlib` 库，我们将不在基础版本中默认安装，而是将其声明在 `[project.optional-dependencies]` 中，供未来社区实现插件时按需引入（如 `uv pip install deer-flow[oidc]`）。

## 三、 身份验证策略：预留扩展的提供者工厂模式 (Provider Factory)

为了确保代码的干净并为未来的第三方登录做好准备，我们在核心层采用"策略模式"（Strategy Pattern）。
系统定义一个抽象基类 `AuthProvider`，声明标准化接口：

```python
class AuthProvider(ABC):
    @abstractmethod
    async def authenticate(self, credentials: dict) -> User:
        pass
```

1.    初始内置实现：`LocalAuthProvider`。仅实现基于本地数据库的邮箱/用户名与密码比对。
1. 社区贡献预留点：系统提供一个注册表工厂（Provider Factory）。未来，任何开源贡献者如果想为 DeerFlow 增加 GitHub 或企业 OIDC 登录，只需新建一个继承自 `AuthProvider` 的类（例如 `OIDCProvider`），实现标准的 Auth 流程，并向工厂注册即可，无需修改现有的任何核心路由逻辑。
### 四、 极简多租户数据库 Schema 设计 (Database Schema)

在数据库设计上，我们回归到最简单的关系模型。底层默认使用 SQLite（适合本地单机），同时向上兼容 PostgreSQL。
####  1. 规范化用户表 (users)
这是第一阶段唯一需要的身份认证表。

| 字段名称 | 数据类型 | 约束与索引 | 字段说明与预留逻 |
|----------|----------|------------|------------------|
| `id` | UUID | Primary Key | UUID 确保在未来升级多租户时的兼容性。 |
| `email` | String(255) | Unique | 用户的邮箱，作为本地登录账号。 |
| `password_hash` | String(255) | Nullable | 本地密码哈希。预留：设为可空（Nullable），是为了未来 OIDC 用户仅通过外部身份验证时，无需强制设置本地密码。 |
| `system_role` | String(50) | Default 'user' | 简单的角色控制（如 admin/user）。 |
| `created_at` | Timestamp | Not Null | 审计时间戳。 |

#### 2. 第三方凭证解耦机制（Credentials）
对于智能体需要访问外部资源（如用户的私有 GitHub 仓库）的场景，我们不将外部 API Token 与登录身份（Identity）强行绑定。这些外部 Key 将被视为智能体的"工具凭证（Credentials）"，存在一个专门的加密凭证表中，从而极大地简化了用户登录模块的复杂度。
### 五、 令牌管理：标准无状态 JWT (Token Management)
考虑到大部分开源部署位于受信任的本地网络或具有前端反向代理的环境中，引入"复用检测熔断"的长效刷新令牌（RTR）属于过度设计。
#### 精简版方案：
- 单一长效 JWT：登录成功后，FastAPI 仅签发一个带有较长有效期（如 7 天）的无状态 JWT。
- 存储与传递：前端（Next.js）获取到该 JWT 后，将其存储在 `HttpOnly Cookie` 中，并在每次请求 FastAPI 时由浏览器自动附带。
- 优势：服务端不需要任何数据库 I/O 即可校验用户身份，彻底省去了维护 `sessions` 状态表的烦恼。

### 六、 基于 FastAPI 依赖注入的权限控制 (FastAPI Auth Routing)
得益于 FastAPI 强大的依赖注入（Dependency Injection）系统，我们不需要编写复杂的全局中间件。系统只需提供一个核心依赖函数 `get_current_user`:
```python
from fastapi import Depends, HTTPException, Request
import jwt

async def get_current_user(request: Request):
    # 从 HttpOnly Cookie 中提取 token
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # 极简校验逻辑：仅使用 CPU 解码并验证 JWT 签名及过期时间
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401)
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

任何需要保护的智能体执行路由，只需将其注入即可：
```python
@router.post("/execute_agent")
async def execute(payload: TaskPayload, user_id: str = Depends(get_current_user)):
    pass
```


### 七、 智能体运行时的状态隔离：基于 LangGraph Metadata (LangGraph State Isolation)
为了防止多用户环境下的数据越权访问（即用户 A 读取到用户 B 的超级智能体执行轨迹），底层状态图（StateGraph）的隔离必须得到严格保障。我们全面拥抱 LangGraph 原生支持的 `metadata` 隔离方案。
1. 注入用户标识到 Metadata：当 API 接收到受保护的请求并准备创建或恢复一个线程（Thread）时，将从 JWT 解析出的用户标识注入到配置的 `metadata` 字典中（例如 `{"user_id": current_user.id}`）。
1. 基于 Metadata 的安全检索与过滤：当需要向前端返回历史对话列表时，后端调用 Checkpointer 原生的搜索和列表方法（例如 `PostgresSaver.list()`），并传入包含该用户的 `metadata` 过滤器参数（例如 `filter={"user_id": current_user.id}`）。
### 八、 前后端集成的轻量化范式与交互逻辑 (Frontend Integration)
#### 1. 架构决策：为何由 FastAPI 处理 OAuth 而非 Next.js？
为了彻底贯彻 `API-First` 的原则并避免前端与后端之间的状态同步地狱，本方案明确将 OAuth 及 OIDC 的核心处理逻辑完全放置在 FastAPI 后端：
- 多端支持能力：DeerFlow 作为智能体引擎，未来必然接入 Python SDK 或 CLI。将鉴权收敛在 FastAPI，可保证所有客户端的认证入口与核心逻辑绝对一致。
- 避免状态同步地狱：若在 Next.js 层处理 OAuth（如使用 NextAuth 产生 JWE 加密的 Session），FastAPI 端解密与状态同步将异常繁琐。
- 极致的安全性：FastAPI 直接与第三方 IdP 交换受保护的 Client Secret，并通过 `HttpOnly Cookie` 下发会话凭证，Next.js 仅作为纯粹的 UI 渲染层，杜绝了前端 XSS 窃取敏感 Token 的可能性。

#### 2. 登录与登出交互时序图
以下是系统（含未来预留的第三方 OAuth 登录）的标准交互时序设计：

```
sequenceDiagram
    participant U as User (浏览器)
    participant FE as Next.js (前端应用)
    participant BE as FastAPI (后端接口)
    participant IdP as OAuth 提供商 (如 GitHub)

    Note over U,BE: ============ 本地账号密码登录流程 ============

    U->>FE: 填写邮箱和密码，点击"登录"
    FE->>BE: POST /api/v1/auth/login/local (username, password)
    BE->>BE: 查询 users 表验证邮箱和密码哈希
    alt 验证成功
        BE->>BE: 签发系统长效 JWT (7 days)
        BE-->>FE: 返回 200 OK
        Note right of BE: Set-Cookie: access_token=JWT, HttpOnly, Secure
        FE->>FE: 存储登录状态
        FE->>U: 重定向至 /workspace 页面
    else 验证失败
        BE-->>FE: 返回 400 Bad Request
        FE-->>U: 显示错误提示信息
    end

    Note over U,IdP: ============ OIDC / OAuth 2.0 登录流程 ============

    U->>FE: 点击 "使用 GitHub 登录" 按钮
    FE->>U: 触发页面重定向
    U->>BE: 发起请求: GET /api/v1/auth/oauth/github
    BE->>BE: 生成随机 State (防 CSRF) 和 PKCE 挑战码
    BE->>U: 302 重定向至 GitHub 授权页面

    U->>IdP: 用户在 GitHub 登录并点击"授权"
    IdP->>U: 302 重定向回后端回调地址
    Note right of IdP: 携带 Authorization Code 和 State

    U->>BE: GET /api/v1/auth/callback/github?code=xxx&state=yyy
    BE->>BE: 校验 State 匹配，防止 CSRF 攻击
    BE->>IdP: 使用 Code + Client Secret 换取 Access Token
    IdP-->>BE: 返回 OAuth Access Token (及 ID Token)

    BE->>IdP: 请求获取用户基本信息 (User Profile)
    IdP-->>BE: 返回邮箱、昵称、头像等

    BE->>BE: 在 users 表中查找邮箱，若不存在则注册
    BE->>BE: 签发系统内部的业务长效 JWT
    BE->>U: 302 重定向至前端 /workspace 页面
    Note right of BE: Set-Cookie: access_token=JWT, HttpOnly, Secure

    U->>FE: 成功进入工作区页面
    FE->>BE: GET /api/v1/auth/me (携带 HttpOnly Cookie)
    BE-->>FE: 返回当前登录用户的配置与基本数据 (JSON)
    FE-->>U: 渲染完整应用界面

    Note over U,IdP: ============ 标准登出流程 ============

    U->>FE: 用户在界面点击 "登出"
    FE->>BE: POST /api/v1/auth/logout (浏览器自动携带 Cookie)
    BE->>BE: 后台注销逻辑 (如需黑名单或清理特定状态)
    BE-->>FE: 返回 200 OK
    Note right of BE: Set-Cookie: access_token=, Max-Age=0
    FE->>FE: 清理前端本地内存状态 (Context/Zustand)
    FE->>U: 页面重定向至 /login 路由
```

#### 3. 核心示例外观层伪代码 (Pseudo-code for Review)
为方便开发团队评审，以下提供 FastAPI 后端路由映射与 Next.js 前端逻辑的核心伪代码，明确区分了"本地账号密码登录"与"第三方 OAuth 登录"两种场景。
##### 3.1 后端 API 实现 (FastAPI)
无论是本地登录还是 OAuth 登录，后端的最终目标都是验证身份，并向前端下发带有系统自有长效 JWT 的 `HttpOnly Cookie`。
```python
app/api/auth.py
from fastapi import APIRouter, Response, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from app.core.security import verify_password, create_jwt_token

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

==========================================
场景 1: 本地简单账号密码登录 (Local Login)
==========================================
@router.post("/login/local")
async def login_local(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends() # 接收前端传来的 username 和 password
):
    # 1. 数据库校验用户与密码
    user = await get_user_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    # 2. 签发系统自有长效 JWT (7 days)
    token = create_jwt_token(data={"sub": str(user.id)}, expires_delta=timedelta(days=7))

    # 3. 将 Token 写入 HttpOnly Cookie (前端 AJAX 请求会收到此头信息)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True, secure=True, samesite="lax", max_age=7 * 24 * 3600
    )
    return {"message": "Login successful", "user_id": str(user.id)}


==========================================
场景 2: 第三方 OAuth 登录 (OAuth Login)
==========================================
@router.get("/oauth/{provider}")
async def login_oauth(provider: str):
    # 1. 工厂模式获取对应 provider 的 authorize URL
    # 2. 生成防 CSRF 的 state 参数并缓存
    authorization_url = provider_factory.get(provider).get_auth_url()

    # 3. 302 重定向用户浏览器至 GitHub / Google
    return RedirectResponse(url=authorization_url)

@router.get("/callback/{provider}")
async def callback_oauth(provider: str, code: str, state: str, response: Response):
    # 1. 验证 state 防范 CSRF
    # 2. 与第三方 IdP 通信，拿 code 换取 user_profile
    auth_provider = provider_factory.get(provider)
    user_profile = await auth_provider.authenticate_by_code(code)

    # 3. 数据库检索或新建 User
    user = await get_or_create_user(email=user_profile.email)

    # 4. 签发系统自有长效 JWT (7 days)
    token = create_jwt_token(data={"sub": str(user.id)}, expires_delta=timedelta(days=7))

    # 5. 生成 302 重定向到前端 Workspace，同时写入 HttpOnly Cookie
    redirect_resp = RedirectResponse(url="http://localhost:3000/workspace")
    redirect_resp.set_cookie(
        key="access_token", value=token,
        httponly=True, secure=True, samesite="lax", max_age=7 * 24 * 3600
    )
    return redirect_resp


==========================================
统一登出接口
==========================================
@router.post("/logout")
async def logout(response: Response):
    # 登出仅需清除前端的 Cookie
    response.delete_cookie(key="access_token")
    return {"message": "Successfully logged out"}
```

#### 3.2 前端集成逻辑 (Next.js)
前端代码无需引入沉重的 Auth 库，主要负责触发路由以及拦截未授权的 401 状态。
##### 登录页面的触发逻辑 (Login Page Component)
```typescript
// src/app/login/page.tsx
'use client';
import { useState } from 'react';
import apiClient from '@/lib/api-client';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // 场景 1：处理本地账号密码登录
  const handleLocalLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // 发送表单数据至 FastAPI，由 FastAPI 将 HttpOnly Cookie 种入浏览器
      const formData = new URLSearchParams();
      formData.append('username', email);
      formData.append('password', password);

      await apiClient.post('/api/v1/auth/login/local', formData);

      // 登录成功后，手动跳转至工作区
      window.location.href = '/workspace';
    } catch (error) {
      console.error("Login failed", error);
    }
  };
  // 场景 2：处理 OAuth 登录 (非常简单，直接利用 <a> 标签跳转至后端)
  const handleOAuthLogin = (provider: string) => {
    // 浏览器直接跳转到 FastAPI 的 OAuth 入口，后续全由后端 302 接管
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/oauth/${provider}`;
  };

  return (
    <div>
      <form onSubmit={handleLocalLogin}>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button type="submit">本地登录 (Local Login)</button>
      </form>

      <hr />

      {/* OAuth 登录直接触发后端重定向 */}
      <button onClick={() => handleOAuthLogin('github')}>
        使用 GitHub 登录 (OAuth)
      </button>
    </div>
  );
}
```

#####   全局路由防护与异常拦截 (Middleware & Interceptor)
```typescript
// src/middleware.ts (Next.js 中间件实现路由保护)
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  // 提取 FastAPI 种下的 HttpOnly Cookie
  const token = request.cookies.get('access_token')?.value

  // 未登录拦截
  if (!token && request.nextUrl.pathname.startsWith('/workspace')) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/workspace/:path*'], // 仅拦截需要鉴权的路由
}
```

```javascript
// src/lib/api-client.ts (Axios 拦截器)
import axios from 'axios'

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
  withCredentials: true, // 核心：允许浏览器跨域发送 HttpOnly Cookie
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 极简容错处理：若长效 token 到期，FastAPI 抛出 401，则重定向要求重新登录
    if (error.response?.status === 401 && typeof window!== 'undefined') {
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
export default apiClient;
```

---

*文档来源: https://my.feishu.cn/wiki/KyU3wWQdgi6tKdkshkMcp4K2n3d*
