# SC2 Replay Analyzer

Personal SC2 replay analysis tool. Watches your replay folder, ingests new replays into SQLite, and gives you a UI for browsing matches, drilling into macro timelines, and tracking metric trends.

## Stack

- **Backend**: Python 3.11+, FastAPI, sc2reader, watchdog, SQLite
- **Frontend**: Vite + Vue 3 + Pinia + Vue Router + ECharts
- **Storage**: SQLite (`backend/data/replays.db`)

## First-time setup

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
# edit .env: set REPLAY_DIR and MY_PLAYER_NAMES
```

Frontend:

```powershell
cd frontend
npm install
```

## Daily run

From the repo root:

```powershell
.\start.bat
```

This launches the backend (`http://127.0.0.1:8765`) and the Vite dev server (`http://localhost:5173`) in two separate terminal windows. Open the frontend URL in your browser.

The backend watches `REPLAY_DIR` and ingests new replays automatically. For a one-off backfill of existing replays, hit **Scan now** on the Settings page.

## How to add a metric

1. Open `backend/app/metrics.py`.
2. Add a function decorated with `@metric("my_metric_name")` returning a float or None.
3. Restart the backend.
4. Hit **Scan now** — existing matches already have all old metrics, but the new one will be computed for future ingests. To re-compute for old matches, delete `backend/data/replays.db` and rescan (current dev shortcut; a proper recompute endpoint is a TODO).

Metric values are shown in the match detail and selectable on the Trends page.

## API endpoints

- `GET /api/health`
- `GET /api/metrics`
- `GET /api/facets`
- `GET /api/matches?matchup=&race=&result=&map_name=&limit=&offset=`
- `GET /api/matches/{id}` — full detail incl. timeseries & build events
- `GET /api/trends/{metric_name}?race=&matchup=`
- `POST /api/ingest/scan` — backfill the replay folder

OpenAPI docs at `http://127.0.0.1:8765/docs`.

## Roadmap

Walking skeleton done. Next obvious steps:
- Build-order fingerprinting / tagging
- LLM-driven coaching summaries (OpenRouter via LiteLLM)
- Training targets ("workers @ 5min ≥ 60") with pass/fail per match
- Reingest endpoint that recomputes metrics without dropping the DB
