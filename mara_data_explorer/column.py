from functools import singledispatch

import mara_db.dbs
import sys

class Column():
    """Base class for different database column types"""

    def __init__(self, column_name, type: str):
        """
        A column of a data set

        Args:
            column_name: the corresponding column_name in the database table
            type: The type of the column
        """
        self.column_name = column_name
        self.type = type

    def sortable(self) -> bool:
        """Whether the column is sortable"""
        return self.type not in ['json', 'text[]']

    def to_dict(self):
        return {'column_name': self.column_name, 'type': self.type}

    def __repr__(self):
        return f'<{self.__class__.__name__} "{self.column_name}">'


@singledispatch
def columns(db: mara_db.dbs.DB, database_schema: str, database_table: str) -> {str:Column}:
    """Extracts a list of column definitions from a database"""
    raise NotImplementedError(f'Please implement columns for type "{db.__class__.__name__}"')


@columns.register(str)
def __(db: str, database_schema: str, database_table: str) -> [Column]:
    """Extracts a list of column definitions from a database"""
    return columns(mara_db.dbs.db(db), database_schema, database_table)


@columns.register(mara_db.dbs.PostgreSQLDB)
def __(db: mara_db.dbs.PostgreSQLDB, database_schema, database_table):
    with mara_db.postgresql.postgres_cursor_context(db) as cursor:
        cursor.execute(f"""
SELECT
  att.attname,
  pg_catalog.format_type(atttypid, NULL) AS display_type
FROM pg_attribute att
  JOIN pg_class tbl ON tbl.oid = att.attrelid
  JOIN pg_namespace ns ON tbl.relnamespace = ns.oid
WHERE tbl.relname = {'%s'} AND ns.nspname = {'%s'} AND attnum > 0
ORDER BY attnum""", (database_table, database_schema))

        result = {}

        for column_name, column_type in cursor.fetchall():
            if column_type in ['character varying', 'text']:
                type = 'text'
            elif column_type in ['bigint', 'integer', 'real', 'smallint', 'double precision', 'numeric']:
                type = 'number'
            elif column_type in ['timestamp', 'timestamp with time zone', 'timestamp without time zone',
                                 'time with time zone', 'time without time zone', 'date']:
                type = 'date'
            elif column_type in ['json', 'jsonb']:
                type = 'json'
            elif column_type == 'text[]':
                type = 'text[]'
            else:
                print(f'Unimplemented column type "{column_type}" of "{database_schema}.{database_table}.{column_name}"',
                      sys.stderr)
                continue
            result[column_name] = Column(column_name, type)
        return result

@columns.register(mara_db.dbs.BigQueryDB)
def __(db: mara_db.dbs.BigQueryDB, database_schema, database_table):
    from mara_db.bigquery import bigquery_client

    client = bigquery_client(db)

    table = client.get_table(f'{database_schema}.{database_table}')

    result = {}
    for field in table.schema:
        if field.field_type in ['STRING']:
            type = 'text'
        elif field.field_type in ['INTEGER', 'INT64', 'FLOAT', 'FLOAT64']:
            type = 'number'
        elif field.field_type in ['TIMESTAMP', 'DATE', 'TIME', 'DATETIME']:
            type = 'date'
        elif field.field_type in ['RECORD', 'STRUCT']:
            type = 'json'
        else:
            print(f'Unimplemented column type "{field.field_type}" of "{database_schema}.{database_table}.{field.name}"',
                  sys.stderr)
            continue
        result[field.name] = Column(field.name, type)

    return result


