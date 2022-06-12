import dataclasses
import sqlite3
from typing import Any, Iterable, Optional, Tuple
from everything import SM64Everything

from model import SM64Model
from object import SM64Object


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
