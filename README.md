# Drifthood

API drift detection toolkit. Compare API responses across two release versions to catch regressions before promotion.

## What it does

Point Drifthood at two instances of your API (version A and version B) and it will:

1. Parse OpenAPI specs from both
2. Execute matching endpoints on both versions
3. Diff the responses, ignoring dynamic fields (timestamps, tokens, nonces)
4. Report structural differences with severity classification

The philosophy: detection over prevention, repetition over abstraction, errors are data not exceptions.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Start backend (port 8899)
HOST_A=http://localhost:3000 HOST_B=http://localhost:3001 python run.py

# Start frontend (port 5899)
npm run dev
```

Open http://localhost:5899

## Architecture

- **Backend**: Python/FastAPI with deepdiff for comparison
- **Frontend**: Svelte 5 with Vite
- **Storage**: SQLite for sessions and testruns

## License

MIT - see [LICENSE](LICENSE)
