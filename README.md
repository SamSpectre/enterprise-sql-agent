# Enterprise SQL Agent

Natural-language querying over a 2.96M-row PostgreSQL database, built as a production-pattern LangGraph agent with risk classification and human-in-the-loop approval gates.

This is the pattern behind tools like LinkedIn's SQL Bot and Uber's internal data democratization platforms: let non-technical users ask questions in plain English, while keeping guardrails between the LLM and the database.

## Architecture

```
User Query (Natural Language)
         │
         ▼
┌─────────────────────────────────────┐
│         LangGraph Agent             │
│                                     │
│   Schema Introspection              │
│         │                           │
│         ▼                           │
│   Query Generation                  │
│         │                           │
│         ▼                           │
│   Query Validation                  │
│         │                           │
│         ▼                           │
│   Risk Classification               │
│     │           │                   │
│  low risk    sensitive/destructive  │
│     │           │                   │
│     │      Human-in-the-Loop        │
│     │      (approve / reject)       │
│     │           │                   │
│     ▼           ▼                   │
│   Query Execution                   │
│         │                           │
│         ▼                           │
│   Response Formatting               │
└─────────────────────────────────────┘
         │
         ▼
   PostgreSQL — NYC TLC trip data (2.96M rows)
```

## Three agent tiers

| Module | What it adds |
|---|---|
| `src/agent.py` | Core agent: schema introspection → SQL generation → validation → execution |
| `src/agent_with_hitl.py` | Risk classification + LangGraph `interrupt` for human approval of sensitive queries |
| `src/agent_full.py` | Conversation memory (checkpointer + `thread_id`) and query-result caching (normalized SQL → hash → cached result) |

## Key engineering decisions

- **Risk classification before execution** — queries are classified (read vs. mutating vs. expensive) and routed to a human-approval node when they cross the risk threshold. The LLM never gets unmediated write access.
- **Validation loop** — generated SQL is checked and corrected before it touches the database, cutting failed executions and hallucinated column names.
- **Stateful conversations** — LangGraph checkpointing gives multi-turn context ("now break that down by month") without re-deriving schema.
- **Caching** — normalized-SQL hashing avoids re-running identical analytical queries against millions of rows.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY and Postgres connection settings

python scripts/01_download_data.py    # NYC TLC trip data
python scripts/02_setup_database.py   # load into PostgreSQL
python scripts/03_verify_setup.py

python -m src.agent_full              # full agent: memory + cache + HITL
streamlit run app/main.py             # web demo
```

## Stack

Python · LangGraph · LangChain · OpenAI · PostgreSQL · SQLAlchemy · Polars · Streamlit

## Data

[NYC Taxi & Limousine Commission trip records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) — a public dataset large enough (millions of rows) to make query planning, caching, and validation behave like they do in production.

## License

MIT
