import dataclasses
import sqlite3
from typing import Any, Iterable, Optional, Tuple

from sm64_sql.everything import ENTITY_TABLES, SM64Everything


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
        # dataclasses.Field.type is the type object normally, but a string when
        # the module uses `from __future__ import annotations`. Handle both.
        type_name = field.type if isinstance(field.type, str) else field.type.__name__
        sql_type = get_sql_type(type_name)
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
    for table_name, row_type, attr in ENTITY_TABLES:
        create_table(cursor, table_name, dataclasses.fields(row_type))
    for table_name, row_type, attr in ENTITY_TABLES:
        insert_values(
            cursor,
            table_name,
            dataclasses.fields(row_type),
            getattr(everything, attr),
        )
    conn.commit()
