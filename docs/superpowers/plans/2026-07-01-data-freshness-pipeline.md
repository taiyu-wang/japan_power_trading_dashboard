# Data Freshness Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add visible data freshness and scheduled public-data publication without making Streamlit responsible for durable ingestion.

**Architecture:** A pure freshness module evaluates dataset records and manifests. A public-data pipeline reuses existing JEPX, weather, news, and offer-stack adapters and publishes compact artifacts to a dedicated `data` branch. Streamlit loaders read the remote artifacts with TTL caching and fall back to bundled files.

**Tech Stack:** Python, pandas, requests, Streamlit caching, GitHub Actions, CSV/JSON artifacts.

---

### Task 1: Freshness Domain Model

**Files:**
- Create: `src/data_freshness.py`
- Create: `tests/test_data_freshness.py`

- [ ] Write failing tests for fresh, delayed, stale, missing, and overall manifest states.
- [ ] Run `PYTHONPATH=. .venv/bin/pytest tests/test_data_freshness.py -q` and confirm failures are caused by the missing module.
- [ ] Implement record construction, threshold evaluation, manifest aggregation, and compact summary generation.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Published Artifact Client

**Files:**
- Create: `src/published_data.py`
- Modify: `src/config.py`
- Modify: `src/data_loader.py`
- Modify: `tests/test_data_loader.py`

- [ ] Write failing tests for successful remote CSV parsing and local fallback after remote failure.
- [ ] Run the focused loader tests and confirm the new behavior is absent.
- [ ] Add configurable public-data URLs, cached manifest/CSV fetches, and remote-first integration for weather, news, intraday, baseload, and compact offer-stack artifacts.
- [ ] Re-run loader tests and existing source tests.

### Task 3: Global Freshness Strip

**Files:**
- Modify: `src/utils.py`
- Modify: `tests/test_utils.py`

- [ ] Write failing tests for deterministic freshness-strip HTML and status classes.
- [ ] Implement compact HTML generation and render it from `configure_page()`.
- [ ] Add current/delayed/stale/unavailable CSS tokens that remain legible in the light dashboard theme.
- [ ] Re-run utility tests.

### Task 4: Public Refresh Pipeline

**Files:**
- Create: `src/public_data_pipeline.py`
- Create: `tests/test_public_data_pipeline.py`

- [ ] Write failing tests for successful publication and preservation of prior records when a collector fails.
- [ ] Implement artifact validation, atomic CSV/JSON writes, collector isolation, and CLI dataset selection.
- [ ] Connect existing Open-Meteo, public news, JEPX intraday/baseload, and seven-day offer-stack processors.
- [ ] Re-run focused pipeline tests.

### Task 5: Scheduled GitHub Publication

**Files:**
- Create: `.github/workflows/refresh_public_data.yml`
- Modify: `README.md`
- Modify: `docs/deployment.md`

- [ ] Add daily and manual workflow triggers.
- [ ] Check out `main` and `data` into separate paths, run the CLI, and commit only `data/published`.
- [ ] Document data-branch architecture, cache behavior, manual dispatch, and deployment troubleshooting.

### Task 6: Seed, Verify, and Publish

**Files:**
- Create on `data` branch: `data/published/*.csv`
- Create on `data` branch: `data/published/manifest.json`

- [ ] Seed the data branch from currently validated local artifacts.
- [ ] Run the complete test suite with `PYTHONPATH=. .venv/bin/pytest`.
- [ ] Start Streamlit and visually verify the freshness strip on Overview, Trading Signals, and Market Structure.
- [ ] Publish the application update while preserving the repository's single-snapshot `main` history policy.
