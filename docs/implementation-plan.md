# 项目1 Implementation Plan

**Goal:** Build a simple customer-service conversation MVP.

**Architecture:** Keep the FastAPI route layer thin and put deterministic conversation behavior in service classes. Use an in-memory repository for lightweight demos, with optional PostgreSQL persistence for conversations, messages, handoff tickets, corrections, AI call logs, knowledge documents, and knowledge chunks.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy-ready models, PostgreSQL-ready schema, Vue 3 + Vite frontend.

---

### Task 1: Conversation Domain

**Files:**

- `backend/app/services/entities.py`
- `backend/app/services/repository.py`
- `backend/app/services/demo_data.py`

### Task 2: API Layer

**Files:**

- `backend/app/main.py`
- `backend/app/api/deps.py`
- `backend/app/api/v1/customer_service.py`
- `backend/app/schemas/customer_service.py`

- [x] Implement customer-service routes for chat, conversation lookup, handoff, human support actions, event replay, corrections, summary, and idle close.
- [x] Remove product/order/policy ingest endpoints and eval endpoint.

### Task 3: Scripts And Docs

**Files:**

- `backend/scripts/extract_correct_answers.py`
- `docs/usage.md`
- `docs/review.md`

- [x] Keep only the corpus extraction script for reusable local data preparation.
- [x] Remove `run_evals.py`.
- [x] Document that product/order/policy data is out of scope.

### Task 4: Frontend Demo

**Files:**

- `frontend/src/App.vue`
- `frontend/src/views/CustomerChatView.vue`
- `frontend/src/views/HumanSupportDeskView.vue`
- `frontend/src/components/ChatThread.vue`
- `frontend/src/components/MetricGrid.vue`

- [x] Build separate customer and human support entry ports.
- [x] Remove citation/source display and product/order example prompts.

### Task 5: Project Metadata

**Files:**

- `backend/pyproject.toml`
- `backend/.env.example`
- `backend/docker-compose.yml`
- `backend/app/core/config.py`
- `backend/app/core/database.py`
- `backend/app/models/tables.py`
- `mcp/customer_service_tools.md`

- [x] Keep PostgreSQL + Redis compose file.
- [x] Keep SQLAlchemy table definitions for conversation data, knowledge documents, and pgvector knowledge chunks.
- [x] Update MCP reservation document for conversation tools only.
