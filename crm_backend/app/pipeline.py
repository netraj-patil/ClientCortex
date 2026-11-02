"""Cache-miss path: generate SQL -> validate -> run (read-only) -> turn the rows into an answer.

Same three stages as the original generate / check / execute graph, as plain functions.
The SQL check is done with a parser instead of a second LLM call.
"""
import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import sqlglot
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp

from . import config, db

SQLGLOT_DIALECTS = {"postgresql": "postgres", "mysql": "mysql", "sqlite": "sqlite"}

_SET_OPS = tuple(getattr(exp, n) for n in ("Union", "Except", "Intersect") if hasattr(exp, n))
_FORBIDDEN = tuple(
    getattr(exp, n)
    for n in ("Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge", "Into", "Command", "Copy", "TruncateTable")
    if hasattr(exp, n)
)


class PipelineError(Exception):
    """The question could not be turned into a safe, working query."""


@dataclass
class Answer:
    answer: str
    sql: str
    tables: List[str]
    fingerprints: Dict[str, str]


class SQLOutput(BaseModel):
    sql: str = Field(description="One read-only SQL SELECT query and nothing else")


_llm = None


def get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        if not config.GROQ_API_KEY:
            raise PipelineError("GROQ_API_KEY is not set")
        _llm = ChatGroq(model=config.LLM_MODEL, temperature=0)
    return _llm


# ---- stage 1: generate ----------------------------------------------------

def generate_sql(question: str, schema: str, dialect: str, previous_error: Optional[str] = None) -> str:
    prompt = (
        f"You are an expert {dialect} query writer for a CRM database.\n\n"
        f"Database schema:\n{schema}\n\n"
        "Rules:\n"
        "- Write exactly one SELECT query. Never modify data or schema.\n"
        "- Use only the tables and columns that appear in the schema.\n"
        f"- Add LIMIT {config.QUERY_ROW_LIMIT} unless the query is an aggregate.\n"
        "- Return only the query.\n"
    )
    if previous_error:
        prompt += f"\nYour previous attempt failed with: {previous_error}\nFix the query.\n"
    prompt += f"\nQuestion: {question}"
    # return get_llm().with_structured_output(SQLOutput).invoke(prompt).sql
    return str(get_llm().invoke(prompt).content)


# ---- stage 2: validate ----------------------------------------------------

def validate_sql(sql: str, dialect: str, known_tables: Iterable[str]) -> Tuple[str, List[str]]:
    """Allow a single read-only SELECT over known tables. Returns (clean_sql, tables_used)."""
    sql = sql.replace("```sql", "").replace("```", "").strip().rstrip(";").strip()
    if not sql:
        raise PipelineError("The model returned an empty query")
    try:
        statements = [s for s in sqlglot.parse(sql, read=SQLGLOT_DIALECTS.get(dialect)) if s is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise PipelineError(f"Could not parse the generated SQL: {exc}")
    if len(statements) != 1:
        raise PipelineError("Exactly one SQL statement is allowed")

    stmt = statements[0]
    if not isinstance(stmt, (exp.Select,) + _SET_OPS):
        raise PipelineError("Only SELECT queries are allowed")
    if next(stmt.find_all(*_FORBIDDEN), None) is not None:
        raise PipelineError("Only read-only SELECT queries are allowed")

    lookup = {t.lower(): t for t in known_tables}
    cte_names = {c.alias_or_name.lower() for c in stmt.find_all(exp.CTE)}
    used = set()
    for table in stmt.find_all(exp.Table):
        name = table.name
        if not name or name.lower() in cte_names:
            continue
        if name.lower() not in lookup:
            raise PipelineError(f"Unknown table: {name}")
        used.add(lookup[name.lower()])
    if not used:
        raise PipelineError("The query does not read from any table")
    return sql, sorted(used)


# ---- stage 3: execute + explain ------------------------------------------

def run_query(ro_engine, sql: str) -> Tuple[List[dict], bool]:
    try:
        with ro_engine.connect() as conn:
            # Escape ':' so SQLAlchemy's text() never mistakes part of the query for a bind parameter.
            result = conn.execute(text(sql.replace(":", "\\:")))
            columns = list(result.keys())
            fetched = result.fetchmany(config.QUERY_ROW_LIMIT + 1)
    except SQLAlchemyError as exc:
        raise PipelineError(f"The query failed: {getattr(exc, 'orig', None) or exc}")
    truncated = len(fetched) > config.QUERY_ROW_LIMIT
    rows = [dict(zip(columns, row)) for row in fetched[: config.QUERY_ROW_LIMIT]]
    return rows, truncated


def summarize(question: str, rows: List[dict], truncated: bool) -> str:
    data = json.dumps(rows, default=str)[:12000]
    note = f" (only the first {len(rows)} rows are shown)" if truncated else ""
    prompt = (
        "Answer the user's question in plain, friendly language using only the query result below. "
        "Be concise. If the result is empty, say that no matching records were found. "
        "Do not mention SQL.\n\n"
        f"Question: {question}\nResult{note}: {data}"
    )
    return str(get_llm().invoke(prompt).content).strip()


def answer_question(conn_id: str, question: str) -> Answer:
    _, ro_engine = db.engines(conn_id)
    dialect = ro_engine.dialect.name
    known_tables = inspect(ro_engine).get_table_names()
    if not known_tables:
        raise PipelineError("This database has no tables")
    schema = SQLDatabase(ro_engine, sample_rows_in_table_info=0).get_table_info()

    error = None
    for _attempt in range(2):  # one retry, feeding the error back to the model
        try:
            sql = generate_sql(question, schema, dialect, error)
            sql, tables = validate_sql(sql, dialect, known_tables)
            # Fingerprint before running the query, so a change during the run is still detected.
            fingerprints = {t: db.table_fingerprint(ro_engine, t) for t in tables}
            rows, truncated = run_query(ro_engine, sql)
            break
        except PipelineError as exc:
            error = str(exc)
    else:
        raise PipelineError(f"Could not produce a working query: {error}")

    return Answer(answer=summarize(question, rows, truncated), sql=sql, tables=tables, fingerprints=fingerprints)
