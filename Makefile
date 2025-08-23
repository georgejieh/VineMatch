# Makefile for VineMatch — one-command onboarding and common tasks
# Usage examples:
#   make setup             # install all runtime deps + Playwright browsers
#   make setup-dev         # install dev tools too (ruff/black/mypy/pytest)
#   make lint format test  # quality checks
#   make scrape-links STYLES="Red White" YEARS="2021 2022" PAGES=5 HEADLESS=1
#   make scrape-details LINKS="data/raw/scraped/wineenthusiast/20250101/wine_links.csv" HEADLESS=1

SHELL := /bin/bash
PY ?= python

# Flags for scrape targets (can be overridden: make PAGES=5 ...)
PAGES ?= 48
STYLES ?=
YEARS ?=
HEADLESS ?= 0
CHECKPOINT ?= 100

# Build optional CLI flags from variables
ifneq ($(strip $(STYLES)),)
STYLE_FLAGS := --styles $(STYLES)
endif
ifneq ($(strip $(YEARS)),)
YEAR_FLAGS := --years $(YEARS)
endif
ifeq ($(HEADLESS),1)
HEADLESS_FLAG := --headless
endif
ifneq ($(strip $(CHECKPOINT)),)
CHECKPOINT_FLAG := --checkpoint-every $(CHECKPOINT)
endif

.DEFAULT_GOAL := help

.PHONY: help setup setup-dev install install-dev browsers precommit lint format typecheck test notebooks app scrape-links scrape-details clean

help:
	@echo "VineMatch Make targets:"
	@echo "  setup           Install runtime deps and Playwright browsers"
	@echo "  setup-dev       Install runtime + dev deps, init pre-commit"
	@echo "  lint            Run ruff checks"
	@echo "  format          Run black formatter"
	@echo "  typecheck       Run mypy type checks"
	@echo "  test            Run pytest"
	@echo "  notebooks       Launch JupyterLab"
	@echo "  app             Launch Gradio UI"
	@echo "  scrape-links    Collect Wine Enthusiast links (see vars)"
	@echo "  scrape-details  Scrape details for LINKS=path/to/wine_links.csv"
	@echo "  clean           Remove caches and build artifacts"

setup: install browsers ## Install runtime deps + Playwright browsers

setup-dev: install-dev browsers precommit ## Install runtime+dev deps + hooks

install:
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e .

install-dev:
	$(PY) -m pip install -U pip
	$(PY) -m pip install -e .[dev]

browsers:
	$(PY) -m playwright install

precommit:
	pre-commit install || true

lint:
	ruff check .

format:
	black .

typecheck:
	mypy src tests

test:
	pytest -q

notebooks:
	jupyter lab

app:
	$(PY) -m vinematch.ui.gradio_app

scrape-links:
	$(PY) scripts/scrape_wineenthusiast_playwright.py links --max-pages $(PAGES) $(STYLE_FLAGS) $(YEAR_FLAGS) $(HEADLESS_FLAG)

scrape-details:
	@if [ -z "$(LINKS)" ]; then echo "Set LINKS=path/to/wine_links.csv" && exit 1; fi
	$(PY) scripts/scrape_wineenthusiast_playwright.py details --links-csv "$(LINKS)" $(HEADLESS_FLAG) $(CHECKPOINT_FLAG)

clean:
	rm -rf .pytest_cache .mypy_cache build dist */__pycache__ **/__pycache__
