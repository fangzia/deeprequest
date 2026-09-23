.PHONY: dev dev-backend dev-frontend test lint eval

# 本地开发：同时起前后端
dev: dev-backend dev-frontend

dev-backend:
	cd backend && uv run uvicorn deepquest.server.app:app --reload --port 8598

dev-frontend:
	cd frontend && npm run dev

# 测试与静态检查
test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check src tests

# 引用一致性评测（对 {"report": ..., "sources": [...]} 格式的 JSON 文件）
eval:
	cd backend && uv run python -m deepquest.evals.citation $(FILE)
