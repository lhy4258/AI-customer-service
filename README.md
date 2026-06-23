# 项目1：客服对话

这是一个客服对话 MVP。项目不接入真实商品、订单、政策系统；即使用户在对话里提到商品或订单，系统也只把它当作聊天文本和知识库资料内容处理。

当前已接入 PostgreSQL + pgvector 知识库、资料上传、混合检索、LLM/Embedding 的 base URL 和 API key 配置入口；这些只服务 AI 客服资料检索，不代表恢复商品、订单或政策假数据。

当前保留的能力：

- 客户聊天端
- AI 知识库检索回复
- 显式转人工
- 人工客服工作台
- WebSocket 实时消息同步
- 会话消息记录
- 会话生命周期
- 空闲自动关闭
- 人工纠错记录
- AI 调用日志
- 可选 PostgreSQL 落库
- pgvector 向量库
- LLM/Embedding provider 配置

快速入口：

- 架构设计：`docs/architecture.md`
- 使用文档：`docs/usage.md`
- AI 知识库与混合检索：`docs/ai_knowledge_base.md`
- AI 客服知识库技术使用文档：`docs/technical_guide.md`
- Review：`docs/review.md`
- 后端包：`backend/`
- 核心服务：`backend/app/services/customer_service.py`
- PostgreSQL 落库：设置 `backend/.env` 中 `REPOSITORY_BACKEND=postgres`
- Vue 前端：`frontend/`

启动后端 API：

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果你已经用 Docker 启动了 PostgreSQL，请只保留这一条后端进程，不要同时再开第二个 `uvicorn`。

启动客户聊天端：

```powershell
cd frontend
npm run dev
```

客户聊天端地址：`http://127.0.0.1:5173`。

启动人工客服工作台：

```powershell
cd frontend
npm run dev:support
```

人工客服工作台地址：`http://127.0.0.1:5174`。
