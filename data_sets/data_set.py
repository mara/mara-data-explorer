"""Representation and management of data sets"""

import mara_db.dbs
import mara_db.postgresql
from data_sets import config


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
            with mara_db.postgresql.postgres_cursor_context(self.database_alias) as cursor:
                cursor.execute(f"""
SELECT
  att.attname,
  pg_catalog.format_type(atttypid, NULL) AS display_type
FROM pg_attribute att
  JOIN pg_class tbl ON tbl.oid = att.attrelid
  JOIN pg_namespace ns ON tbl.relnamespace = ns.oid
WHERE tbl.relname = {'%s'} AND ns.nspname = {'%s'} AND attnum > 0
ORDER BY attnum""", (self.database_table, self.database_schema))
                for column_name, column_type in cursor.fetchall():
                    if column_type in ['character varying', 'text']:
                        type = 'text'
                    elif column_type in ['integer', 'real', 'smallint', 'double precision']:
                        type = 'number'
                    elif column_type in ['timestamp', 'timestamp with time zone', 'date']:
                        type = 'date'
                    elif column_type in ['json', 'jsonb']:
                        type = 'json'
                    elif column_type == 'text[]':
                        type = 'text[]'
                    else:
                        raise ValueError(
                            f'Unimplemented column type "{column_type}" of "{self.database_alias}.{self.database_schema}.{self.database_table}.{column_name}"')
                    self._columns[column_name] = Column(column_name, type)
        return self._columns

    def autocomplete_text_column(self, column_name, term):
        """Returns a list of values from `column` that contain `term` """
        with mara_db.postgresql.postgres_cursor_context(self.database_alias) as cursor:
            if self.columns[column_name].type == 'text[]':
                cursor.execute(f"""
SELECT f
FROM (SELECT DISTINCT unnest("{column_name}") AS f FROM {self.database_schema}.{self.database_table}) t
WHERE f ilike %s
ORDER BY f
LIMIT 50""", (f'%{term}%',))

            elif self.use_attributes_table:
                cursor.execute(f"""
SELECT value 
FROM {self.database_schema}.{self.database_table}_attributes 
WHERE attribute = %s AND value ilike %s 
LIMIT 50""", (column_name, f'%{term}%'))

            else:
                cursor.execute(f"""
SELECT DISTINCT "{column_name}" 
FROM {self.database_schema}.{self.database_table}
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
        with mara_db.postgresql.postgres_cursor_context(self.database_alias) as cursor:
            cursor.execute(f'SELECT count(*) FROM {self.database_schema}.{self.database_table}')
            return cursor.fetchone()[0]

    def __repr__(self):
        return f'<DataSet "{self.name}">'


def find_data_set(id: str) -> DataSet:
    """Returns a data set by its id"""
    for ds in config.data_sets():
        if ds.id == id: return ds
