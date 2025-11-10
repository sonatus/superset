# FlightSQL SQLAlchemy Dialect

FlightSQL dialect backed by `adbc-driver-flightsql` for integrating Apache Superset with FlightSQL endpoints.

## Development

```bash
uv sync
uv sync --group dev
uv run pytest
```

Install the package into another project with:

```bash
uv add flightsql-alchemy
```

## Quickstart

```bash
uv sync
uv run pytest
```

Create an engine:

```python
from sqlalchemy import create_engine

engine = create_engine("flightsql://user:pass@localhost:32010?transport=grpc")
```

Superset can use the same SQLAlchemy URI when configuring a new database connection.

## Superset Notes

- Only SQLAlchemy 1.4-style engines are supported; URIs should be formed as `tsdb://user:password@host:port/database`.
- The dialect reflects schemas, tables, and columns via `information_schema` tables, enabling dataset discovery.
- The connection is read-only by default; Superset should rely on datasets for querying.

