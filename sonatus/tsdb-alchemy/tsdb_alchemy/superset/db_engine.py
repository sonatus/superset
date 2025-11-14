from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import types

# from sqlalchemy.engine.reflection import Inspector
from superset.constants import TimeGrain
from superset.db_engine_specs.base import BaseEngineSpec
from superset.utils.core import GenericDataType

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class DqeEngineSpec(BaseEngineSpec):
    engine = "tsdb"
    engine_name = "Distributed Query Engine"
    default_driver = "tsdb"

    sqlalchemy_uri_placeholder = "tsdb://host.docker.internal:52360"

    # DQE-specific column type mappings to ensure float/double types are recognized
    column_type_mappings = (
        (
            re.compile(r"^hugeint", re.IGNORECASE),
            types.BigInteger(),
            GenericDataType.NUMERIC,
        ),
        (
            re.compile(r"^ubigint", re.IGNORECASE),
            types.BigInteger(),
            GenericDataType.NUMERIC,
        ),
        (
            re.compile(r"^uinteger", re.IGNORECASE),
            types.Integer(),
            GenericDataType.NUMERIC,
        ),
        (
            re.compile(r"^usmallint", re.IGNORECASE),
            types.SmallInteger(),
            GenericDataType.NUMERIC,
        ),
        (
            re.compile(r"^utinyint", re.IGNORECASE),
            types.SmallInteger(),
            GenericDataType.NUMERIC,
        ),
    )

    _time_grain_expressions = {
        None: "{col}",
        TimeGrain.SECOND: "DATE_TRUNC('second', {col})",
        TimeGrain.MINUTE: "DATE_TRUNC('minute', {col})",
        TimeGrain.HOUR: "DATE_TRUNC('hour', {col})",
        TimeGrain.DAY: "DATE_TRUNC('day', {col})",
        TimeGrain.WEEK: "DATE_TRUNC('week', {col})",
        TimeGrain.MONTH: "DATE_TRUNC('month', {col})",
        TimeGrain.QUARTER: "DATE_TRUNC('quarter', {col})",
        TimeGrain.YEAR: "DATE_TRUNC('year', {col})",
    }

    @classmethod
    def epoch_to_dttm(cls) -> str:
        # Use TO_TIMESTAMP({col}) for seconds
        # Use TO_TIMESTAMP_MILLIS({col}) for milliseconds
        # Use TO_TIMESTAMP_MICROS({col}) for microseconds
        return "TO_TIMESTAMP({col})"

    @classmethod
    def convert_dttm(
        cls, target_type: str, dttm: datetime, db_extra: dict[str, Any] | None = None
    ) -> str | None:
        sqla_type = cls.get_sqla_column_type(target_type)

        if isinstance(sqla_type, (types.String, types.DateTime)):
            return f"""'{dttm.isoformat(sep=" ", timespec="microseconds")}'"""
        return None

    # @classmethod
    # def get_table_names(
    #     cls, database: Database, inspector: Inspector, schema: str | None
    # ) -> set[str]:
    #     return set(inspector.get_table_names(schema))

    # @staticmethod
    # def get_extra_params(
    #     database: Database, source: QuerySource | None = None
    # ) -> dict[str, Any]:
    #     """
    #     Add a user agent to be used in the requests.
    #     """
    #     extra: dict[str, Any] = BaseEngineSpec.get_extra_params(database)
    #     engine_params: dict[str, Any] = extra.setdefault("engine_params", {})
    #     connect_args: dict[str, Any] = engine_params.setdefault("connect_args", {})
    #     config: dict[str, Any] = connect_args.setdefault("config", {})
    #     custom_user_agent = config.pop("custom_user_agent", "")
    #     delim = " " if custom_user_agent else ""
    #     user_agent = get_user_agent(database, source)
    #     user_agent = user_agent.replace(" ", "-").lower()
    #     version_string = app.config["VERSION_STRING"]
    #     user_agent = f"{user_agent}/{version_string}{delim}{custom_user_agent}"
    #     config.setdefault("custom_user_agent", user_agent)

    #     return extra

    # @classmethod
    # def get_function_names(
    #     cls,
    #     database: Database,
    # ) -> list[str]:
    #     """
    #     Return function names.
    #     """
    #     return [
    #         "abs",
    #         "acos",
    #         "acosh",
    #         "asin",
    #         "asinh",
    #         "atan",
    #         "atan2",
    #         "atanh",
    #         "avg",
    #         "ceil",
    #         "ceiling",
    #         "changes",
    #         "char",
    #         "coalesce",
    #         "cos",
    #         "cosh",
    #         "count",
    #         "cume_dist",
    #         "date",
    #         "datetime",
    #         "degrees",
    #         "dense_rank",
    #         "exp",
    #         "first_value",
    #         "floor",
    #         "format",
    #         "glob",
    #         "group_concat",
    #         "hex",
    #         "ifnull",
    #         "iif",
    #         "instr",
    #         "json",
    #         "json_array",
    #         "json_array_length",
    #         "json_each",
    #         "json_error_position",
    #         "json_extract",
    #         "json_group_array",
    #         "json_group_object",
    #         "json_insert",
    #         "json_object",
    #         "json_patch",
    #         "json_quote",
    #         "json_remove",
    #         "json_replace",
    #         "json_set",
    #         "json_tree",
    #         "json_type",
    #         "json_valid",
    #         "julianday",
    #         "lag",
    #         "last_insert_rowid",
    #         "last_value",
    #         "lead",
    #         "length",
    #         "like",
    #         "likelihood",
    #         "likely",
    #         "ln",
    #         "load_extension",
    #         "log",
    #         "log10",
    #         "log2",
    #         "lower",
    #         "ltrim",
    #         "max",
    #         "min",
    #         "mod",
    #         "nth_value",
    #         "ntile",
    #         "nullif",
    #         "percent_rank",
    #         "pi",
    #         "pow",
    #         "power",
    #         "printf",
    #         "quote",
    #         "radians",
    #         "random",
    #         "randomblob",
    #         "rank",
    #         "replace",
    #         "round",
    #         "row_number",
    #         "rtrim",
    #         "sign",
    #         "sin",
    #         "sinh",
    #         "soundex",
    #         "sqlite_compileoption_get",
    #         "sqlite_compileoption_used",
    #         "sqlite_offset",
    #         "sqlite_source_id",
    #         "sqlite_version",
    #         "sqrt",
    #         "strftime",
    #         "substr",
    #         "substring",
    #         "sum",
    #         "tan",
    #         "tanh",
    #         "time",
    #         "total_changes",
    #         "trim",
    #         "trunc",
    #         "typeof",
    #         "unhex",
    #         "unicode",
    #         "unixepoch",
    #         "unlikely",
    #         "upper",
    #         "zeroblob",
    #     ]
