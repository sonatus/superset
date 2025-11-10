from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List, Sequence, Tuple
from unittest.mock import patch, MagicMock
from sqlalchemy.engine.url import make_url
from sqlalchemy.sql import sqltypes, text, select, column, table
from sqlalchemy import bindparam
import sqlalchemy

from tsdb_alchemy.dialect import TSDBDialect, LiteralBindCompiler


@dataclass
class FakeResult:
    rows: Sequence[Tuple[object, ...]]
    _index: int = 0

    def fetchone(self):
        if self._index >= len(self.rows):
            return None
        value = self.rows[self._index]
        self._index += 1
        return value

    def __iter__(self) -> Iterator[Tuple[object, ...]]:
        return iter(self.rows)
    
    def close(self):
        pass


class FakeConnection:
    def __init__(self, responses: Dict[str, Sequence[Tuple[object, ...]]]):
        self._responses = responses
        self.calls: List[Tuple[str, Dict[str, object]]] = []

    def execute(self, statement, params=None):
        sql = statement.text if hasattr(statement, "text") else str(statement)
        payload = params or {}
        self.calls.append((sql, dict(payload)))
        return FakeResult(self._responses.get(sql, []))


def test_create_connect_args_with_transport():
    dialect = TSDBDialect()
    url = make_url("flightsql://user:pass@host:5555/db?transport=grpc+tls&foo=bar")
    args, kwargs = dialect.create_connect_args(url)
    assert args == []
    assert kwargs["uri"] == "grpc+tls://host:5555/db"
    assert kwargs["user"] == "user"
    assert kwargs["password"] == "pass"
    assert kwargs["foo"] == "bar"


def test_create_connect_args_docker_host():
    """Test that host.docker.internal is preserved in the URI."""
    dialect = TSDBDialect()
    url = make_url("flightsql://host.docker.internal:52360")
    args, kwargs = dialect.create_connect_args(url)
    assert args == []
    assert kwargs["uri"] == "grpc://host.docker.internal:52360"
    assert "user" not in kwargs



def test_get_columns_maps_types():
    sql = (
        "SELECT column_name, is_nullable, data_type, column_default, ordinal_position "
        "FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table "
        "ORDER BY ordinal_position"
    )
    responses = {
        sql: [
            ("id", "NO", "Int64", None, 1),
            ("name", "YES", "Utf8", None, 2),
        ]
    }
    connection = FakeConnection(responses)
    dialect = TSDBDialect()
    columns = dialect.get_columns(connection, "example")
    assert columns[0]["name"] == "id"
    assert isinstance(columns[0]["type"], sqltypes.BigInteger)
    assert columns[0]["nullable"] is False
    assert isinstance(columns[1]["type"], sqltypes.String)
    assert columns[1]["nullable"] is True


def test_literal_bind_compiler_forces_literal_binds():
    """Test that LiteralBindCompiler replaces bind parameters with literal values."""
    from sqlalchemy import bindparam
    from sqlalchemy.sql import text
    
    # Create a mock dialect instance
    dialect = TSDBDialect()
    
    # Create a LiteralBindCompiler instance
    compiler = LiteralBindCompiler(dialect, text("SELECT * FROM table WHERE id = :id"))
    
    # Create a bind parameter
    bind_param = bindparam("id", value=123)
    
    # Test that visit_bindparam forces literal_binds=True
    result = compiler.visit_bindparam(bind_param, literal_binds=False)
    
    # The result should contain the literal value, not a parameter placeholder
    assert "123" in result
    assert ":id" not in result


def test_flightsql_dialect_uses_literal_bind_compiler():
    """Test that TSDBDialect uses LiteralBindCompiler when prepared_statements_enabled is False."""
    # Create a mock connection
    mock_connection = MagicMock()
    
    # Create dialect instance
    dialect = TSDBDialect()
    
    # Initialize the dialect (this sets the statement_compiler)
    dialect.initialize(mock_connection)
    
    # Verify that LiteralBindCompiler is being used
    assert dialect.statement_compiler == LiteralBindCompiler

