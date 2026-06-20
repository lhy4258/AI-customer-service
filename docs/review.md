# 项目1 Review

## 需求覆盖

- 后端代码：已实现核心服务、FastAPI 路由、Pydantic schema、内存 repository 和 SQLAlchemy repository。
- 客服对话：普通消息返回知识库约束下的 AI 回复，并记录到同一会话。
- AI 调用日志：普通 AI 回复会写入 `ai_call_logs`。
- 人工转接：显式转人工创建 ticket，会话进入 `handoff_requested`。
- 人工后台：实现 ticket 列表、接入、人工回复、主动关闭。
- 生命周期：实现 `ai_active`、`handoff_requested`、`human_active`、`human_closed`、`auto_closed`。
- 空闲关闭：实现 60 秒 idle 扫描，只关闭 `ai_active`。
- 纠错沉淀：实现 correction 记录。
- 前端演示：客户聊天端运行在 `5173`，人工客服工作台运行在 `5174`。

## 已删除范围

- 商品、订单、政策实体和 seed 数据。
- 商品/订单/政策导入 API。
- 旧商品/订单/政策知识切块数据。
- 黄金集评测和 `run_evals.py`。
- 商品、订单、政策导出文本。

## 已知限制

- LLM/Embedding 未配置时会使用本地兜底；配置后才会调用真实模型。
- PostgreSQL + pgvector 已用于资料上传和知识切片；当前不会生成商品、订单或政策业务切块。
- SQLAlchemy repository 已落地；生产级并发抢单仍需在数据库版本 claim 时补事务或行级锁。
- WebSocket 已是同一会话内的实时消息主链路；SSE `events` 仅保留为历史消息回放。
- Vue 前端不包含登录、权限和生产级客服分配策略。

## 测试计划

- 核心单元测试：在 `backend/` 下运行 `uv run python -m unittest discover -s tests -v`
- 数据摘要检查：在 `backend/` 下运行 `uv run python scripts/seed_demo_data.py`
- 演示流程：在 `backend/` 下运行 `uv run python scripts/run_demo.py`
- 空闲关闭脚本：在 `backend/` 下运行 `uv run python scripts/check_idle_sessions.py`
- 前端构建：在 `frontend/` 下运行 `npm run build:customer` 和 `npm run build:support`

## Review 关注点

- 状态机边界清晰：已关闭会话不能继续写入。
- 重复接入：当前通过状态判断防止同一 ticket 重复接入；生产级数据库部署应在 claim 时加事务或行级锁。
- 业务数据边界：项目不查询商品、订单或政策，相关词只作为用户输入文本记录。
