from __future__ import annotations

import logging
import weakref
from typing import Any, Mapping, MutableMapping, Sequence

from sqlalchemy import bindparam, pool, text
from sqlalchemy.engine import Connection, default
from sqlalchemy.engine.url import URL
from sqlalchemy.sql import compiler
from sqlalchemy.types import String

# Import the real driver at module level (or inside dbapi if lazy loading is preferred)
try:
    from adbc_driver_flightsql import dbapi as _adbc_dbapi
except ImportError:
    _adbc_dbapi = None

from .helpers import coerce_schema, make_type

logger = logging.getLogger(__name__)
_DEFAULT_GRPC_PORT = 32010


logger = logging.getLogger(__name__)

_DEFAULT_GRPC_PORT = 32010
logger = logging.getLogger(__name__)


class LiteralBindCompiler(compiler.SQLCompiler):
    def __init__(
        self, dialect: Any, statement: Any, column_keys: Any = None, **kwargs: Any
    ) -> None:
        super().__init__(dialect, statement, column_keys=column_keys, **kwargs)

    def visit_bindparam(
        self,
        bindparam: Any,
        within_columns_clause: bool = False,
        literal_binds: bool = False,
        **kwargs: Any,
    ) -> Any:
        return super().visit_bindparam(
            bindparam,
            within_columns_clause=within_columns_clause,
            literal_binds=True,
            **kwargs,
        )


# Wrapper classes to ensure safe cursor/connection handling with ADBC
class LoggingAdbcCursor:
    """
    Proxy for the ADBC Cursor needed to intercept executed statements.
    """

    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, statement: str, *args: Any, **kwargs: Any) -> Any:
        log_stmt = statement if statement else ""
        logger.info("ADBC:Intercepted SQL statement: %s", log_stmt)
        return self._cursor.execute(statement, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def close(self) -> None:
        self._cursor.close()


class SafeAdbcConnection:
    """
    Wrapper for ADBC Connection.

    Solves the 'NullPool' crash by tracking open cursors and forcibly
    closing them before closing the connection itself.
    """

    def __init__(self, wrapped_conn: Any):
        self._conn = wrapped_conn
        # WeakSet tracks cursors without preventing Garbage Collection
        self._cursors: weakref.WeakSet[Any] = weakref.WeakSet()

    def cursor(self) -> Any:
        real_cursor = self._conn.cursor()
        safe_cursor = LoggingAdbcCursor(real_cursor)

        # Track the REAL cursor, not the wrapper, so we can close the backend resource
        self._cursors.add(real_cursor)
        return safe_cursor

    def close(self) -> None:
        """
        Safely close all cursors before closing the connection.
        CRITICAL: This prevents 'RuntimeError: Cannot close AdbcConnection'
        when using NullPool by ensuring all cursors are closed first.
        """
        for c in self._cursors:
            try:
                c.close()
            except Exception:
                logging.warning("Cursor might already be closed or invalid; ignore.")
                pass

        # Now it is safe to close the connection
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class TSDBDialect(default.DefaultDialect):
    """SQLAlchemy dialect backed by the FlightSQL ADBC DB-API."""

    name = "tsdb"
    driver = "adbc"
    default_paramstyle = "qmark"
    poolclass = pool.SingletonThreadPool
    supports_native_decimal = True
    supports_server_side_cursors = False
    returns_unicode_strings = True
    supports_default_values = False
    supports_empty_insert = False
    supports_native_boolean = True
    supports_pk_autoincrement = False
    supports_statement_cache = True
    supports_unicode_binds = True
    supports_unicode_statements = True
    supports_sane_rowcount = False
    supports_sane_multi_rowcount = False

    @classmethod
    def dbapi(cls) -> Any:
        """Return the FlightSQL patched DB-API module."""
        logger.debug("TSDBDialect.dbapi() entry")

        if _adbc_dbapi is None:
            raise ImportError("adbc_driver_flightsql is not installed.")

        # If we haven't patched the connect method yet, do it now.
        # We check a custom flag to avoid double-wrapping if dbapi() is called twice.
        if not getattr(_adbc_dbapi, "_is_wrapped_by_tsdb", False):
            original_connect = _adbc_dbapi.connect

            def connect_wrapper(*args: Any, **kwargs: Any) -> SafeAdbcConnection:
                connection = original_connect(*args, **kwargs)
                return SafeAdbcConnection(connection)

            _adbc_dbapi.connect = connect_wrapper
            _adbc_dbapi._is_wrapped_by_tsdb = True

        return _adbc_dbapi

    def create_connect_args(
        self, url: URL
    ) -> tuple[Sequence[object], Mapping[str, object]]:
        """Translate a SQLAlchemy URL into DB-API connect keyword arguments."""
        logger.debug(
            "TSDBDialect.create_connect_args: url.host=%r,url.port=%r,url.database=%r",
            url.host,
            url.port,
            url.database,
        )

        query: MutableMapping[str, object] = dict(url.query)
        uri = query.pop("uri", None)
        transport = str(query.pop("transport", "grpc")).replace(" ", "+")
        if uri is None:
            host = url.host or "localhost"
            port = url.port or (
                443 if transport.endswith("+tls") else _DEFAULT_GRPC_PORT
            )
            uri = f"{transport}://{host}"
            if port:
                uri = f"{uri}:{port}"
            if url.database:
                uri = f"{uri}/{url.database}"

        connect_args: dict[str, object] = {"uri": uri}
        if url.username:
            connect_args["user"] = url.username
        if url.password:
            connect_args["password"] = url.password
        connect_args.update(query)

        # Create a sanitized version for logging
        log_connect_args = {k: v for k, v in connect_args.items() if k != "password"}
        result: tuple[list[object], dict[str, object]] = ([], connect_args)
        logger.debug(
            "TSDBDialect.create_connect_args() exit: result=%r", ([], log_connect_args)
        )
        return result

    def do_execute(
        self, cursor: Any, statement: Any, parameters: Any, context: Any = ...
    ) -> Any:
        logger.debug(
            "TSDBDialect.do_execute() entry: statement=%r, parameters=%r, context=%r",
            statement,
            parameters,
            context,
        )
        return super().do_execute(cursor, statement, parameters, context)

    def do_ping(self, dbapi_connection: Any) -> bool:
        """Call a lightweight query to validate connectivity."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            result = True
            logger.debug("TSDBDialect.do_ping() exit: result=%r (success)", result)
            return result
        except Exception as e:
            logger.debug("TSDBDialect.do_ping() exception: %r", e)
            return False
        finally:
            cursor.close()

    def has_table(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = None,
        **kw: Any,
    ) -> bool:
        """Return whether a table exists in the target schema."""
        logger.debug(
            "TSDBDialect.has_table() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        target_schema = coerce_schema(schema)
        if target_schema is None:
            target_schema = self.default_schema_name
        logger.debug("has_table: target_schema=%r", target_schema)

        stmt = text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table LIMIT 1"
        ).bindparams(
            bindparam(
                "schema", value=target_schema, type_=String(), literal_execute=True
            ),
            bindparam("table", value=table_name, type_=String(), literal_execute=True),
        )
        logger.debug("has_table: executing stmt=%r", stmt)

        result = connection.execute(stmt)
        try:
            exists = result.fetchone() is not None
            logger.debug("TSDBDialect.has_table() exit: result=%r", exists)
        finally:
            result.close()
        return exists

    def get_schema_names(self, connection: Connection, **kw: Any) -> list[str]:
        """Fetch available schemas from information_schema."""
        logger.debug("TSDBDialect.get_schema_names() entry: kw=%r", kw)
        stmt = text(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_schema NOT IN ('information_schema') ORDER BY table_schema"
        )
        result = connection.execute(stmt)
        schemas = [row[0] for row in result if row[0]]
        logger.debug("TSDBDialect.get_schema_names() exit: result=%r", schemas)
        return schemas

    def _get_table_or_view_names(
        self, connection: Connection, table_type: str, schema: str | None, **kw: Any
    ) -> list[str]:
        """Common method to return table or view names for the given schema."""
        method_name = f"get_{table_type.lower()}_names"
        logger.debug(
            f"TSDBDialect.{method_name}() entry: schema=%r, kw=%r, canary", schema, kw
        )
        target_schema = coerce_schema(schema)
        logger.debug(f"{method_name}: target_schema=%r", target_schema)
        if target_schema is None:
            stmt = text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('information_schema') "
                "AND table_type = :table_type "
                "ORDER BY table_name"
            ).bindparams(
                bindparam(
                    "table_type", value=table_type, type_=String(), literal_execute=True
                )
            )
        else:
            stmt = text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema "
                "AND table_type = :table_type ORDER BY table_name"
            ).bindparams(
                bindparam(
                    "schema", value=target_schema, type_=String(), literal_execute=True
                ),
                bindparam(
                    "table_type", value=table_type, type_=String(), literal_execute=True
                ),
            )

        result = connection.execute(stmt)

        items = [row[0] for row in result]
        logger.debug(f"TSDBDialect.{method_name}() exit: result=%r", items)
        return items

    def get_table_names(
        self, connection: Connection, schema: str | None = None, **kw: Any
    ) -> list[str]:
        """Return table names for the given schema."""
        return self._get_table_or_view_names(connection, "BASE TABLE", schema, **kw)

    def get_view_names(
        self, connection: Connection, schema: str | None = None, **kw: Any
    ) -> list[str]:
        """Return view names for the given schema."""
        return self._get_table_or_view_names(connection, "VIEW", schema, **kw)

    def get_columns(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = "all",
        **kw: Any,
    ) -> list[dict[str, object]]:
        """Retrieve column metadata for a table."""
        logger.debug(
            "TSDBDialect.get_columns() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        target_schema = coerce_schema(schema)
        if schema is None:
            target_schema = self.default_schema_name
        stmt = text(
            "SELECT column_name, is_nullable, data_type, "
            "column_default, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table "
            "ORDER BY ordinal_position"
        ).bindparams(
            bindparam(
                "schema", value=target_schema, type_=String(), literal_execute=True
            ),
            bindparam("table", value=table_name, type_=String(), literal_execute=True),
        )

        rows = connection.execute(stmt)
        columns: list[dict[str, object]] = []
        for row in rows:
            data_type = str(row[2]) if row[2] is not None else ""
            column_info = {
                "name": str(row[0]),
                "type": make_type(data_type),
                "nullable": str(row[1]).upper() == "YES",
                "default": row[3],
            }
            columns.append(column_info)
        logger.debug("TSDBDialect.get_columns() exit: result=%r", columns)
        return columns

    def get_pk_constraint(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = "all",
        **kw: Any,
    ) -> dict[str, object]:
        """Return the primary key constraint definition (none for TSDB)."""
        logger.debug(
            "TSDBDialect.get_pk_constraint() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        # NOTE: there are no PK constraints for DataFusion tables
        return {}

    def get_foreign_keys(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = "all",
        **kw: Any,
    ) -> list[dict[str, object]]:
        """Return foreign key constraints (none for TSDB)."""
        logger.debug(
            "TSDBDialect.get_foreign_keys() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        return []

    def get_indexes(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = "all",
        **kw: Any,
    ) -> list[dict[str, object]]:
        """Return index constraints."""
        logger.debug(
            "TSDBDialect.get_indexes() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        #  no index support
        return []

    def get_unique_constraints(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = "all",
        **kw: Any,
    ) -> list[dict[str, object]]:
        """Return unique constraints."""
        logger.debug(
            "TSDBDialect.get_unique_constraints() entry: "
            "table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        # no unique constraint support
        return []

    def get_check_constraints(
        self,
        connection: Connection,
        table_name: str,
        schema: str | None = "all",
        **kw: Any,
    ) -> list[dict[str, object]]:
        """Return check constraints."""
        logger.debug(
            "TSDBDialect.get_check_constraints() entry: "
            "table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        # no check constraint support
        return []

    # TODO: Use table comments to provide DBC information
    #  for AI Agents to build up context
    # def get_table_comment(
    #     self, connection: Connection, table_name: str, schema: str | None = "all",
    # **kw
    # ) -> dict[str, object]:
    #     """Return table comment. """
    #     logger.debug(
    #         "TSDBDialect.get_table_comment() entry: table_name=%r, schema=%r, kw=%r",
    #         table_name,
    #         schema,
    #         kw,
    #     )
    #     # Return empty dict if no comment support
    #     return {}

    def get_view_definition(
        self,
        connection: Connection,
        view_name: str,
        schema: str | None = "all",
        **kw: Any,
    ) -> str | None:
        """Return the view's SQL definition."""
        logger.debug(
            "TSDBDialect.get_view_definition() entry: view_name=%r, schema=%r, kw=%r",
            view_name,
            schema,
            kw,
        )
        # Return None if not supported
        return None

    def initialize(self, connection: Any) -> None:
        super().initialize(connection)
        # Use the literal binding SQL compiler as we don't support prepared statements.
        self.statement_compiler = LiteralBindCompiler

    def _get_default_schema_name(self, connection: Any) -> str:
        return "all"


def register_dialect() -> None:
    """Register the FlightSQL dialect with SQLAlchemy."""
    logger.debug("register_dialect() entry")

    from sqlalchemy.dialects import registry

    registry.register("tsdb", __name__, "TSDBDialect")
    logger.debug("register_dialect() exit: dialect registered")


register_dialect()
