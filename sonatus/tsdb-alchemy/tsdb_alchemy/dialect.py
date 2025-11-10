"""
Extremely hacky implementation of SQLAlchemy db driver.
Lots of trial and error to cover TSDB current shortcomings (like no prepared statements, no flight-info for reflection, no full schema information in the information_schema)
Added tracing for all functions as debugging under full blown superset is very hard.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Mapping, MutableMapping, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Connection, default
from sqlalchemy.engine.url import URL
from sqlalchemy.sql import sqltypes
from sqlalchemy.sql import compiler
from sqlalchemy import bindparam
from sqlalchemy import pool

# Set up debug logging by default
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


_DEFAULT_GRPC_PORT = 32010
_TYPE_FALLBACK = sqltypes.String()


def _lower(value: str) -> str:
    """Normalize a type string to lowercase for matching."""
    logger.warning("_lower() entry: value=%r", value)
    result = value.lower()
    logger.warning("_lower() exit: result=%r", result)
    return result


def _make_type(type_name: str) -> sqltypes.TypeEngine:
    """Return a SQLAlchemy type instance for a DataFusion type string."""
    logger.warning("_make_type() entry: type_name=%r", type_name)

    normalized = _lower(type_name)
    if normalized in {"bool", "boolean"}:
        result = sqltypes.Boolean()
        return result
    if normalized in {
        "int8",
        "int16",
        "int32",
        "int64",
        "tinyint",
        "smallint",
        "integer",
        "bigint",
    }:
        if normalized in {"int8", "tinyint"}:
            result = sqltypes.SmallInteger()
            return result
        if normalized in {"int16", "smallint"}:
            result = sqltypes.SmallInteger()
            return result
        if normalized in {"int32", "integer"}:
            result = sqltypes.Integer()
            return result
        result = sqltypes.BigInteger()
        return result
    if normalized in {"uint8", "uint16", "uint32", "uint64"}:
        if normalized == "uint64":
            result = sqltypes.BigInteger()
            return result
        result = sqltypes.Integer()
        return result
    if normalized in {"float", "float32", "float64", "double"}:
        if normalized in {"float", "float32"}:
            result = sqltypes.Float()
            return result
        result = sqltypes.Float()
        return result
    if normalized.startswith("decimal") or normalized.startswith("numeric"):
        result = sqltypes.Numeric()
        return result
    if normalized.startswith("timestamp"):
        result = sqltypes.DateTime()
        return result
    if normalized.startswith("date"):
        result = sqltypes.Date()
        return result
    if normalized.startswith("time"):
        result = sqltypes.Time()
        return result
    if normalized in {"utf8", "largeutf8", "string", "varchar"}:
        result = sqltypes.String()
        return result
    if normalized in {"binary", "largebinary"}:
        result = sqltypes.LargeBinary()
        return result
    if (
        normalized.startswith("list")
        or normalized.startswith("struct")
        or normalized.startswith("map")
    ):
        result = sqltypes.JSON()
        return result
    result = _TYPE_FALLBACK
    logger.warning("_make_type() exit: result=%r (fallback)", result)
    return result


def _coerce_schema(schema: str | None) -> str | None:
    """Normalize schema names used by reflection."""
    if schema == "":
        return None
    return schema


import logging
from sqlalchemy.sql import compiler
from sqlalchemy.types import String, NullType, Integer  # Add any types you need
from sqlalchemy import bindparam as create_bindparam  # Import the bindparam constructor

logger = logging.getLogger(__name__)


class LiteralBindCompiler(compiler.SQLCompiler):

    def __init__(self, dialect, statement, column_keys=None, **kwargs):
        super().__init__(dialect, statement, column_keys=column_keys, **kwargs)

    def visit_bindparam(
        self, bindparam, within_columns_clause=False, literal_binds=False, **kwargs
    ):
        force_literal_binds = True
        return super().visit_bindparam(
            bindparam,
            within_columns_clause=within_columns_clause,
            literal_binds=force_literal_binds,
            **kwargs,
        )


class TSDBDialect(default.DefaultDialect):
    """SQLAlchemy dialect backed by the FlightSQL ADBC DB-API."""

    name = "flightsql"
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
    default_schema_name = "all"
    # statement_compiler = LiteralBindCompiler

    @classmethod
    def dbapi(cls):  # type: ignore[override]
        """Return the FlightSQL DB-API module."""
        logger.warning("TSDBDialect.dbapi() entry")
        from adbc_driver_flightsql import dbapi  # type: ignore[import-not-found]

        logger.warning("TSDBDialect.dbapi() exit: dbapi=%r", dbapi)
        return dbapi

    def create_connect_args(
        self, url: URL
    ) -> Tuple[Sequence[object], Mapping[str, object]]:
        """Translate a SQLAlchemy URL into DB-API connect keyword arguments."""
        logger.warning("TSDBDialect.create_connect_args() entry: url=%r", url)
        logger.warning(
            "create_connect_args: url.host=%r, url.port=%r, url.database=%r",
            url.host,
            url.port,
            url.database,
        )

        query: MutableMapping[str, object] = dict(url.query)
        uri = query.pop("uri", None)
        transport = str(query.pop("transport", "grpc")).replace(" ", "+")
        logger.warning("create_connect_args: uri=%r, transport=%r", uri, transport)
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
            logger.warning("create_connect_args: constructed uri=%r", uri)

        connect_args: Dict[str, object] = {"uri": uri}
        if url.username:
            connect_args["user"] = url.username
        if url.password:
            connect_args["password"] = url.password
        connect_args.update(query)

        # Create a sanitized version for logging
        log_connect_args = {k: v for k, v in connect_args.items() if k != "password"}
        result = ([], connect_args)
        logger.warning(
            "TSDBDialect.create_connect_args() exit: result=%r", ([], log_connect_args)
        )
        return result

    def do_execute(self, cursor, statement, parameters, context=...):
        logger.warning(
            "TSDBDialect.do_execute() entry: statement=%r, parameters=%r, context=%r",
            statement,
            parameters,
            context,
        )
        return super().do_execute(cursor, statement, parameters, context)

    def do_ping(self, dbapi_connection) -> bool:  # type: ignore[override]
        """Call a lightweight query to validate connectivity."""
        logger.warning(
            "TSDBDialect.do_ping() entry: dbapi_connection=%r", dbapi_connection
        )

        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            result = True
            logger.warning("TSDBDialect.do_ping() exit: result=%r (success)", result)
            return result
        except Exception as e:
            logger.warning("TSDBDialect.do_ping() exception: %r", e)
            raise
        finally:
            cursor.close()

    def has_table(
        self, connection: Connection, table_name: str, schema: str | None = None, **kw
    ) -> bool:
        """Return whether a table exists in the target schema."""
        logger.warning(
            "TSDBDialect.has_table() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        target_schema = _coerce_schema(schema)
        if target_schema is None:
            target_schema = self.default_schema_name
        logger.warning("has_table: target_schema=%r", target_schema)

        stmt = text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table LIMIT 1"
        ).bindparams(
            bindparam(
                "schema", value=target_schema, type_=String(), literal_execute=True
            ),
            bindparam("table", value=table_name, type_=String(), literal_execute=True),
        )
        logger.warning("has_table: executing stmt=%r", stmt)

        result = connection.execute(stmt)
        try:
            exists = result.fetchone() is not None
            logger.warning("TSDBDialect.has_table() exit: result=%r", exists)
        finally:
            result.close()
        return exists

    def get_schema_names(self, connection: Connection, **kw) -> List[str]:
        """Fetch available schemas from information_schema."""
        logger.warning("TSDBDialect.get_schema_names() entry: kw=%r", kw)
        stmt = text(
            "SELECT DISTINCT table_schema FROM information_schema.tables "
            "WHERE table_schema NOT IN ('information_schema') ORDER BY table_schema"
        )
        result = connection.execute(stmt)
        schemas = [row[0] for row in result if row[0]]
        logger.warning("TSDBDialect.get_schema_names() exit: result=%r", schemas)
        return schemas

    def _get_table_or_view_names(
        self, connection: Connection, table_type: str, schema: str | None, **kw
    ) -> List[str]:
        """Common method to return table or view names for the given schema."""
        method_name = f"get_{table_type.lower()}_names"
        logger.warning(
            f"TSDBDialect.{method_name}() entry: schema=%r, kw=%r, canary", schema, kw
        )
        target_schema = _coerce_schema(schema)
        logger.warning(f"{method_name}: target_schema=%r", target_schema)
        if target_schema is None:
            stmt = text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('information_schema') AND table_type = :table_type "
                "ORDER BY table_name"
            ).bindparams(
                bindparam(
                    "table_type", value=table_type, type_=String(), literal_execute=True
                )
            )
        else:
            stmt = text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = :schema AND table_type = :table_type ORDER BY table_name"
            ).bindparams(
                bindparam(
                    "schema", value=target_schema, type_=String(), literal_execute=True
                ),
                bindparam(
                    "table_type", value=table_type, type_=String(), literal_execute=True
                ),
            )

        logger.warning(f"{method_name}: executing stmt=%r", stmt)
        result = connection.execute(stmt)

        items = [row[0] for row in result]
        logger.warning(f"TSDBDialect.{method_name}() exit: result=%r", items)
        return items

    def get_table_names(
        self, connection: Connection, schema: str | None = None, **kw
    ) -> List[str]:
        """Return table names for the given schema."""
        return self._get_table_or_view_names(connection, "BASE TABLE", schema, **kw)

    def get_view_names(
        self, connection: Connection, schema: str | None = None, **kw
    ) -> List[str]:
        """Return view names for the given schema."""
        return self._get_table_or_view_names(connection, "VIEW", schema, **kw)

    def get_columns(
        self, connection: Connection, table_name: str, schema: str | None = "all", **kw
    ) -> List[Dict[str, object]]:
        """Retrieve column metadata for a table."""
        logger.warning(
            "TSDBDialect.get_columns() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        target_schema = _coerce_schema(schema)
        if schema is None:
            target_schema = self.default_schema_name
        stmt = text(
            "SELECT column_name, is_nullable, data_type, column_default, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table "
            "ORDER BY ordinal_position"
        ).bindparams(
            bindparam(
                "schema", value=target_schema, type_=String(), literal_execute=True
            ),
            bindparam("table", value=table_name, type_=String(), literal_execute=True),
        )
        logger.warning("get_columns: executing stmt=%r", stmt)

        rows = connection.execute(stmt)
        columns: List[Dict[str, object]] = []
        for row in rows:
            data_type = str(row[2]) if row[2] is not None else ""
            column_info = {
                "name": str(row[0]),
                "type": _make_type(data_type),
                "nullable": str(row[1]).upper() == "YES",
                "default": row[3],
            }
            logger.warning("get_columns: processed column=%r", column_info)
            columns.append(column_info)

        logger.warning("TSDBDialect.get_columns() exit: result=%r", columns)
        return columns

    def get_pk_constraint(
        self, connection: Connection, table_name: str, schema: str | None = "all", **kw
    ) -> Dict[str, object]:
        """Return the primary key constraint definition (none for TSDB)."""
        logger.warning(
            "TSDBDialect.get_pk_constraint() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        # NOTE: there are no PK constraints for DataFusion tables
        return {}

    def get_foreign_keys(
        self, connection: Connection, table_name: str, schema: str | None = "all", **kw
    ) -> List[Dict[str, object]]:
        """Return foreign key constraints (none for TSDB)."""
        logger.warning(
            "TSDBDialect.get_foreign_keys() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        return []

    def get_indexes(
        self, connection: Connection, table_name: str, schema: str | None = "all", **kw
    ) -> List[Dict[str, object]]:
        """Return index constraints."""
        logger.warning(
            "TSDBDialect.get_indexes() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        #  no index support
        return []

    def get_unique_constraints(
        self, connection: Connection, table_name: str, schema: str | None = "all", **kw
    ) -> List[Dict[str, object]]:
        """Return unique constraints."""
        logger.warning(
            "TSDBDialect.get_unique_constraints() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        # no unique constraint support
        return []

    def get_check_constraints(
        self, connection: Connection, table_name: str, schema: str | None = "all", **kw
    ) -> List[Dict[str, object]]:
        """Return check constraints."""
        logger.warning(
            "TSDBDialect.get_check_constraints() entry: table_name=%r, schema=%r, kw=%r",
            table_name,
            schema,
            kw,
        )
        # no check constraint support
        return []

    # def get_table_comment(
    #     self, connection: Connection, table_name: str, schema: str | None = "all", **kw
    # ) -> Dict[str, object]:
    #     """Return table comment."""
    #     logger.warning(
    #         "TSDBDialect.get_table_comment() entry: table_name=%r, schema=%r, kw=%r",
    #         table_name,
    #         schema,
    #         kw,
    #     )
    #     # Return empty dict if no comment support
    #     return {}

    def get_view_definition(
        self, connection: Connection, view_name: str, schema: str | None = "all", **kw
    ) -> str | None:
        """Return the view's SQL definition."""
        logger.warning(
            "TSDBDialect.get_view_definition() entry: view_name=%r, schema=%r, kw=%r",
            view_name,
            schema,
            kw,
        )
        # Return None if not supported
        return None

    def initialize(self, connection):
        super().initialize(connection)
        # Use the literal binding SQL compiler as we don't support prepared statements. 
        self.statement_compiler = LiteralBindCompiler

    def _get_default_schema_name(self, connection):
        return "all"


def register_dialect() -> None:
    """Register the FlightSQL dialect with SQLAlchemy."""
    logger.warning("register_dialect() entry")

    from sqlalchemy.dialects import registry

    registry.register("tsdb", __name__, "TSDBDialect")
    logger.warning("register_dialect() exit: dialect registered")


register_dialect()
