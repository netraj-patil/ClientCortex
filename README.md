# ClientCortex

**Ask your CRM database questions in plain English, and get instant answers.**

ClientCortex is a natural-language Q&A layer for CRM databases. Connect a PostgreSQL, MySQL or SQLite database, type a question like *"Which deals closed last month?"*, and ClientCortex turns it into a safe, read-only SQL query, runs it, and replies with a plain-English answer.

What makes it fast is a **semantic cache** powered by [Glia](https://github.com/pranitgarje/glia). When someone asks a question that is similar to one already answered, the answer comes straight from the cache without calling the LLM or touching the database. When the underlying data changes, the affected cached answers are removed automatically, so users never see stale results.

## Features

- **Natural-language queries**: ask in plain English, no SQL needed.
- **Semantic caching**: similar questions (not just identical ones) are answered instantly from a Redis-backed vector cache.
- **Automatic cache invalidation**: cached answers are deleted when the tables they depend on change, whether the change came through the app or directly in the database.
- **Safe by design**: generated SQL is parsed and validated (a single `SELECT` on known tables only), then executed on a read-only connection with a timeout and a row limit.
- **Multiple databases**: connect PostgreSQL, MySQL or SQLite. Each connection gets its own isolated cache.
- **Record management**: browse, create, edit and delete rows from the web UI.
- **Cache dashboard**: see cached questions, hit rate, misses and invalidations.
- **Encrypted credentials**: saved database passwords are encrypted with a Fernet key.

## How it works

```
Question ──► Glia semantic cache ──hit──► Cached answer
                  │
                 miss
                  ▼
   LLM generates SQL ► Validate (sqlglot) ► Run read-only ► LLM writes answer
                                                                  │
                                                      Store in Glia cache
                                                                  │
   Table changes (API writes or background watcher) ──► Invalidate dependent entries
```

1. **Fast path:** the question is embedded and looked up in Glia. A close-enough match returns the stored answer.
2. **Miss path:** an LLM (via Groq) writes SQL, the SQL is validated, executed read-only, and the rows are turned into an answer, which is then cached.
3. **Invalidation:** each cached answer is tagged with the tables its SQL reads. Writes made through the API invalidate immediately, and a background watcher catches changes made outside the app.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, Tailwind CSS |
| Backend | FastAPI, SQLAlchemy, sqlglot |
| Cache | [Glia](https://github.com/pranitgarje/glia) on Redis Stack (RediSearch) |
| Embeddings | fastembed (`all-MiniLM-L6-v2`, runs locally) |
| LLM | Groq via LangChain |

## Prerequisites

- **Python** 3.10 or higher
- **Node.js** 20.9 or higher, with npm
- **Docker** (to run Redis Stack)
- **Git**
- A **Groq API key**: get one at [console.groq.com](https://console.groq.com)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/netraj-patil/ClientCortex.git
cd ClientCortex
```

### 2. Start Redis Stack

Glia needs RediSearch, which ships with Redis Stack:

```bash
docker run -d --name redis-stack -p 6379:6379 redis/redis-stack-server:latest
```

### 3. Set up the backend

```bash
cd crm_backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Glia
pip install git+https://github.com/pranitgarje/glia.git
```

Create your environment file:

```bash
cp .env.example .env            # Windows: copy .env.example .env
```

Generate a secret key (used to encrypt saved database passwords):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Open `.env` and fill in the two required values:

```env
GROQ_API_KEY=your_groq_api_key
SECRET_KEY=paste_the_generated_key_here
```

Start the API server:

```bash
uvicorn app.main:app --reload
```

The API runs at **http://localhost:8000**, with interactive docs at **http://localhost:8000/docs**. The first start downloads the embedding model, so it can take a minute.

### 4. Set up the frontend

Open a new terminal:

```bash
cd crm_frontend
npm install
npm run dev
```

The app runs at **http://localhost:3000**.

If your backend is not on `http://localhost:8000`, create `crm_frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://your-backend-host:8000
```

### 5. Try it out

1. Open http://localhost:3000 and go to **Connections**.
2. Add your CRM database. It is tested before it is saved.
3. Go to **Ask**, pick the connection, and ask a question.
4. Ask the same question again, or a similar one. The second answer comes from the cache and is much faster.

## Configuration

All backend settings live in `crm_backend/.env`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | – | API key for the Groq LLM |
| `SECRET_KEY` | Yes | – | Fernet key for encrypting saved database passwords |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis Stack connection URL |
| `LLM_MODEL` | No | `openai/gpt-oss-120b` | Groq model used for SQL and answer generation |
| `CACHE_DISTANCE_THRESHOLD` | No | `0.2` | How similar a question must be to count as a cache hit (lower is stricter) |
| `CACHE_TTL_SECONDS` | No | `3600` | Cached answers expire after this time, as a safety net |
| `WATCHER_ENABLED` | No | `true` | Detect outside table changes and invalidate the cache |
| `WATCHER_INTERVAL_SECONDS` | No | `10` | How often the watcher checks for changes |
| `QUERY_ROW_LIMIT` | No | `100` | Maximum rows a generated query may return |
| `QUERY_TIMEOUT_SECONDS` | No | `10` | Timeout for generated queries |
| `CORS_ORIGINS` | No | `http://localhost:3000,http://localhost:5173` | Allowed frontend origins |

## Project structure

```
ClientCortex/
├── crm_backend/     # FastAPI service: Q&A pipeline, cache, database access
└── crm_frontend/    # Next.js web app
```

### Backend (`crm_backend/`)

```
crm_backend/
├── requirements.txt
├── .env.example
└── app/
    ├── main.py            # FastAPI app, startup/shutdown, CORS, health check
    ├── config.py          # Reads settings from environment variables
    ├── schemas.py         # Request/response models (Pydantic)
    ├── db.py              # Saved connections, encrypted passwords, SQLAlchemy engines, schema helpers
    ├── pipeline.py        # Cache-miss path: generate SQL, validate, run read-only, write answer
    ├── cache_service.py   # Glia semantic cache and table-to-answer dependency registry
    ├── embeddings.py      # Local embedding model used by Glia
    ├── watcher.py         # Background poller that invalidates cache on outside data changes
    ├── redis_client.py    # Shared Redis connection
    └── routers/
        ├── ask.py         # POST /api/ask
        ├── connections.py # Add, list and remove database connections; view schema
        ├── records.py     # CRUD on table rows (invalidates the cache on write)
        └── cache.py       # Cache entries, stats and clearing
```

### Frontend (`crm_frontend/`)

```
crm_frontend/
├── package.json
├── next.config.mjs
├── app/
│   ├── layout.js          # Root layout with navbar and connection provider
│   ├── page.js            # Ask page: type a question, see answer, source and SQL
│   ├── records/page.js    # Browse and edit table records
│   ├── cache/page.js      # Cached entries and hit-rate stats
│   └── connections/page.js# Add and manage database connections
├── components/
│   ├── Navbar.js          # Navigation and active-connection selector
│   ├── ConnectionContext.js # Shares the active connection across pages
│   └── ui.js              # Shared Alert, Button and input styles
└── lib/
    └── api.js             # Fetch wrapper for talking to the backend
```

## API overview

Full interactive documentation is available at `/docs` once the backend is running.

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/ask` | Ask a question and get `{answer, source, sql, latency_ms}` |
| POST | `/api/connections` | Add a database (tested before saving) |
| GET | `/api/connections` | List saved connections |
| GET | `/api/connections/{id}/schema` | Tables and columns |
| DELETE | `/api/connections/{id}` | Remove a connection and its cache entries |
| GET / POST | `/api/connections/{id}/tables/{table}/records` | List or create rows |
| GET / PUT / DELETE | `/api/connections/{id}/tables/{table}/records/{rid}` | Read, update or delete a row |
| GET | `/api/cache/entries` | Cached questions and answers |
| GET | `/api/cache/stats` | Hits, misses, invalidations, hit rate |
| DELETE | `/api/cache` | Clear the cache |
| GET | `/api/health` | Liveness and Redis check |

## Security notes

- Generated SQL is validated to be a single `SELECT` on known tables, and runs on a read-only connection with a timeout and row limit.
- Rows returned by a query are sent to the LLM to compose the answer, so avoid connecting databases whose data must not leave your environment.
- There is currently **no authentication**, connections accept any host, and the record routes can write to connected databases. This is fine for local use and demos. Add authentication and restrict allowed hosts before deploying publicly.

## Troubleshooting

- **`SECRET_KEY is not set`**: generate a key with the command in step 3 and add it to `.env`.
- **Backend cannot connect to Redis**: make sure the Redis Stack container is running (`docker ps`) and `REDIS_URL` is correct.
- **Frontend says it cannot reach the backend**: confirm `uvicorn` is running on port 8000, or set `NEXT_PUBLIC_API_URL`.
- **Too few or too many cache hits**: adjust `CACHE_DISTANCE_THRESHOLD` in `.env`.
