"""sm64.sql — load Super Mario 64 decompilation game data into a SQLite database."""

from sm64_sql.everything import SM64Everything, parse_repo

__version__ = "0.1.0"

__all__ = ["SM64Everything", "parse_repo", "__version__"]
