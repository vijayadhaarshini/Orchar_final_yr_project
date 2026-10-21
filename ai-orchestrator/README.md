# Orchar — AI Orchestrator

A multi-agent system that takes a feature request or bug report, plans it,
writes Python code for it, reviews the code, and tests it. A human can pause
the run at chosen points to approve, change or reject the work.

## How a run works

1. **Overseer** reads the request and picks the stages to run, plus the
   points where a human should review ("checkpoints").
2. The stages run in order:

   | Stage | What it does |
   |---|---|
   | Planner | Splits the request into tasks |
   | Designer | Writes a short architecture and API design |
   | Developer ↔ Critic | The developer writes code; the critic scores it (1–10) and the developer revises until the score is high enough |
   | Tester | Writes pytest tests and runs them. If they fail, the developer fixes the code and the tests run again |
   | Self-evolve | Saves a lesson from this run, which is added to agent prompts in later runs |

3. At a checkpoint the run stops with status `awaiting_human`. The web app
   shows what was produced, and the reviewer approves, adds instructions, or
   rejects. The run then continues from the next stage.

If a plan needs several kinds of work (for example database + auth), the
planner stage can also start **specialist sub-agents** that write those
parts in parallel.

Everything about a run is saved in PostgreSQL, so a paused run survives a
server restart.

## Tech stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy (async) + PostgreSQL
- **Agents:** [AutoGen 0.2](https://microsoft.github.io/autogen/0.2/) (`pyautogen`) calling the Groq API
- **Memory:** ChromaDB with a local embedding model (`all-MiniLM-L6-v2`)
- **Frontend:** React 18, Vite, Tailwind CSS

## Setup

You need **Python 3.11 or 3.12** (`pyautogen` 0.2 does not install on 3.13),
**Node.js 18+**, **PostgreSQL**, and a **Groq API key**.

### Backend

```bash
cd ai-orchestrator
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt

copy .env.example .env            # Windows  (macOS / Linux: cp .env.example .env)
# then open .env and set DATABASE_URL and GROQ_API_KEY

uvicorn app.main:app --reload
```

The API runs on http://localhost:8000 (interactive docs at `/docs`).
Tables are created on first start. Run a single server process: on startup
the app marks runs that were cut off by a restart as failed, which assumes
no other worker is running them.

The first run that uses project memory downloads the embedding model
(about 90 MB).

### Frontend

```bash
cd ai-orchestrator/frontend
npm install
copy .env.example .env            # optional: only if the backend is not on localhost:8000
npm run dev
```

Open http://localhost:5173.

## Tests and linting

```bash
cd ai-orchestrator
pytest
ruff check app tests
```

The tests do **not** need PostgreSQL, an API key, or network access. They
use an in-memory SQLite database and fake agents, and they ignore your
`.env` file.

GitHub Actions runs the lint, the tests and the frontend build on every
push and pull request (`.github/workflows/ci.yml`).

## Project layout

```
ai-orchestrator/
  app/
    agents/          one file per agent, plus llm_output.py (shared reply parsing)
    api/routes.py    HTTP endpoints
    orchestrator/    service.py: runs the stages, pauses and resumes
    memory/          vector store, learned prompts, agent message bus
    models/          database tables
    schemas/         request / response shapes
    utils/           sandbox for running generated code, background tasks, logging
  frontend/src/
    pages/           one file per screen
    services/api.js  all calls to the backend
  tests/
```

## Running AI-written code safely

The tester runs code that an LLM wrote. `app/utils/sandbox.py` runs it in a
separate process, in a temporary folder, with a time limit, and **without**
the app's environment variables (so it cannot read the API key or database
password). Missing packages are replaced with fakes instead of installed.

This is not full isolation: the code can still read files and use the
network. For that, run the sandbox inside a container (for example Docker
with networking turned off).
