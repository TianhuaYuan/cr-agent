# cr-agent Railway 部署指南

## 快速开始（5 分钟）

### 1. 注册 Railway 账号

访问 https://railway.app/，用 GitHub 账号登录。

### 2. 创建项目

```bash
# 安装 Railway CLI
npm install -g @railway/cli

# 登录
railway login

# 在项目目录初始化
railway init
```

### 3. 配置环境变量

在 Railway Dashboard → Variables 中设置：

| 变量 | 说明 | 示例 |
|------|------|------|
| `CR_AGENT_CHAT_API_KEY` | LLM API key | `sk-xxx` |
| `CR_AGENT_CHAT_BASE_URL` | LLM API 地址 | `https://api.openai.com/v1` |
| `CR_AGENT_CHAT_MODEL` | 默认模型 | `gpt-4o-mini` |
| `CR_AGENT_JWT_SECRET` | JWT 签名密钥 | `openssl rand -hex 32` |
| `CR_AGENT_API_KEY` | 管理 API key | 自定义强密码 |
| `CR_AGENT_API_AUTH_REQUIRED` | 是否启用鉴权 | `True` |
| `CR_AGENT_DATABASE_URL` | 数据库 URL | Railway Postgres 自动生成 |

### 4. 生成 JWT_SECRET

```bash
# macOS / Linux
openssl rand -hex 32

# Windows (PowerShell)
-join ((1..32) | ForEach-Object { "{0:X2}" -f (Get-Random -Max 256) })
```

### 5. 添加 PostgreSQL 数据库

Railway Dashboard → New → Database → Add PostgreSQL

Railway 会自动注入 `DATABASE_URL` 环境变量，无需手动配置。

### 6. 部署

```bash
railway up
```

部署成功后 Railway 会提供公网 URL。

### 7. 获取访问 token

```bash
# 调用 /auth/token 获取 JWT
curl -X POST https://your-app.railway.app/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key": "your-admin-api-key"}'
```

返回：
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 8. 前端配置 token

打开前端页面 → 顶部输入 API key → 点击"获取 Token"→ 自动保存到 localStorage。

所有后续请求自动携带 Bearer token。

## 首次启动流程

1. 部署成功后访问公网 URL
2. 前端弹出 token 输入框（或手动点击顶部"设置 Token"）
3. 输入 admin API key → 获取 token
4. 开始代码审查

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 502 Bad Gateway | 容器启动失败 | 查看 Railway Logs |
| 401 Unauthorized | token 无效或过期 | 重新获取 token |
| 数据库连接失败 | DATABASE_URL 未配置 | 检查环境变量 |
| LLM 调用超时 | 代码太长或网络慢 | 调大 LLM_TIMEOUT |

## 安全建议

1. **JWT_SECRET**：至少 32 字节随机字符串，不要硬编码
2. **API_KEY**：使用强密码，不要泄露
3. **API_AUTH_REQUIRED**：生产必须设为 `True`
4. **GITHUB_WEBHOOK_SECRET**：如果使用 Webhook，必须配置
