# 项目1 使用文档

## 1. 项目内容

`项目1` 是客服对话 MVP，包含：

- 后端包：`backend/`
- FastAPI 路由层：`backend/app/api/v1/customer_service.py`
- 核心服务层：`backend/app/services/customer_service.py`
- 人工转接状态机：`ai_active -> handoff_requested -> human_active -> human_closed`
- AI 空闲关闭：超过 60 秒无新消息的 `ai_active` 变为 `auto_closed`
- Vue 客户聊天端：`frontend/src/views/CustomerChatView.vue`
- Vue 人工客服工作台：`frontend/src/views/HumanSupportDeskView.vue`

项目不包含真实商品、订单、政策系统；对话中出现相关词汇时，只作为普通文本或知识库资料内容处理。

PostgreSQL + pgvector、资料上传、`knowledge_chunks` 向量表、LLM/Embedding base URL 和 API key 配置入口已经用于当前 AI 客服知识库。

## 2. 环境准备

```powershell
cd C:\Users\36183\Desktop\working\demo1\backend
uv sync
```

## 3. 运行测试

```powershell
cd C:\Users\36183\Desktop\working\demo1\backend
uv run python -m unittest discover -s tests -v
```

AI 知识库、资料上传、混合检索和提示词防护的详细技术说明见：

```text
C:\Users\36183\Desktop\working\demo1\docs\ai_knowledge_base.md
C:\Users\36183\Desktop\working\demo1\docs\technical_guide.md
```

## 4. 查看当前数据摘要

```powershell
cd C:\Users\36183\Desktop\working\demo1\backend
uv run python scripts/seed_demo_data.py
```

预期包含对话和知识库相关计数：

- `conversations`
- `messages`
- `handoff_tickets`
- `corrections`
- `ai_call_logs`
- `knowledge_documents`
- `knowledge_chunks`

## 5. 运行本地演示脚本

```powershell
cd C:\Users\36183\Desktop\working\demo1\backend
uv run python scripts/run_demo.py
```

脚本会依次演示：

1. 普通 AI 客服回复。
2. 用户显式转人工。
3. 后台接入工单。
4. 人工回复。
5. 人工纠错沉淀。
6. 人工主动结束服务。

## 6. 启动 API

```powershell
cd C:\Users\36183\Desktop\working\demo1\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

注意：后端只需要启动一次。如果你前面已经开过一个 `uvicorn`，先关掉旧进程，再开新进程，避免同一个项目同时跑两个后端实例。

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

普通聊天：

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/customer-service/chat `
  -H "Content-Type: application/json" `
  -d "{\"customer_id\":\"customer-001\",\"content\":\"你好，我想咨询一下\"}"
```

显式转人工：

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/customer-service/chat `
  -H "Content-Type: application/json" `
  -d "{\"customer_id\":\"customer-002\",\"content\":\"我要转人工，人工处理\"}"
```

## 7. 启动 Vue 前端

客户聊天端：

```powershell
cd C:\Users\36183\Desktop\working\demo1\frontend
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173
```

人工客服工作台：

```powershell
cd C:\Users\36183\Desktop\working\demo1\frontend
npm run dev:support
```

浏览器打开：

```text
http://127.0.0.1:5174
```

推荐演示路径：

1. 打开客户聊天端，发送一条普通咨询。
2. 客户点击“转人工”。
3. 打开人工客服工作台，刷新队列并接入该工单。
4. 客服发送人工回复。
5. 回到客户聊天端，消息会通过 WebSocket 自动出现，不需要手动刷新。
6. 客服在工作台点击“结束服务”。

## 8. PostgreSQL 与 Redis

项目支持两种 repository：

- 默认 `REPOSITORY_BACKEND=memory`：使用内存仓库，适合快速测试和无数据库演示。
- `REPOSITORY_BACKEND=postgres`：使用 SQLAlchemy repository，会话、消息、工单、纠错和 AI 日志会写入 PostgreSQL。

用 Docker Compose 启动带 pgvector 的 PostgreSQL 和 Redis：

```powershell
cd C:\Users\36183\Desktop\working\demo1\backend
docker compose up -d
```

如果要让后端使用 PostgreSQL，创建 `backend/.env`：

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ai_portfolio
REDIS_URL=redis://localhost:6379/0
REPOSITORY_BACKEND=postgres
PROJECT_ID=customer-service
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=local-dialog-summary
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
EMBEDDING_DIM=1536
```

启动 API 时会自动创建缺失的对话相关表、`knowledge_documents` 和 `knowledge_chunks`。Docker 首次初始化 PostgreSQL 数据卷时会执行 `infra/init.sql`，创建 `vector` 扩展。历史数据库里如果已经存在旧商品/订单/政策/评测表，当前代码不会再使用它们。
