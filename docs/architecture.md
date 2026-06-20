# 项目1 架构设计：客服对话

## 目标

本项目实现一个客服对话 MVP。系统负责记录客户消息、基于知识库检索生成 AI 回复、支持显式转人工、让人工客服接入并继续对话。项目不维护真实商品、订单、政策系统，也不根据对话里的商品或订单编号查询真实业务数据。

## 范围

包含：

- 客户聊天端：客户发送消息、刷新会话、请求转人工。
- AI 知识库回复：先做澄清/改写，再混合检索知识库，基于命中资料回答。
- AI 调用日志：记录 request_id、模型名、耗时、token 估算和错误字段。
- 人工转接：显式“转人工/找客服/人工处理/投诉人工处理”创建 handoff ticket。
- 人工后台：待接入列表、接入、回复、主动结束服务。
- 生命周期：`ai_active`、`handoff_requested`、`human_active`、`human_closed`、`auto_closed`。
- 空闲关闭：只关闭超过 60 秒无新消息的 `ai_active` 会话。
- 纠错沉淀：人工可记录修正答案，作为后续优化样本。
- 可选 PostgreSQL repository：会话、消息、工单、纠错和 AI 日志可落库。
- pgvector 知识库：保存上传资料切片、稀疏特征、全文检索字段和可选稠密向量。
- LLM/Embedding provider 配置：配置 base URL、API key 和模型名后启用真实 embedding 与模型生成；未配置时使用本地兜底。

不包含：

- 商品、订单、政策或旧演示业务数据表。
- 黄金集评测。
- 自动退款、修改订单等真实业务副作用。
- 生产级权限和客服分配策略。
- 多进程或多实例 WebSocket 广播；当前实时消息使用单后端进程内的 WebSocket 连接管理器。

## 架构

```text
frontend/
  src/
    App.vue
    api/customerService.js
    components/ChatThread.vue
    components/MetricGrid.vue
    views/CustomerChatView.vue
    views/HumanSupportDeskView.vue
      |
      v
FastAPI routes: backend/app/api/v1/customer_service.py
      |
      v
Service facade: backend/app/services/customer_service.py
      |
      +-- AnswerService
      +-- Handoff flow
      +-- Human reply flow
      +-- Conversation lifecycle
      +-- Correction logging
      |
      v
Repository boundary: backend/app/services/repository.py
      |
      +-- InMemoryRepository
      +-- SqlAlchemyRepository
```

## 数据流

1. 用户调用 `/api/v1/customer-service/chat`。
2. 服务创建或读取会话，并写入用户消息。
3. 如果命中显式转人工意图，创建 `handoff_ticket`，会话进入 `handoff_requested`。
4. 普通消息由 `AnswerService` 做澄清/改写、混合检索和可选 LLM 生成，并写入 AI 消息和 `ai_call_logs`。
5. 人工后台读取待接入 ticket，接入后会话进入 `human_active`。
6. 人工回复写入同一会话，主动关闭后会话进入 `human_closed`。
7. `check_idle_sessions.py` 或 `/admin/lifecycle/auto-close-idle` 只关闭 idle 的 `ai_active` 会话。
8. 同一会话的新消息通过 WebSocket 广播给客户聊天端和人工客服工作台；`/events` 只保留为历史消息回放接口。

## API

- `GET /api/v1/customer-service/summary`
- `POST /api/v1/customer-service/chat`
- `GET /api/v1/customer-service/conversations/{id}`
- `POST /api/v1/customer-service/conversations/{id}/handoff`
- `GET /api/v1/customer-service/admin/handoff-tickets`
- `POST /api/v1/customer-service/admin/handoff-tickets/{id}/claim`
- `POST /api/v1/customer-service/admin/conversations/{id}/reply`
- `POST /api/v1/customer-service/admin/conversations/{id}/close`
- `GET /api/v1/customer-service/conversations/{id}/events`
- `WS /api/v1/customer-service/ws/conversations/{id}`
- `POST /api/v1/customer-service/corrections`
- `POST /api/v1/customer-service/admin/lifecycle/auto-close-idle`

## 错误处理

- 已关闭会话收到新消息时返回明确错误，调用方应新建会话。
- 未接入的人工会话不能回复。
- 已被接入或关闭的 ticket 不能重复接入。
- 自动关闭前再次检查会话状态和 `last_message_at`，避免误关转人工或人工接待会话。

## 测试

核心业务以纯 Python 服务测试覆盖，数据库 repository 另有 SQLAlchemy 行为测试：

- demo service 不生成商品、订单、政策业务数据；知识切块只来自人工上传资料。
- 普通聊天返回知识库约束下的 AI 回复并写入 AI 调用日志。
- 显式转人工创建 ticket。
- 普通聊天不会自动创建 ticket。
- 人工接入、回复、关闭。
- 空闲关闭只处理 `ai_active`。
- SQLAlchemy repository 覆盖会话、消息、工单和 AI 日志落库。
- `knowledge_documents` 和 `knowledge_chunks` 参与当前知识库上传、检索和 `data_summary`。
