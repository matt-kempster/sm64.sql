import argparse
from asyncore import write
from dataclasses import dataclass
import dataclasses
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple
import sqlite3
from venv import create


def check_repo(repo_path: str) -> Path:
    path = Path(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"{repo_path} does not exist")
    if not path.is_dir():
        raise NotADirectoryError(f"{repo_path} is not a directory")
    return path


@dataclass
class SM64Object:
    model_name: str
    level: str
    initial_x: int
    initial_y: int
    initial_z: int
    initial_rot_x: int
    initial_rot_y: int
    initial_rot_z: int
    # TODO: Figure out how to parse this
    # beh_param: int
    behavior: str
    in_act_1: bool
    in_act_2: bool
    in_act_3: bool
    in_act_4: bool
    in_act_5: bool
    in_act_6: bool


def try_parse_object(line: str, level: str) -> Optional[SM64Object]:
    if not line.startswith("OBJECT"):
        return None

    def strip_comments_and_whitespace(line: str) -> str:
        while True:
            comment_start = line.find("/*")
            comment_end = line.find("*/")
            if comment_start == -1 or comment_end == -1:
                break
            line = line[:comment_start] + line[comment_end + 2 :]
        return line.strip()

    def parse_acts(acts: str) -> List[bool]:
        if acts == "ALL_ACTS":
            return [True for _ in range(6)]
        act_presence = [False for _ in range(6)]
        for act_id in acts.split(" | "):
            act = int(act_id[len("ACT_") :])
            act_presence[act - 1] = True
        return act_presence

    has_acts = False
    if line.startswith("OBJECT_WITH_ACTS"):
        has_acts = True
        line = line.replace("OBJECT_WITH_ACTS(", "").replace("),", "")
    else:
        line = line.replace("OBJECT(", "").replace("),", "")
    line_parts = [strip_comments_and_whitespace(part) for part in line.split(",")]
    if len(line_parts) != (10 if has_acts else 9):
        raise ValueError(f"Invalid number of parts ({len(line_parts)}) in line: {line}")

    # If ACT_* not present, the object is in all the acts
    act_presence = parse_acts(line_parts[9]) if has_acts else [True for _ in range(6)]

    return SM64Object(
        level=level,
        model_name=line_parts[0],
        initial_x=int(line_parts[1]),
        initial_y=int(line_parts[2]),
        initial_z=int(line_parts[3]),
        initial_rot_x=int(line_parts[4]),
        initial_rot_y=int(line_parts[5]),
        initial_rot_z=int(line_parts[6]),
        # TODO: Figure out how to parse this
        # beh_param=int(line_parts[7], 16),
        behavior=line_parts[8],
        in_act_1=act_presence[0],
        in_act_2=act_presence[1],
        in_act_3=act_presence[2],
        in_act_4=act_presence[3],
        in_act_5=act_presence[4],
        in_act_6=act_presence[5],
    )


def parse_level(path: Path) -> List[SM64Object]:
    script = (path / "script.c").read_text().splitlines()
    level_name = path.name
    sm64_objects = []
    for line in script:
        line = line.strip()
        if sm64_object := try_parse_object(line, level_name):
            sm64_objects.append(sm64_object)
    return sm64_objects


@dataclass
class SM64Model:
    model_name: str
    model_id: int
    # TODO: include level geo-overriding models


def parse_model_ids(path: Path) -> List[SM64Model]:
    text = path.read_text().splitlines()
    model_ids = []
    for line in text:
        line = line.strip()
        if not line.startswith("#define MODEL_"):
            continue
        parts = line.split()
        model_name = parts[1]
        try:
            model_id_str = parts[2]
        except IndexError:
            if line != "#define MODEL_IDS_H":
                print(f"Invalid line: {line}")
            continue
        if model_id_str.startswith("0x"):
            model_id = int(model_id_str, 16)
        elif model_id_str.isnumeric():
            model_id = int(model_id_str)
        else:
            # TODO: interpret model ids that reference other model ids
            pass
        model_ids.append(SM64Model(model_name, model_id))
    return model_ids


@dataclass
class SM64Everything:
    sm64_objects: List[SM64Object]
    sm64_models: List[SM64Model]


def parse_repo(repo: Path) -> SM64Everything:
    sm64_objects = []
    for level_dir in (repo / "levels").iterdir():
        if level_dir.is_dir():
            sm64_objects_level = parse_level(level_dir)
            sm64_objects.extend(sm64_objects_level)
    model_ids_file = repo / "include" / "model_ids.h"
    sm64_models = parse_model_ids(model_ids_file)
    return SM64Everything(sm64_objects, sm64_models)


def get_sql_type(python_type: str) -> str:
    if python_type == "int":
        return "INTEGER"
    elif python_type == "bool":
        return "INTEGER"
    elif python_type == "str":
        return "TEXT"
    else:
        raise ValueError(f"Unhandled python type: {python_type}")


def create_table(
    cursor: sqlite3.Cursor,
    table_name: str,
    fields: Iterable[dataclasses.Field],
    primary_key: Optional[str] = None,
):
    command = f"CREATE TABLE {table_name} ("
    for field in fields:
        sql_type = get_sql_type(field.type.__name__)
        command += f"{field.name} {sql_type}, "
    if primary_key:
        command += f"PRIMARY KEY {primary_key}"
    else:
        command = command[:-2]
    command += ")"
    cursor.execute(command)


def insert_into_table(
    cursor: sqlite3.Cursor,
    table_name: str,
    row: Tuple[Any, ...],
):
    question_marks = ", ".join(["?" for _ in row])
    command = f"INSERT INTO {table_name} VALUES ({question_marks})"
    cursor.execute(command, row)


def insert_values(
    cursor: sqlite3.Cursor,
    table_name: str,
    fields: Iterable[dataclasses.Field],
    values: Iterable[Any],
):
    for value in values:
        row = tuple(getattr(value, field.name) for field in fields)
        insert_into_table(cursor, table_name, row)


def write_to_db(conn: sqlite3.Connection, everything: SM64Everything) -> None:
    cursor = conn.cursor()
    create_table(
        cursor,
        "object",
        dataclasses.fields(SM64Object),
    )
    create_table(
        cursor,
        "model",
        dataclasses.fields(SM64Model),
    )

    insert_values(
        cursor,
        "object",
        dataclasses.fields(SM64Object),
        everything.sm64_objects,
    )
    insert_values(
        cursor,
        "model",
        dataclasses.fields(SM64Model),
        everything.sm64_models,
    )
    conn.commit()


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
