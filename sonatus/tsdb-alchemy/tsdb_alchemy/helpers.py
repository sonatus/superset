from __future__ import annotations

import logging

from sqlalchemy.sql import sqltypes

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

_TYPE_FALLBACK = sqltypes.String()
_TYPE_MAP: dict[str, sqltypes.TypeEngine] = {
    "bool": sqltypes.Boolean(),
    "boolean": sqltypes.Boolean(),
    "int8": sqltypes.SmallInteger(),
    "tinyint": sqltypes.SmallInteger(),
    "int16": sqltypes.SmallInteger(),
    "smallint": sqltypes.SmallInteger(),
    "int32": sqltypes.Integer(),
    "integer": sqltypes.Integer(),
    "uint8": sqltypes.Integer(),
    "uint16": sqltypes.Integer(),
    "uint32": sqltypes.Integer(),
    "int64": sqltypes.BigInteger(),
    "bigint": sqltypes.BigInteger(),
    "uint64": sqltypes.BigInteger(),
    "float": sqltypes.Float(),
    "float32": sqltypes.Float(),
    "float64": sqltypes.Float(),
    "double": sqltypes.Float(),
    "utf8": sqltypes.String(),
    "largeutf8": sqltypes.String(),
    "string": sqltypes.String(),
    "varchar": sqltypes.String(),
    "binary": sqltypes.LargeBinary(),
    "largebinary": sqltypes.LargeBinary(),
}


def make_type(type_name: str) -> sqltypes.TypeEngine:
    """Return a SQLAlchemy type instance for a DataFusion type string."""
    logger.debug("make_type() entry: type_name=%r", type_name)
    normalized = type_name.lower()

    if (exact_type := _TYPE_MAP.get(normalized)) is not None:
        return exact_type

    match normalized:
        case val if val.startswith(("decimal", "numeric")):
            return sqltypes.Numeric()
        case val if val.startswith("timestamp"):
            return sqltypes.DateTime()
        case val if val.startswith("date"):
            return sqltypes.Date()
        case val if val.startswith("time"):
            return sqltypes.Time()
        case val if val.startswith(("list", "struct", "map")):
            return sqltypes.JSON()
        case _:
            logger.debug("make_type() exit: result=%r (fallback)", _TYPE_FALLBACK)
            return _TYPE_FALLBACK


def coerce_schema(schema: str | None) -> str | None:
    """Normalize schema names used by reflection."""
    if schema == "":
        return None
    return schema
