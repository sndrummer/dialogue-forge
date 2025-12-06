.PHONY: web play validate export test lint fix format sync build clean dev help

help:
	@echo "Available commands:"
	@echo "  make build        - Sync deps, fix lint, and test (full rebuild)"
	@echo "  make dev          - Start web editor in debug mode (auto-reload)"
	@echo "  make web          - Start web editor (port 5000)"
	@echo "  make play         - Interactive dialogue player"
	@echo "  make validate     - Validate a .dlg file"
	@echo "  make export       - Export .dlg to JSON"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run ruff linter (check only)"
	@echo "  make fix          - Auto-fix lint issues and format"
	@echo "  make format       - Format code with ruff"
	@echo "  make sync         - Install dependencies"
	@echo "  make clean        - Remove cache files"
	@echo ""
	@echo "Examples:"
	@echo "  make validate file=resources/example.dlg"
	@echo "  make play file=resources/example.dlg"
	@echo "  make web port=8080"

# Full rebuild: sync dependencies, fix lint issues, and test
build: sync fix test
	@echo "✅ Build complete!"

# Clean up cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Cleaned up cache files"

# Start web editor in debug mode with auto-reload
dev:
	uv run dlg-web --debug $(if $(port),--port $(port),)

web:
	uv run dlg-web $(if $(port),--port $(port),)

play:
	uv run dlg-play $(file)

validate:
	uv run dlg-validate $(file)

export:
	uv run dlg-export $(file) $(output)

test:
	uv run pytest

lint:
	uv run ruff check dialogue_forge/

# Auto-fix lint issues (ignores unfixable errors like line-too-long)
fix:
	uv run ruff check --fix dialogue_forge/ || true
	uv run ruff format dialogue_forge/

format:
	uv run ruff format dialogue_forge/

sync:
	uv sync --all-extras
