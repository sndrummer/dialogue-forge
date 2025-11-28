.PHONY: web play validate export test lint format sync help

help:
	@echo "Available commands:"
	@echo "  make web          - Start web editor (port 5000)"
	@echo "  make play         - Interactive dialogue player"
	@echo "  make validate     - Validate a .dlg file"
	@echo "  make export       - Export .dlg to JSON"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run ruff linter"
	@echo "  make format       - Format code with ruff"
	@echo "  make sync         - Install dependencies"
	@echo ""
	@echo "Examples:"
	@echo "  make validate file=resources/example.dlg"
	@echo "  make play file=resources/example.dlg"
	@echo "  make web port=8080"

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

format:
	uv run ruff format dialogue_forge/

sync:
	uv sync --all-extras
