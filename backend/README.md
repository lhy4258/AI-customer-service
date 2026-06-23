# 后端包

这里是项目1的后端代码包，包含 FastAPI API、核心客服对话服务、资料处理脚本、Docker Compose 和 Python 依赖定义。

Docker Compose 使用带 pgvector 的 PostgreSQL 镜像。当前业务代码会写入客服对话、工单、纠错、AI 日志、知识文档和知识切片；配置 LLM/Embedding 后可启用稠密向量和生成式回答。

常用命令：

```powershell
uv sync
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
uv run python scripts/extract_correct_answers.py
```

核心路径：

- `app/main.py`：FastAPI 入口
- `app/api/v1/customer_service.py`：REST API
- `app/services/customer_service.py`：客服业务服务
- `app/services/repository.py`：内存/SQLAlchemy repository
- `scripts/extract_correct_answers.py`：从原始语料提取干净历史案例
