# Fitness merge

Containerized **FastAPI** service that ingests workouts from **FIT, GPX, and TCX** files (drop exports from Garmin, iFit, or others into an import folder), optionally pulls summaries from **Strava**, and builds **merged canonical workouts** with per-field provenance (for example, elevation from an iFit TCX and heart rate from a Garmin FIT file).

## Quick start

1. Copy `.env.example` to `.env` and set Strava credentials if you want the Strava bridge ([Strava API settings](https://www.strava.com/settings/api)).

2. Start Postgres and the API:

```bash
docker compose up --build
```

3. Open the **dashboard**: [http://localhost:8000/](http://localhost:8000/) — scan the import folder, upload files, sync Strava (optional), rebuild merge, and inspect results.

4. Or use the API directly (see [http://localhost:8000/docs](http://localhost:8000/docs)).

Host import folder: **`./imports`** on your machine is mounted to **`/data/imports`** in the container. Drop `.fit`, `.gpx`, or `.tcx` files there, then click **Scan import folder** (or `POST /imports/scan`).

## Strava (optional)

- Set `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and `STRAVA_REDIRECT_URI` (must match your Strava app’s authorization callback domain).

- In the UI: **Connect Strava**, approve access, return to the dashboard, **Sync**, then **Rebuild merged activities**.

Strava provides summaries that pair well with files from disk; run merge after syncing so clusters update.

## API overview

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Web dashboard |
| GET | `/health` | Liveness |
| GET | `/api/config` | Import dir + Strava flags (no secrets) |
| GET | `/api/summary` | Row counts + Strava connected |
| POST | `/imports/scan` | Walk `IMPORT_DIR` and parse new/changed files |
| POST | `/imports/upload` | Upload a single FIT/GPX/TCX file |
| GET | `/imports` | Paginated imports (`items`, `total`, `limit`, `offset`) |
| POST | `/merge/rebuild` | Re-cluster all imports and rewrite canonical workouts |
| GET | `/activities` | Paginated merged workouts (`items`, …) |
| GET | `/auth/strava` | Start Strava OAuth |
| GET | `/auth/strava/callback` | OAuth redirect (HTML result page) |
| POST | `/sync/strava` | Fetch recent Strava activities into the import table |

## Matching and merge rules

- **Matching**: imports overlap when start times are within **15 minutes** (configurable via `MATCH_START_TOLERANCE_SECONDS`) and durations agree within **12%** when both exist (`MATCH_DURATION_TOLERANCE_RATIO`), or when time intervals overlap.

- **Heart rate / distance**: prefers **Garmin FIT** (`garmin_fit`) over Strava when multiple sources disagree.

- **Elevation gain**: prefers **`ifit_tcx`** when the import’s origin key contains `ifit` (name your files or paths accordingly); otherwise the largest reported gain is kept as a simple heuristic.

Tune defaults in `app/config.py` or via environment variables on `Settings`.

## Recommendations

- **Backups**: periodically dump Postgres (`docker compose exec db pg_dump -U fitness fitness`) if you care about history.
- **iFit elevation**: put exports under a path or filename containing `ifit` so the merger labels them `ifit_tcx` and prefers elevation from that source when present.
- **Workflow**: scan imports → (optional) Strava sync → rebuild merge → inspect `/activities`. Repeat after new files.
- **Tunnel / HTTPS**: if you expose Strava OAuth beyond localhost, update `STRAVA_REDIRECT_URI` and `PUBLIC_BASE_URL` to match your public URL.
- **Scaling**: OAuth CSRF state is in-memory; use a single API replica or add shared storage for state if you scale out.

## Local development (without Docker)

Create a virtualenv, install `pip install -e .`, run Postgres locally, set `DATABASE_URL`, create `./imports`, then:

```bash
uvicorn app.main:app --reload
```

## Notes

- **OAuth state** for Strava is kept in memory (fine for a single local container; use Redis or similar if you scale horizontally).

- **Garmin**: official Connect API is optional; this stack is built around **files + Strava** as discussed.
