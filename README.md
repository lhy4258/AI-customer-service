# 项目1：AI 客服工作台

一个面向客服对话场景的 AI 工作台 Demo，覆盖“客户咨询 -> AI 知识库回复 -> 必要时转人工 -> 人工接入处理 -> 全链路留痕”的核心闭环。

项目不接入真实商品、订单、库存或售后业务系统。对话中出现的商品、订单、退款等内容只作为聊天文本或知识库资料处理，避免把演示数据误包装成真实业务能力。

## 核心亮点

- RAG 客服回复：基于 PostgreSQL + pgvector 保存知识切片，支持稠密向量和稀疏关键词混合检索。
- 人工接管闭环：客户可显式转人工，客服工作台支持接入、回复、结束服务。
- 实时消息同步：客户聊天端和人工客服端通过 WebSocket 接收同一会话的新消息。
- 资料上传入库：人工客服可上传文本资料，后端切片、去重、生成稀疏特征和可选 embedding 后入库。
- 召回可观测：AI 回复会在 `conversation_messages.metadata_json` 和 `ai_call_logs.metadata_json` 中记录 query、命中切片、分数、置信度和最终引用。
- 安全回答边界：资料不足时拒答并建议转人工；命中资料后要求模型只基于召回内容回答。
- 本地可运行：Docker Compose 提供 PostgreSQL/pgvector 和 Redis；前后端可在本机直接启动。

## 系统架构

```text
客户聊天端 / 人工客服工作台
        |
        v
FastAPI Customer Service API
        |
        v
CustomerServiceFacade
        |
        +-- 会话状态机
        +-- 转人工工单
        +-- WebSocket 广播
        +-- AnswerService
              |
              +-- 澄清门控 / 上下文改写
              +-- PostgreSQL + pgvector 混合检索
              +-- OpenAI-compatible LLM / Embedding
              +-- AI 调用日志与召回审计
```

当前仓库层为了兼容轻量演示，仍在 Python 中融合 `dense_score` 和 `sparse_score`。大规模数据场景可升级为 PostgreSQL 侧 pgvector/tsvector 先召回候选，再由应用层重排。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3, Vite |
| 后端 | FastAPI, Pydantic, SQLAlchemy |
| 数据库 | PostgreSQL, pgvector, tsvector/jsonb |
| 实时通信 | WebSocket |
| AI 接口 | OpenAI-compatible Embedding / Chat Completions |
| 本地基础设施 | Docker Compose, Redis 预留 |

## 目录结构

```text
demo1/
  backend/                 FastAPI 后端、领域服务、数据库模型
  frontend/                客户聊天端和人工客服工作台
  docs/                    技术文档、架构说明、使用说明
  backend/infra/init.sql   PostgreSQL pgvector 初始化
  backend/.env.example     后端环境变量示例
```

## 快速启动

### 1. 启动数据库

```powershell
cd backend
docker compose up -d
```

### 2. 配置后端环境

复制示例配置：

```powershell
copy .env.example .env
```

关键配置：

```env
REPOSITORY_BACKEND=postgres
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/ai_portfolio
LLM_BASE_URL=
LLM_API_KEY=
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=
```

未配置 LLM/Embedding 时，系统仍可上传资料、落库、做稀疏检索和本地兜底回复；配置后启用真实 embedding 和模型生成。

### 3. 启动后端

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

本地调试只保留一个后端进程，避免 WebSocket 连接和请求落到不同进程。

### 4. 启动客户聊天端

```powershell
cd frontend
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

### 5. 启动人工客服工作台

```powershell
cd frontend
npm run dev:support
```

访问：

```text
http://127.0.0.1:5174
```

`dev:support` 表示用 Vite 的 `support` 模式启动人工客服端，端口固定为 `5174`；客户聊天端运行在 `5173`。

## 知识库资料

项目保留了小样本：

```text
backend/data/correct_qa_200.txt
```

大语料文件不会提交到仓库：

```text
backend/data/correct_answer.txt
backend/data/correct_qa.txt
```

如需从原始训练集重新生成干净语料，可运行：

```powershell
cd backend
uv run python scripts/extract_correct_answers.py
```

当前入库策略不是强行拆分单轮 `question_text/answer_text`，而是把客服历史案例整体写入 `retrieval_text/chunk_text`，减少多轮语料说话人边界不清造成的误标。

## 关键 API

| 功能 | API |
| --- | --- |
| 客户发送消息 | `POST /api/v1/customer-service/chat` |
| 获取会话详情 | `GET /api/v1/customer-service/conversations/{conversation_id}` |
| 客户请求转人工 | `POST /api/v1/customer-service/conversations/{conversation_id}/handoff` |
| WebSocket 实时消息 | `WS /api/v1/customer-service/ws/conversations/{conversation_id}` |
| 客服查看工单 | `GET /api/v1/customer-service/admin/handoff-tickets` |
| 客服接入工单 | `POST /api/v1/customer-service/admin/handoff-tickets/{ticket_id}/claim` |
| 客服发送回复 | `POST /api/v1/customer-service/admin/conversations/{conversation_id}/reply` |
| 上传知识资料 | `POST /api/v1/customer-service/admin/knowledge/upload` |
| 查看知识文档 | `GET /api/v1/customer-service/admin/knowledge/documents` |

后端启动后也可查看自动接口文档：

```text
http://127.0.0.1:8000/docs
```

## 文档入口

- 架构设计：`docs/architecture.md`
- 使用说明：`docs/usage.md`
- AI 知识库与混合检索：`docs/ai_knowledge_base.md`
- 完整技术文档：`docs/technical_guide.md`
- Review 记录：`docs/review.md`

## 当前边界

- 不查询真实商品、订单、库存、优惠和售后政策。
- Redis 当前是基础设施预留，主检索路径使用 PostgreSQL + pgvector。
- WebSocket 广播是单后端进程内存版，多进程部署需要增加 Redis pub/sub 等跨进程广播机制。
- AI 回复是完整生成后返回，不是 token-by-token 流式输出。
