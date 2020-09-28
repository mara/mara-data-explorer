"""Representation and management of data sets"""

from . import config
from .column import Column, columns
from .sql import execute_query, quote_identifier, row_count, quote_text_literal


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
        db = self.database_alias

        if self.columns[column_name].type == 'text[]':
            result = execute_query(self.database_alias, f"""
SELECT f
FROM (SELECT DISTINCT unnest({quote_identifier(db, column_name)}) AS f 
FROM {quote_identifier(self.database_schema)}.{quote_identifier(self.database_table)}) t
WHERE lower(f) LIKE concat('%', {quote_text_literal(db, term.lower())}, '%')
ORDER BY f
LIMIT 50""")

        elif self.use_attributes_table:
            result = execute_query(self.database_alias, f"""
SELECT value 
FROM {quote_identifier(db, self.database_schema)}.{quote_identifier(self.database_table + '_attributes')} 
WHERE attribute = {quote_text_literal(column_name)} 
      AND lower(value) LIKE concat('%', {quote_text_literal(db, term.lower())}, '%') 
LIMIT 50""")

        else:
            result = execute_query(db, f"""
SELECT DISTINCT {quote_identifier(db, column_name)} 
FROM {quote_identifier(db, self.database_schema)}.{quote_identifier(db, self.database_table)}
WHERE lower({quote_identifier(db, column_name)}) LIKE concat('%', {quote_text_literal(db, term.lower())}, '%') 
     AND {quote_identifier(db, column_name)} <> '' 
ORDER BY {quote_identifier(db, column_name)}
LIMIT 50""")

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
