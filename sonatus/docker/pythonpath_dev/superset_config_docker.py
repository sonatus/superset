import logging
from datetime import timedelta

FEATURE_FLAGS = {
    "ALERT_REPORTS": True,
    "ENABLE_SUPERSET_META_DB": True,
}

# Override SUPERSET_LOG_LEVEL envvar
LOG_LEVEL = logging.DEBUG

# The limit for the Superset Meta DB when the feature flag ENABLE_SUPERSET_META_DB is on
SUPERSET_META_DB_LIMIT = 1000
# Maximum number of rows returned for any analytical database query
SQL_MAX_ROW = 100000

# Maximum number of rows for any query with Server Pagination in Table Viz type
TABLE_VIZ_MAX_ROW_SERVER = 500000


# Maximum number of rows displayed in SQL Lab UI
# Is set to avoid out of memory/localstorage issues in browsers. Does not affect
# exported CSVs
DISPLAY_MAX_ROW = 10000

# Default row limit for SQL Lab queries. Is overridden by setting a new limit in
# the SQL Lab UI
DEFAULT_SQLLAB_LIMIT = 1000


# The db id here results in selecting this one as a default in SQL Lab
DEFAULT_DB_ID = None

# Timeout duration for SQL Lab synchronous queries
SQLLAB_TIMEOUT = int(timedelta(seconds=30).total_seconds())

# Timeout duration for SQL Lab query validation
SQLLAB_VALIDATION_TIMEOUT = int(timedelta(seconds=10).total_seconds())

# SQLLAB_DEFAULT_DBID
SQLLAB_DEFAULT_DBID = None

# The MAX duration a query can run for before being killed by celery.
SQLLAB_ASYNC_TIME_LIMIT_SEC = int(timedelta(hours=24).total_seconds())

# Some databases support running EXPLAIN queries that allow users to estimate
# query costs before they run. These EXPLAIN queries should have a small
# timeout.
SQLLAB_QUERY_COST_ESTIMATE_TIMEOUT = int(timedelta(seconds=10).total_seconds())

# Timeout duration for SQL Lab fetching query results by the resultsKey.
# 0 means no timeout.
SQLLAB_QUERY_RESULT_TIMEOUT = 0

PREFERRED_DATABASES: list[str] = [
    "Distributed Query Engine",
    "PostgreSQL",
    "Presto",
    "SQLite",
]
