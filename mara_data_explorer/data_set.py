"""Representation and management of data sets"""

import mara_db.dbs
import mara_db.postgresql
from . import config
from .column import Column, columns

from functools import singledispatch



class DataSet():
    def __init__(self, id: str, name: str,
                 database_alias: str, database_schema: str, database_table: str,
                 default_column_names: [str],
                 personal_data_column_names: [str] = None, use_attributes_table: bool = False,
                 custom_column_renderers: dict = None):
        """
        Description of a database table with default output columns

        Args:
            id: The id (url key) of the data set
            name: The title of the data set (only used in UI)
            database_alias: The alias of the mara_db connection to use
            database_schema: The schema of the underlying data set table
            database_table: The underlying data set table
            default_column_names: The list of columns to be displayed by default
            personal_data_column_names: The names of all columns that are considered personal data
            use_attributes_table: If true, a {{database_schema}}.{{database_table}}_attributes table
                                  is used for auto-completion
            custom_column_renderers: A mapping of columns to functions that render columns differently,
                                     e.g. `{'my-column': lambda value: f'<span style='color:red'>{value}</span>'}`
        """
        self.id = id
        self.name = name
        self.database_alias = database_alias
        self.database_schema = database_schema
        self.database_table = database_table
        self.default_column_names = default_column_names
        self.personal_data_column_names = personal_data_column_names or []
        self.use_attributes_table = use_attributes_table
        self.custom_column_renderers = custom_column_renderers or {}

        self._columns = {}

    @property
    def columns(self) -> {str: Column}:
        """Retrieves all columns of a data set from the database table"""
        if not self._columns:
            self._columns = columns(self.database_alias, self.database_schema, self.database_table)
        return self._columns

    def autocomplete_text_column(self, column_name, term):
        """Returns a list of values from `column` that contain `term` """
        with mara_db.postgresql.postgres_cursor_context(self.database_alias) as cursor:
            if self.columns[column_name].type == 'text[]':
                cursor.execute(f"""
SELECT f
FROM (SELECT DISTINCT unnest("{column_name}") AS f FROM "{self.database_schema}"."{self.database_table}") t
WHERE f ilike %s
ORDER BY f
LIMIT 50""", (f'%{term}%',))

            elif self.use_attributes_table:
                cursor.execute(f"""
SELECT value 
FROM "{self.database_schema}"."{self.database_table}_attributes" 
WHERE attribute = %s AND value ilike %s 
LIMIT 50""", (column_name, f'%{term}%'))

            else:
                cursor.execute(f"""
SELECT DISTINCT "{column_name}" 
FROM "{self.database_schema}"."{self.database_table}"
WHERE "{column_name}" ILIKE %s AND "{column_name}" <> '' 
ORDER BY "{column_name}"
LIMIT 50""", (f'%{term}%',))

            result = cursor.fetchall()
            if not result:
                return ["\tNo match"]
            else:
                return [row[0] for row in result]

    def row_count(self):
        """Compute the total number of rows of the data set"""
        if self.columns:
            return row_count(self.database_alias, self.database_schema, self.database_table)
        else:
            return 0

    def __repr__(self):
        return f'<DataSet "{self.name}">'


def find_data_set(id: str) -> DataSet:
    """Returns a data set by its id"""
    for ds in config.data_sets():
        if ds.id == id: return ds


@singledispatch
def row_count(db: mara_db.dbs.DB, database_schema: str, database_table: str) -> int:
    """Returns the total number of rows in a database table"""
    raise NotImplementedError(f'Please implement row_count for type "{db.__class__.__name__}"')


@row_count.register(str)
def __(db: str, database_schema: str, database_table: str) -> [Column]:
    """Extracts a list of column definitions from a database"""
    return row_count(mara_db.dbs.db(db), database_schema, database_table)

@row_count.register(mara_db.dbs.BigQueryDB)
def __(db: mara_db.dbs.BigQueryDB, database_schema: str, database_table: str):
    from mara_db.bigquery import bigquery_client

    client = bigquery_client(db)
    table = client.get_table(f'{database_schema}.{database_table}')

    return table.num_rows


    #
    # with mara_db.postgresql.postgres_cursor_context(self.database_alias) as cursor:
    #     cursor.execute(f'SELECT count(*) FROM "{self.database_schema}"."{self.database_table}"')
    #     return cursor.fetchone()[0]
