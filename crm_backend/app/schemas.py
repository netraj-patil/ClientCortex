from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    connection_id: str


class AskResponse(BaseModel):
    answer: str
    source: Literal["cache", "database"]
    sql: Optional[str] = None
    latency_ms: int


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    db_type: Literal["postgresql", "mysql", "sqlite"] = "postgresql"
    host: Optional[str] = None
    port: Optional[int] = None
    database: str = Field(min_length=1, description="Database name (or file path for sqlite)")
    username: Optional[str] = None
    password: Optional[str] = None

    @model_validator(mode="after")
    def _host_required(self):
        if self.db_type != "sqlite" and not self.host:
            raise ValueError("host is required for this database type")
        return self


class ConnectionOut(BaseModel):
    id: str
    name: str
    db_type: str
    host: Optional[str] = None
    port: Optional[int] = None
    database: str
    username: Optional[str] = None
    created_at: str
    tables: Optional[List[str]] = None
