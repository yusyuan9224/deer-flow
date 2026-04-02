# RFC: Next.js 前端接入 FastAPI 认证

## 1. 背景

当前 DeerFlow 的前端基于 Next.js App Router，主要业务页面位于 `/workspace` 下；业务数据接口主要由 FastAPI 提供。项目中存在未正式启用的 `better-auth` 相关代码，但它并不是当前业务接口的认证基础。

本 RFC 的目标是明确：

- Next.js 前端如何接入 FastAPI 提供的登录能力
- FastAPI 需要向前端暴露哪些认证接口
- Next.js 服务端与客户端如何分工
- 如何在不引入第二套认证体系的前提下完成安全接入

本 RFC **不讨论 FastAPI 内部如何签发 JWT、如何实现用户体系、如何实现权限系统**；只约束前后端之间的接口契约与前端接入方案。

---

## 2. 设计目标

### 2.1 目标

1. `/workspace` 及其子路由必须受保护
2. 认证判断以 FastAPI 为唯一真相源
3. Next.js 服务端完成首层守卫，避免页面闪烁
4. Next.js 客户端通过 Provider 消费已校验的用户信息
5. 业务请求统一携带认证信息
6. 会话失效、登出、未登录访问等行为统一
7. 认证方案满足基本 Web 安全要求，尤其是 JWT 暴露面控制与 CSRF 防护

### 2.2 非目标

本 RFC 不包含：

- JWT refresh 机制
- OAuth / 第三方登录
- RBAC / 细粒度权限设计
- FastAPI 内部登录、签名、存储、撤销实现

---

## 3. 已知前提与约束

### 3.1 已知前提

- Next.js frontend 与 FastAPI **同域**
- FastAPI 登录成功后向浏览器下发 **JWT**
- 业务接口主要已由 FastAPI 提供
- Next.js 使用 App Router
- 首版方案 **不提供 refresh JWT token 接口**

### 3.2 设计约束

- 不在前端 JavaScript 可访问的位置存储 JWT
- 不在客户端通过额外 `/api/auth/me` 请求完成首屏登录判断
- Next.js 服务端只负责校验与透传用户信息，不负责成为新的认证真相源
- 所有认证状态最终由 FastAPI 判断

---

## 4. 总体方案

## 4.1 核心原则

采用以下架构：

- **FastAPI**：唯一认证真相源
- **Next.js server**：受保护路由首层守卫
- **Next.js client**：消费 server 已校验的用户信息并维护前端展示态

换句话说：

1. 浏览器访问受保护页面
2. Next.js server 读取请求中的认证 cookie
3. Next.js server 调用 FastAPI 的认证校验接口
4. 若校验通过，则拿到 `user`
5. Next.js server 渲染页面，并通过 `AuthProvider` 将 `user` 注入客户端
6. 客户端直接消费 `initialUser`，**首屏不再额外请求一次 `/api/auth/me`**

---

## 4.2 推荐登录态载体

**推荐方案：JWT 通过 HttpOnly Cookie 传递。**

要求：

- `HttpOnly`
- `Secure`（生产环境）
- 配置合适的 `SameSite`
- Cookie 作用域仅限必要域名与路径

### 不推荐方案

以下做法不在本 RFC 接受范围内：

- localStorage 保存 JWT
- sessionStorage 保存 JWT
- 前端 JS 可读取的 cookie 保存 JWT
- 将 JWT 显式注入前端 state、HTML 或 hydration 数据

原因：这些方案会明显扩大 XSS 场景下的凭证泄露风险。

---

## 5. FastAPI 需要提供的接口契约

FastAPI 需要提供最小认证接口集合：

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

本 RFC **不需要** `refresh token` 或 `refresh JWT` 接口。

---

## 5.1 `POST /api/auth/login`

### 用途

提交登录凭证并建立认证态。

### 请求体

推荐格式：

```json
{
  "email": "user@example.com",
  "password": "******"
}
```

如业务侧采用用户名登录，也可为：

```json
{
  "username": "alice",
  "password": "******"
}
```

### 成功响应

- HTTP `200 OK` 或 `204 No Content`
- 通过 `Set-Cookie` 建立认证 cookie
- 可选返回当前用户信息

推荐返回：

```json
{
  "user": {
    "id": "u_123",
    "email": "user@example.com",
    "name": "Alice",
    "avatar_url": "https://...",
    "roles": ["user"]
  }
}
```

### 失败响应

推荐语义：

- `400 Bad Request`：参数缺失或格式错误
- `401 Unauthorized`：凭证错误
- `403 Forbidden`：账号禁用、冻结等

推荐错误结构：

```json
{
  "code": "INVALID_CREDENTIALS",
  "message": "Invalid email or password."
}
```

### 接口要求

- 登录成功后由 FastAPI 负责 `Set-Cookie`
- 前端不自行拼接或持久化 JWT
- 错误信息应稳定，便于前端展示
- 不应暴露过多认证细节，避免账号枚举

---

## 5.2 `POST /api/auth/logout`

### 用途

注销当前会话。

### 请求

无特殊 body 要求，认证信息通过 cookie 识别。

### 成功响应

- HTTP `200 OK` 或 `204 No Content`
- 清除认证 cookie

### 前端预期

前端调用成功后：

- 立即清空本地 `user` 状态
- 跳转到登录页

即使服务端当前已处于未登录状态，前端也可将其视为幂等成功。

---

## 5.3 `GET /api/auth/me`

### 用途

返回当前请求对应的已登录用户信息；未登录时返回 401。

这是本 RFC 中 **唯一用于判断当前请求是否已认证** 的标准接口。

### 成功响应

```json
{
  "user": {
    "id": "u_123",
    "email": "user@example.com",
    "name": "Alice",
    "avatar_url": "https://...",
    "roles": ["user"]
  }
}
```

### 未登录响应

- `401 Unauthorized`

### 接口要求

该接口必须满足：

1. **稳定**：作为守卫基础接口，返回结构不能频繁变化
2. **轻量**：不要返回不必要的大字段
3. **安全**：不返回 JWT、refresh token、会话票据等敏感凭证
4. **权威**：其返回结果代表当前请求的真实认证状态

---

## 6. Next.js 侧职责划分

## 6.1 服务端职责

Next.js server 负责：

- 保护 `/workspace` 及其子路由
- 从请求中读取 cookie
- 服务端调用 FastAPI `/api/auth/me`
- 基于校验结果决定继续渲染或重定向
- 将已校验的 `user` 作为 `initialUser` 注入前端 Provider

### 明确要求

Next.js server **不负责本地直接验证 JWT 是否有效**，而是：

- 读取请求 cookie
- 将当前请求上下文带给 FastAPI
- 由 FastAPI 返回当前用户或 401

这样可以保证认证逻辑统一，不会出现 Next.js 与 FastAPI 判断不一致的问题。

---

## 6.2 客户端职责

Next.js client 负责：

- 消费 `AuthProvider` 注入的用户信息
- 展示头像、用户名等 UI
- 在登录成功后更新用户态
- 在登出后清空用户态
- 在业务请求遇到 401 时清空用户态并跳转登录页

### 明确要求

客户端首屏 **不需要主动再请求一次** `/api/auth/me`。

原因：

- 服务端在守卫阶段已完成认证判断
- 服务端已拿到 `user`
- `user` 可以直接注入 `AuthProvider`
- 客户端再请求一次只会引入额外网络开销和潜在闪烁

---

## 7. 路由守卫设计

## 7.1 守卫位置

推荐在受保护路由组的 server layout 中完成守卫，例如：

- `/workspace` 路由组 layout

### 守卫流程

1. 用户访问 `/workspace` 或其子路由
2. Next.js server 读取当前请求中的 cookie
3. Next.js server 请求 FastAPI `GET /api/auth/me`
4. FastAPI 返回：
   - `200 + user`：允许继续渲染
   - `401`：重定向到 `/login?next=当前路径`
5. 校验通过时，Next.js server 将 `user` 传入 `AuthProvider`

---

## 7.2 不采用客户端首层守卫的原因

不推荐用客户端首屏调用 `/api/auth/me` 再跳转登录页，原因包括：

- 会先渲染页面再跳转，造成闪烁
- 会产生多一次首屏请求
- 受保护内容可能在极短时间内被渲染
- 与 App Router 的 server-side guard 方式不一致

因此：

**首层守卫必须在 Next.js server 完成。**

---

## 8. Provider 设计

## 8.1 设计要求

前端需要一个统一的认证 Provider，例如：

- `AuthProvider`
- `useAuth()`

它负责向客户端组件暴露：

- `user`
- `isAuthenticated`
- `logout()`
- `setUser()` 或等价更新能力

### 推荐输入

`AuthProvider` 接收来自 Next.js server 的：

- `initialUser: User | null`

### 推荐行为

- `initialUser !== null` 时，视为已登录
- 首屏不自动触发 `/api/auth/me`
- 登录成功后，显式写入新的用户信息
- 登出后，清空用户信息
- 任意业务请求遇到 401 时，清空用户信息并跳转登录页

---

## 8.2 安全边界

Provider 中只允许出现 **用户信息**，不允许出现：

- 原始 JWT
- refresh token
- cookie 内容
- 任何需要前端持久化的认证凭证

Provider 只承担“前端展示态”的职责，不承担“凭证存储”的职责。

---

## 9. 统一请求层要求

当前前端业务代码中存在多处直接 `fetch` FastAPI 的模式。接入认证后，必须统一请求行为。

## 9.1 显式携带凭证

所有调用 FastAPI 的请求都应显式设置：

```ts
credentials: "include"
```

即使当前为同域环境，也推荐显式写明，确保行为稳定、可读、可维护。

---

## 9.2 统一 401 处理

当任一业务请求返回 `401` 时，前端必须执行统一逻辑：

1. 清空 `AuthProvider` 中的用户状态
2. 中断当前业务流程
3. 跳转到 `/login?next=当前路径`

### 目的

避免出现以下不一致行为：

- 某些页面默默失败
- 某些页面仍显示旧用户信息
- 某些页面卡死在 loading
- 某些页面继续允许操作但实际请求都失败

---

## 9.3 统一错误结构

建议封装统一 fetcher，对外暴露标准化结果：

- 自动带上 `credentials: "include"`
- 统一解析错误结构
- 对 `401` 进行统一处理
- 减少页面和业务模块中的重复判断逻辑

---

## 10. 登录页要求

## 10.1 页面职责

登录页负责：

- 收集账号与密码
- 调用 `POST /api/auth/login`
- 登录成功后跳转到 `next` 指定路径或默认工作区
- 登录失败时显示错误提示

## 10.2 跳转规则

若存在合法 `next` 参数，则登录成功后跳转至该路径；否则跳转至默认首页，如 `/workspace`。

### 安全要求

`next` 参数必须限制为站内相对路径。

不得允许：

- `https://evil.com`
- `//evil.com`
- 各种协议绕过形式

原因：避免开放重定向（open redirect）风险。

---

## 11. 登出要求

登出流程如下：

1. 调用 `POST /api/auth/logout`
2. 前端立即清空 `AuthProvider` 中的 `user`
3. 跳转到 `/login`

### 说明

首版无需等待重新拉取 `/api/auth/me` 来确认登出是否成功；以本地状态清空为准，页面不应继续停留在登录态 UI。

---

## 12. 安全要求

这是本 RFC 的核心部分。

## 12.1 JWT 不得暴露给前端 JavaScript

JWT 必须通过 HttpOnly Cookie 传递，不得由前端 JS 直接读取。

### 不允许的行为

- 把 JWT 放进 localStorage
- 把 JWT 放进 sessionStorage
- 把 JWT 放进可读 cookie
- 把 JWT 放进 React state / context / props
- 把 JWT 放入 HTML、SSR 注水数据或日志

### 原因

一旦发生 XSS，任何 JS 可访问的 JWT 都可能被直接窃取并用于会话冒用。

---

## 12.2 Next.js server 可以读取 cookie，但不得透传敏感凭证

Next.js server 作为受信任后端，可以读取请求中的 cookie 以完成守卫。但它不得：

- 把 JWT 作为 props 传给客户端组件
- 把 JWT 写入页面 HTML
- 把 JWT 写入可观测日志
- 把 JWT 发送到第三方服务

Next.js server 向客户端暴露的只能是：

- 用户基础资料
- 权限角色等非敏感展示信息

---

## 12.3 认证判断必须以 FastAPI 为准

Next.js server **不得因为能读到 JWT 就直接认定用户已登录**。

推荐方式始终是：

1. 读取 cookie
2. 请求 `GET /api/auth/me`
3. 由 FastAPI 决定该请求是否已认证

### 原因

即使 JWT 签名看起来有效，FastAPI 仍可能基于以下条件拒绝该会话：

- token 已过期
- 用户已被禁用
- token 已被撤销
- 账号处于安全冻结状态
- 服务器端策略已使旧 token 失效

如果 Next.js 自行判断，就会与后端真实状态产生偏差。

---

## 12.4 必须考虑 CSRF

由于认证依赖 cookie 自动携带，因此必须考虑跨站请求伪造（CSRF）。

### 风险范围

所有会改变状态的接口都应纳入防护范围，例如：

- 登出
- 创建/删除线程
- 发送消息
- 上传文件
- 修改配置
- 安装技能
- 修改记忆、MCP、agents 等资源

### FastAPI 需要具备的能力

FastAPI 至少应提供下列一种或多种防护策略：

1. 合理配置 `SameSite=Lax` 或更严格策略
2. 对敏感写操作校验 `Origin` / `Referer`
3. 引入 CSRF token 机制
4. 对高风险接口采用组合校验

### 对前端的影响

若后端采用 CSRF token 方案，则前端请求层必须支持：

- 获取 CSRF token
- 在写请求中以 header 等方式携带
- 与统一 fetcher 集成

### 结论

即使同域，也不能忽略 CSRF。

---

## 12.5 防止开放重定向

登录成功后的跳转逻辑若允许直接消费 `next` 参数，必须严格限制其范围。

### 只允许

- 站内相对路径，如 `/workspace`
- 明确受控的内部页面路径

### 禁止

- 外部绝对 URL
- 协议相对路径
- 含协议绕过或编码绕过的非法跳转目标

---

## 12.6 登录错误信息不得泄露过多细节

推荐将“用户名不存在”和“密码错误”统一为同一类提示，例如：

- `Invalid email or password.`

不建议前端根据后端返回信息做可区分的账号存在性提示。

目的：降低账号枚举风险。

---

## 12.7 401 行为必须一致

当会话失效后，前端所有页面必须进入一致状态：

- 清空当前用户
- 阻止继续使用需要登录的功能
- 引导重新登录

不得出现部分页面继续显示旧用户信息、部分页面报错、部分页面静默失败的情况。

---

## 13. 失败与异常场景

## 13.1 未登录访问受保护页面

- Next.js server 请求 `/api/auth/me`
- FastAPI 返回 `401`
- Next.js server 重定向到 `/login?next=原路径`

---

## 13.2 JWT 过期

- 受保护页面首屏访问：守卫失败，直接跳登录页
- 页面内后续请求：返回 `401`，前端清空用户态并跳登录页

首版不做 refresh，过期后统一重新登录。

---

## 13.3 FastAPI 暂时不可用

若 `/api/auth/me` 返回 `5xx` 或网络失败：

- 不应简单当作“未登录”处理
- 应区分“认证失败”和“服务不可用”
- 受保护页面可展示统一错误页或服务异常状态

原因：`401` 与 `5xx` 的处理语义不同。

---

## 13.4 客户端已有旧用户态但后续请求 401

说明服务端会话已失效或已被撤销。

前端应：

- 立即清空 Provider 中的 `user`
- 终止当前登录态行为
- 跳转登录页

不应继续依赖本地旧用户信息。

---

## 14. 与现有代码的关系

当前前端仓库中存在 `better-auth` 相关实现痕迹，但本 RFC 方案要求：

- FastAPI 为唯一认证真相源
- Next.js 不再依赖 `better-auth` 作为正式登录态方案
- 避免两套并行认证系统长期共存

原因：双套体系会带来以下问题：

- 用户态来源不一致
- 路由守卫标准不一致
- 调试成本高
- 安全边界不清晰

---

## 15. 实施要求（前端视角）

## 15.1 必做项

1. 新增前端 `auth` 模块
2. 新增 `/login` 页面
3. 在 `/workspace` 路由组 server layout 中加入守卫
4. 通过 server 侧 `/api/auth/me` 校验后将 `user` 注入 `AuthProvider`
5. 客户端首屏不再额外请求 `/api/auth/me`
6. 统一请求层显式带 `credentials: "include"`
7. 统一处理 `401`
8. 停用或迁移现有 `better-auth` 入口

---

## 15.2 可后续演进项

1. 更细粒度的权限控制
2. 全站级别登录态感知（不只 `/workspace`）
3. 会话管理页面
4. 安全审计与登录历史展示

这些不属于本 RFC 首版范围。

---

## 16. 最终结论

本 RFC 确定如下方案：

- FastAPI 作为唯一认证真相源
- JWT 通过 HttpOnly Cookie 传递
- FastAPI 仅需提供：
  - `POST /api/auth/login`
  - `POST /api/auth/logout`
  - `GET /api/auth/me`
- 首版不提供 refresh token / refresh JWT 接口
- Next.js server 负责 `/workspace` 及其子路由的首层守卫
- Next.js server 通过调用 FastAPI `/api/auth/me` 获取当前用户
- 守卫成功后，直接将 `user` 通过 `AuthProvider` 提供给客户端
- 客户端首屏不再额外请求 `/api/auth/me`
- 客户端只持有 `user` 等展示信息，不持有 JWT
- 所有业务请求统一携带 cookie，并统一处理 `401`
- 安全重点为：JWT 不暴露给前端 JS、认证判断统一由 FastAPI 决定、CSRF 防护、防开放重定向、统一会话失效处理

这是当前同域架构下，最简洁、最一致、也最安全的 Next.js 前端接入方案。
