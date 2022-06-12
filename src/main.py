import argparse
import sqlite3
from pathlib import Path
from typing import Optional
from db import write_to_db
from everything import parse_repo


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
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--repo", help="SM64 source repo", required=True)
    parser.add_argument("-d", "--db", help="SQLite database file")
    parser.add_argument(
        "-o", "--overwrite", help="Overwrite database by default", action="store_true"
    )
    args = parser.parse_args()
    run(args.repo, args.db, args.overwrite)


if __name__ == "__main__":
    main()
