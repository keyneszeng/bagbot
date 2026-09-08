.PHONY: help install dev test lint run dashboard probe once status demo clean

PYTHON ?= python3.10
VENV  ?= .venv

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## Create venv and install dependencies.
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	cp -n .env.example .env || true
	@echo "✓ venv ready.  Run 'make demo' to see it work, then edit .env."

dev: install  ## Alias for install.

demo:  ## Run the zero-config end-to-end demo (no token needed).
	$(VENV)/bin/python scripts/demo_e2e.py

test:  ## Run pytest.
	$(VENV)/bin/python -m pytest tests/ -v

lint:  ## Lint the source.
	$(VENV)/bin/python -m compileall -q src/

run:  ## Start the daemon (foreground).
	$(VENV)/bin/python -m bagbot.cli run

dashboard:  ## Start the dashboard.
	$(VENV)/bin/python -m bagbot.cli dashboard

probe:  ## Exercise all 6 MCP tools and print results.
	$(VENV)/bin/python -m bagbot.cli probe

once:  ## Run one daemon tick and exit.
	$(VENV)/bin/python -m bagbot.cli once

status:  ## Show recent state from local SQLite.
	$(VENV)/bin/python -m bagbot.cli status

clean:  ## Remove venv and local data.
	rm -rf $(VENV) data/ .pytest_cache/ __pycache__/ */__pycache__/ */*/__pycache__/
