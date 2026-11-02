# CRM Q&A backend (FastAPI + Glia)

Ask questions about a CRM database in plain English. Answers come from a Glia semantic cache when a
similar question was asked before, otherwise from LLM-generated read-only SQL. Cached answers are
removed automatically when the data they depend on changes.

## Setup

```bash
# 1. Redis Stack (RediSearch is required by Glia)
docker run -d -p 6379:6379 redis/redis-stack-server:latest

# 2. Python deps + your local Glia package
pip install -r requirements.txt
pip install -e ../glia

# 3. Config
cp .env.example .env     # fill in GROQ_API_KEY and SECRET_KEY

# 4. Run
uvicorn app.main:app --reload
```

Interactive docs: http://localhost:8000/docs

## Routes

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/ask` | `{question, connection_id}` -> `{answer, source: "cache"\|"database", sql, latency_ms}` |
| POST | `/api/connections` | Add a database (tested before saving) |
| GET | `/api/connections` | List saved connections (no passwords) |
| GET | `/api/connections/{id}/schema` | Tables and columns |
| DELETE | `/api/connections/{id}` | Remove a connection and its cache entries |
| GET | `/api/connections/{id}/tables/{table}/records` | List rows (`limit`, `offset`) |
| GET | `/api/connections/{id}/tables/{table}/records/{rid}` | One row |
| POST | `/api/connections/{id}/tables/{table}/records` | Create a row |
| PUT | `/api/connections/{id}/tables/{table}/records/{rid}` | Update columns of a row |
| DELETE | `/api/connections/{id}/tables/{table}/records/{rid}` | Delete a row |
| GET | `/api/cache/entries` | Cached questions, answers and the tables they depend on |
| GET | `/api/cache/stats` | hits, misses, invalidations, entries, hit_rate |
| DELETE | `/api/cache` | Clear the cache and reset the counters |
| GET | `/api/health` | Liveness and Redis check |

The three cache routes take an optional `?connection_id=`; without it they cover every connection.
Write routes return `cache_entries_invalidated` so the frontend can show it.

## How the flows map to the code

1. **Fast path** - `routers/ask.py` calls `cache_service.lookup()` -> `GliaManager.check()`.
2. **Miss path** - `pipeline.py`: generate SQL (LLM) -> validate (sqlglot: one SELECT, known tables only)
   -> run on a read-only connection -> LLM turns the rows into an answer -> `GliaManager.store()`.
3. **Invalidation** - two triggers, both end in `CacheInvalidator.delete_by_tag()`:
   - the record routes invalidate right after a commit;
   - `watcher.py` polls tables that have cached answers and catches changes made outside this API.

## Design notes

- **Granularity is per table.** A cached answer is tagged with the tables its SQL reads
  (`customers__deals`). Any change to one of those tables removes it. This is deliberate: an
  aggregate like "how many open deals" changes when a row is inserted, which row-level tracking would miss.
- **One Glia index per connection** (`crm_<connection_id>`), so identical questions on different
  databases never share answers.
- **Read-only safety.** Generated SQL is validated, then run on a connection set to read-only mode with a
  statement timeout and a row limit. Rows returned by a query are sent to the LLM to write the answer.
- **Watcher change detection.** Postgres uses `pg_stat_user_tables` counters. Other databases use
  `COUNT(*)` plus `MAX(updated_at)` when that column exists.
- `CACHE_TTL_SECONDS` expires entries even if an invalidation is somehow missed.
- Tune `CACHE_DISTANCE_THRESHOLD` against your embedding model if hits are too loose or too rare.

## Before putting this anywhere public

Connections accept any host (or any file path for sqlite), and the record routes can write to those
databases. There is no authentication. That is fine for a demo; add auth and restrict hosts first otherwise.
