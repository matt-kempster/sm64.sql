import argparse
import sqlite3
from pathlib import Path
from typing import Optional

from sm64_sql import __version__
from sm64_sql.db import write_to_db
from sm64_sql.everything import parse_repo


def check_repo(repo_path: str) -> Path:
    path = Path(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"{repo_path} does not exist")
    if not path.is_dir():
        raise NotADirectoryError(f"{repo_path} is not a directory")
    return path


def run(repo: str, db: Optional[str], overwrite: bool) -> None:
    path = check_repo(repo)
    everything = parse_repo(path)
    if db is not None and Path(db).is_file():
        if not overwrite:
            prompt = input("Database already exists. Overwrite? [y/n]: ")
            if prompt.lower() != "y":
                return
        Path(db).unlink()
    conn = sqlite3.connect(db or ":memory:")
    write_to_db(conn, everything)
    if conn:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sm64-sql",
        description="Load SM64 decompilation game data into a SQLite database.",
    )
    parser.add_argument(
        "-r", "--repo", help="path to the SM64 decompilation source tree", required=True
    )
    parser.add_argument(
        "-d", "--db", help="SQLite file to write (default: in-memory, discarded)"
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        help="overwrite an existing database without prompting",
        action="store_true",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()
    run(args.repo, args.db, args.overwrite)


if __name__ == "__main__":
    main()
