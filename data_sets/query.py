"""Queries on data sets"""

import datetime
import json
import re
import subprocess
import math
import decimal

import sqlalchemy
from data_sets.data_set import find_data_set
from sqlalchemy.ext.declarative import declarative_base

import mara_db.dbs
import mara_db.shell
import mara_db.postgresql
from mara_page import acl

Base = declarative_base()


class Filter():
    def __init__(self, column_name, operator, value):
        """
        A "where condition" for a data set query
        Args:
            column_name: The column to filter on
            operator: The comparision operator (depends on column type
            value: The constant value to compare the column to
        """
        self.column_name = column_name
        self.operator = operator
        self.value = value

    def to_dict(self):
        return {'column_name': self.column_name, 'operator': self.operator, 'value': self.value}

    @classmethod
    def from_dict(cls, d):
        return Filter(**d)


class Query(Base):
    __tablename__ = 'data_set_query'

    query_id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    data_set_id = sqlalchemy.Column(sqlalchemy.String, primary_key=True)

    column_names = sqlalchemy.Column(sqlalchemy.ARRAY(sqlalchemy.TEXT))
    sort_column_name = sqlalchemy.Column(sqlalchemy.TEXT)
    sort_order = sqlalchemy.Column(sqlalchemy.TEXT)
    filters = sqlalchemy.Column(sqlalchemy.JSON)

    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP(timezone=True), nullable=False)
    created_by = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP(timezone=True), nullable=False)
    updated_by = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)

    def __init__(self, data_set_id: str, query_id: str = None, column_names: [str] = None,
                 sort_column_name: str = None, sort_order: str = 'ASC',
                 filters: [Filter] = None,
                 created_at: datetime.datetime = None, created_by: str = None,
                 updated_at: datetime.datetime = None, updated_by: str = None):
        """
        Represents a query on a data set

        Args:
            data_set_id: The id of the data set to query
            query_id: The id (name) of the query
            column_names: All columns that are included in the query
            sort_column_name: The column to sort on
            sort_order: How to sort, 'ASC', 'DESC' or None
            filters: Restrictions on the data set

            created_at: When the query was created
            created_by: Rhe user that created the query

            updated_at: When the query was changed the last time
            updated_by: The user that changed the query last
        """
        self.data_set = find_data_set(data_set_id)

        self.data_set_id = data_set_id
        self.query_id = re.sub(r'\W+', '-', query_id).lower() if query_id else ''
        self.column_names = [column_name for column_name in
                             (self.data_set.default_column_names if column_names == None else column_names)
                             if column_name in self.data_set.columns]
        self.sort_column_name = sort_column_name if sort_column_name in self.data_set.columns else None
        self.sort_order = sort_order
        self.filters = [filter for filter in filters or [] if filter.column_name in self.data_set.columns]
        self.created_at = created_at
        self.created_by = created_by
        self.updated_at = updated_at
        self.updated_by = updated_by

    def run(self, limit=None, offset=None, include_personal_data: bool = True):
        """
        Runs the query and returns the result
        Args:
            limit: How many rows to return at max
            offset: Which row to start with
            include_personal_data: When True, include columns that contain personal data

        Returns: An array of values
        """
        if not self.column_names:  # table probably does not exists or no columns are selected
            return []
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(self.to_sql(limit=limit, offset=offset, include_personal_data=include_personal_data))
            return cursor.fetchall()

    def to_sql(self, limit=None, offset=None, decimal_mark: str = '.', include_personal_data: bool = True):
        if self.column_names:
            columns = []
            for column_name in self.column_names:
                if (not include_personal_data) and (column_name in self.data_set.personal_data_column_names):
                    columns.append(f"""'🔒' AS "{column_name}" """)
                elif self.data_set.columns[column_name].type == 'number' and decimal_mark == ',':
                    columns.append(f'''REPLACE("{column_name}"::TEXT, '.', ',') AS "{column_name}"''')
                else:
                    columns.append(f'"{column_name}"')

            sql = f"""
SELECT """ + ',\n       '.join(columns) + f"""
FROM "{self.data_set.database_schema}"."{self.data_set.database_table}"
""" + self.filters_to_sql()
            if self.sort_order and self.sort_column_name:
                sql += f'\nORDER BY "{self.sort_column_name}" {self.sort_order} NULLS LAST\n';

            if limit is not None:
                sql += f'\nLIMIT {int(limit)}\n'
            if offset is not None:
                sql += f'\nOFFSET {int(offset)}\n'

            return sql
        else:
            return None

    def filters_to_sql(self) -> str:
        """Renders a SQL WHERE condition for the query"""
        if self.filters:
            return 'WHERE ' + '\n  AND '.join([self.filter_to_sql(filter) for filter in self.filters]) + '\n'
        else:
            return ''

    def filter_to_sql(self, filter: Filter):
        """Renders a filter to a part of an SQL WHERE expression"""
        type = self.data_set.columns[filter.column_name].type
        if type == 'text':
            if filter.operator == '~':
                return f'"{filter.column_name}" ILIKE ANY(ARRAY[' \
                       + ', '.join(f"'%{value}%'" for value in filter.value or ['']) + ']::TEXT[])'
            else:
                return f'''"{filter.column_name}" {'IN' if filter.operator == '=' else 'NOT IN'} (''' \
                       + ', '.join(f"'{value}'" for value in filter.value or ['']) + ')'
        elif type == 'text[]':
            clause = f'''"{filter.column_name}" && ARRAY[''' \
                     + ', '.join(f"'{value}'" for value in filter.value or ['']) + ']::TEXT[]'
            if filter.operator == '!=':
                clause = ' not (' + clause + ')'
            return clause
        elif type == 'number':
            return f'''"{filter.column_name}" {filter.operator} {filter.value}'''
        elif type == 'date':
            return f'''"{filter.column_name}"::Date {filter.operator} '{filter.value}' '''
        else:
            return '1=1'

    def row_count(self):
        """Compute how many rows will be returned by the current set of filters"""
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'SELECT count(*) FROM "{self.data_set.database_schema}"."{self.data_set.database_table}" '
                           + self.filters_to_sql())
            return cursor.fetchone()[0]

    def filter_row_count(self, filter_pos):
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(
                f'SELECT count(*) FROM "{self.data_set.database_schema}"."{self.data_set.database_table}" WHERE '
                + self.filter_to_sql(self.filters[filter_pos]))
            return cursor.fetchone()[0]

    def as_csv(self, delimiter, decimal_mark, include_personal_data):
        query = self.to_sql(decimal_mark=decimal_mark, include_personal_data=include_personal_data).replace('"', '\\"')
        command = mara_db.shell.query_command(self.data_set.database_alias, echo_queries=False) \
                  + f''' --command="COPY ({query}) TO STDOUT WITH DELIMITER E'{delimiter}' CSV HEADER;"'''

        return subprocess.check_output(command, shell=True)

    def as_spreadsheet(self, array_format, header: bool = True, limit=None, offset=None,
                       include_personal_data: bool = True):
        """
        Runs the query and returns the result as a spreadsheet data input (list of lists)
        Args:
            header: When True, include a header row with the column names
            limit: How many rows to return at max
            offset: Which row to start with
            include_personal_data: When True, include columns that contain personal data
            array_format: Array to string format for array types

        Returns: A spreadsheet data input as list of lists
        """
        if not self.column_names:  # table probably does not exists or no columns are selected
            return []
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(self.to_sql(limit=limit, offset=offset, include_personal_data=include_personal_data))
            result = cursor.fetchall()
            if header is True:
                column_names = [desc[0] for desc in cursor.description]
                yield column_names
            for row in result:
                row_list = []
                for value in list(row):
                    if isinstance(value, str):
                        list_value_str = value.replace('\t', ' - ')
                        # no more than 50k characters for a single cell value (Google API limit reference)
                        row_list.append((list_value_str[:48995] + ' ... ') if len(list_value_str) > 50000 else value)
                    elif isinstance(value, list):
                        list_value_str = str(value).replace('\t', ' - ') if len(value) > 0 else ''
                        # Adjust array format
                        if array_format == 'curly':
                            list_value_str = ('{' + list_value_str[1:-1] + '}').replace('{}', '')
                        elif array_format == 'tuple':
                            list_value_str = str(tuple(value)).replace('\t', ' - ') if len(value) > 0 else ''

                        row_list.append(
                            (list_value_str[:48995] + ' ... ') if len(list_value_str) > 50000 else list_value_str)
                    elif isinstance(value, datetime.datetime):
                        row_list.append(str(value.strftime("%d-%m-%Y")))
                    else:
                        row_list.append(value)
                yield row_list

    def number_distribution(self, column_name):
        """Returns a frequency histogram for a number column"""
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f"""
SELECT min("{column_name}") :: NUMERIC AS min_value,
       max("{column_name}") :: NUMERIC AS max_value,
       count(*)                        AS number_of_values
FROM "{self.data_set.database_schema}"."{self.data_set.database_table}"
WHERE "{column_name}" IS NOT NULL
      {('AND ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters])) if self.filters else ''}
""")
            (min_value, max_value, number_of_values) = cursor.fetchone()
            if min_value == None:
                return []

            min_buckets = 5

            # find the highest magnitude of 10
            exponent = math.ceil(max(abs(min_value).log10(), abs(max_value).log10()))

            # when there is only a single value
            if min_value == max_value:
                return ([(float(min_value), float(max_value), float(number_of_values))])

            while True:
                _10 = decimal.Decimal(10)

                # truncate to the next lower magnitude of 10
                min_ = math.floor(min_value / pow(_10, exponent))
                max_ = math.ceil(max_value / pow(_10, exponent))

                if (max_ - min_) > min_buckets:
                    # compute buckets (tuples of min and max values)
                    cursor.execute(f"""
SELECT width_bucket("{column_name}", {min_ * pow(_10, exponent)}, {max_ * pow(_10, exponent)}, {max_ - min_}) as bucket,
      count(*) AS n
FROM "{self.data_set.database_schema}"."{self.data_set.database_table}"
WHERE "{column_name}" IS NOT NULL
      {('AND ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters])) if self.filters else ''}
GROUP by bucket
ORDER BY bucket
""")
                    return ([(float((min_ + bucket - 1) * pow(_10, exponent)),
                              float((min_ + bucket) * pow(_10, exponent)),
                              n) for bucket, n in cursor.fetchall()])
                else:
                    exponent += -1

    def date_distribution(self, column_name):
        """Returns a frequency histogram for a date column"""

        import arrow

        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
                cursor.execute(f"""
SELECT min("{column_name}") :: TIMESTAMPTZ AS min_value,
       max("{column_name}") :: TIMESTAMPTZ AS max_value
FROM "{self.data_set.database_schema}"."{self.data_set.database_table}"
WHERE "{column_name}" IS NOT NULL
      {('AND ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters])) if self.filters else ''}
""")
                (min_value, max_value) = cursor.fetchone()
                if min_value == None:
                    return []

                resolutions = {'year': 'YYYY',
                               'month': 'YYYY Mon',
                               'week': 'IYYY "-" "CW "IW',
                               'day': 'Dy, Mon DD YYYY'}

                min_buckets = 5

                for resolution in resolutions.keys():
                    if len(list(arrow.Arrow.range(resolution, min_value, max_value))) >= min_buckets:
                        break

                # compute buckets (tuples of min and max values)
                cursor.execute(f"""
SELECT date_trunc('{resolution}', "{column_name}") as d,
       to_char(date_trunc('{resolution}', "{column_name}"), '{resolutions[resolution]}'),
       count(*) AS n
FROM "{self.data_set.database_schema}"."{self.data_set.database_table}"
WHERE "{column_name}" IS NOT NULL
      {('AND ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters])) if self.filters else ''}
GROUP by d
ORDER BY d
""")
                return cursor.fetchall()

    def text_distribution(self, column_name):
        """Returns the most frequent values and their counts for a column"""
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'''
SELECT "{column_name}" AS value,
       count(*) AS n
FROM "{self.data_set.database_schema}"."{self.data_set.database_table}"
WHERE "{column_name}" IS NOT NULL 
      {('AND ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters])) if self.filters else ''}
GROUP BY value
ORDER BY n DESC
LIMIT 10''')
            return cursor.fetchall()

    def text_array_distribution(self, column_name):
        """Returns the most frequent values and their counts for a text array column"""
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'''
SELECT unnest("{column_name}") AS value,
       count(*) AS n
FROM "{self.data_set.database_schema}"."{self.data_set.database_table}"
WHERE "{column_name}" IS NOT NULL 
      {('AND ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters])) if self.filters else ''}
GROUP BY value
ORDER BY n DESC
LIMIT 10''')
            return cursor.fetchall()

    def save(self):
        """Saves a query in the database"""
        with mara_db.postgresql.postgres_cursor_context('mara') as cursor:
            cursor.execute(f'''
INSERT INTO data_set_query (query_id, data_set_id, column_names, sort_column_name, sort_order, filters, 
                            created_at, created_by, updated_at, updated_by)
VALUES ({'%s, %s, %s, %s, %s, %s, %s, %s, %s, %s'})
ON CONFLICT (query_id, data_set_id)
DO UPDATE SET 
    column_names=EXCLUDED.column_names,
    sort_column_name=EXCLUDED.sort_column_name,
    sort_order=EXCLUDED.sort_order,
    filters=EXCLUDED.filters,
    updated_at=EXCLUDED.updated_at, 
    updated_by=EXCLUDED.updated_by
''', (self.query_id, self.data_set.id, self.column_names, self.sort_column_name, self.sort_order,
      json.dumps([filter.to_dict() for filter in self.filters]),
      datetime.datetime.now(), acl.current_user_email(),
      datetime.datetime.now(), acl.current_user_email()))

    @classmethod
    def load(cls, query_id, data_set_id):
        """Loads a query from the database"""
        with mara_db.postgresql.postgres_cursor_context('mara') as cursor:
            cursor.execute(f'''
SELECT data_set_id, query_id, column_names, sort_column_name, sort_order, filters, 
       created_at, created_by, updated_at, updated_by 
FROM data_set_query 
WHERE data_set_id = {'%s'} AND query_id = {'%s'}''',
                           (data_set_id, query_id))
            (data_set_id, query_id, column_names, sort_column_name, sort_order, filters,
             created_at, created_by, updated_at, updated_by) = cursor.fetchone()
            return Query(data_set_id, query_id, column_names, sort_column_name, sort_order,
                         [Filter.from_dict(f) for f in filters],
                         created_at, created_by, updated_at, updated_by)

    def to_dict(self):
        return {'data_set_id': self.data_set.id,
                'query_id': self.query_id,
                'column_names': self.column_names,
                'sort_column_name': self.sort_column_name,
                'sort_order': self.sort_order,
                'filters': [filter.to_dict() for filter in self.filters],
                'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else None,
                'created_by': self.created_by,
                'updated_at': self.updated_at.strftime('%Y-%m-%d') if self.updated_at else None,
                'updated_by': self.updated_by}

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        d['filters'] = [Filter.from_dict(f) for f in d['filters']]
        return Query(**d)

    def __repr__(self):
        return f'<Query {self.to_sql()}>'


def delete_query(data_set_id, query_id: str):
    with mara_db.postgresql.postgres_cursor_context('mara') as cursor:
        cursor.execute(f'''
DELETE FROM data_set_query
WHERE data_set_id = {'%s'} AND query_id = {'%s'}''', (data_set_id, query_id))


def list_queries(data_set_id: str):
    with mara_db.postgresql.postgres_cursor_context('mara') as cursor:
        cursor.execute(f'''
SELECT query_id, updated_at, updated_by 
FROM data_set_query
WHERE data_set_id = {'%s'}
ORDER BY updated_at DESC             
''', (data_set_id,))
        return cursor.fetchall()
