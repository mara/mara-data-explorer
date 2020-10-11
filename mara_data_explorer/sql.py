"""Database agnostic query functions"""

from functools import singledispatch

import sqlalchemy

import mara_db.dbs


def quote_identifier(db: mara_db.dbs.DB, name: str):
    """Quotes a column name or table name for the right dialect of the database"""
    from mara_db import sqlalchemy_engine

    return sqlalchemy_engine.engine(db).dialect.identifier_preparer.quote(name)


def quote_text_literal(db: mara_db.dbs.DB, text: str):
    from mara_db import sqlalchemy_engine

    return sqlalchemy.TEXT().literal_processor(sqlalchemy_engine.engine(db).dialect)(text)


# execute_query

@singledispatch
def execute_query(db: mara_db.dbs.DB, sql_statement: str) -> ([], [str]):
    """
    Execute an sql statement and return the result as an array
    Args:
        db: The database to query
        sql_statement: The sql statement to execute

    Returns:
        The rows as an array and the column names
    """
    raise NotImplementedError(f'Please implement execute_query for type "{db.__class__.__name__}"')


@execute_query.register(str)
def __(db: str, sql_statement: str):
    return execute_query(mara_db.dbs.db(db), sql_statement)


@execute_query.register(mara_db.dbs.BigQueryDB)
def __(db: mara_db.dbs.BigQueryDB, sql_stament: str):
    from mara_db.bigquery import bigquery_cursor_context

    with bigquery_cursor_context(db) as cursor:
        cursor.execute(sql_stament)
        return [list(row) for row in cursor.fetchall()], [column.name for column in cursor.description]


@execute_query.register(mara_db.dbs.PostgreSQLDB)
def __(db: mara_db.dbs.PostgreSQLDB, sql_stament: str):
    with mara_db.postgresql.postgres_cursor_context(db) as cursor:
        cursor.execute(sql_stament)
        return cursor.fetchall(), [column[0] for column in cursor.description]


# row_count

@singledispatch
def row_count(db: mara_db.dbs.DB, database_schema: str, database_table: str) -> int:
    """Returns the total number of rows in a database table"""
    raise NotImplementedError(f'Please implement row_count for type "{db.__class__.__name__}"')


@row_count.register(str)
def __(db: str, database_schema: str, database_table: str) -> int:
    """Extracts a list of column definitions from a database"""
    return row_count(mara_db.dbs.db(db), database_schema, database_table)


@row_count.register(mara_db.dbs.BigQueryDB)
def __(db: mara_db.dbs.BigQueryDB, database_schema: str, database_table: str):
    from mara_db.bigquery import bigquery_client

    client = bigquery_client(db)
    table = client.get_table(f'{database_schema}.{database_table}')

    return table.num_rows


@row_count.register(mara_db.dbs.PostgreSQLDB)
def __(db: mara_db.dbs.PostgreSQLDB, database_schema: str, database_table: str):
    with mara_db.postgresql.postgres_cursor_context(db) as cursor:
        cursor.execute(f'SELECT count(*) FROM "{database_schema}"."{database_table}"')
        return cursor.fetchone()[0]
