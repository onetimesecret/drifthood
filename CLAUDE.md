# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

API drift detection toolkit. Compares API responses across two release versions (A and B) of a codebase to catch regressions before promotion. The philosophy is scrappy: detection over prevention, repetition over abstraction, errors are data not exceptions.

## Architecture

- **`dd/`** — Python package: `app.py` (FastAPI routes), `config.py`, `compare.py` (deepdiff integration), `openapi.py` (OpenAPI parser).
- **`src/`** — Svelte 5 frontend. Vite dev server on port 5899, proxies `/api` to backend on :8899.
- **`lib/`** — JavaScript utilities for API calls, diffing, content-type handling, state management.
- **`tests/`** — Python tests (pytest) and JS tests.
- **`run.py`** — Entry point. Starts FastAPI backend on port 8899.

## Running the Drift Detector

```bash
pip install -r requirements.txt
npm install

# Terminal 1: API backend on :8899
HOST_A=http://localhost:10235 HOST_B=http://localhost:10240 python run.py

# Terminal 2: Vite dev server on :5899 (proxies /api to :8899)
npm run dev
```

## Identity and Security Model

The drift detector uses a two-part session identity:

- **Token** — a cryptographic secret stored in browser storage (`sessionStorage`, or `localStorage` with "Remember me"). Used in `Authorization: Bearer` headers. The server stores only the SHA256 hash; the raw token is never persisted server-side.
- **Extid** — a UUIDv7 public identifier for the session. Appears in URLs (`/s/{extid}`). Not a credential — knowing the extid does not grant access.

All database entities (sessions, documents, testruns) carry UUIDv7 `extid` fields. Integer primary keys, foreign keys, and raw tokens never appear in URLs, UI text, or API payloads.

## Key Conventions

- `compare_one()` sends authenticated requests; `compare_one_anon()` sends without auth
- Dynamic fields (keys, timestamps, nonces, tokens) are stripped before diffing — only structural shape matters
- Default ports: backend → 8899, Vite dev → 5899

## Dependencies

Python: `fastapi`, `uvicorn`, `requests`, `deepdiff`
Frontend: `svelte`, `vite`, `tailwindcss`
