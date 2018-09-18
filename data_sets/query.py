"""Queries on data sets"""

import datetime
import json
import re
import subprocess

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

    created_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False)
    created_by = sqlalchemy.Column(sqlalchemy.TEXT, nullable=False)
    updated_at = sqlalchemy.Column(sqlalchemy.TIMESTAMP, nullable=False)
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
SELECT """ + ','.join(columns) + f"""
FROM {self.data_set.database_schema}.{self.data_set.database_table}
""" + self.filters_to_sql()
            if self.sort_order and self.sort_column_name:
                sql += f'ORDER BY "{self.sort_column_name}" {self.sort_order} NULLS LAST\n';

            if limit != None and offset != None:
                sql += f'LIMIT {int(limit)}\n'
                sql += f'OFFSET {int(offset)}\n'

            return sql
        else:
            return None

    def filters_to_sql(self) -> str:
        """Renders a SQL WHERE condition for the query"""
        if self.filters:
            return 'WHERE ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters]) + '\n'
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
            cursor.execute(f'SELECT count(*) FROM {self.data_set.database_schema}.{self.data_set.database_table} '
                           + self.filters_to_sql())
            return cursor.fetchone()[0]

    def filter_row_count(self, filter_pos):
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'SELECT count(*) FROM {self.data_set.database_schema}.{self.data_set.database_table} WHERE '
                           + self.filter_to_sql(self.filters[filter_pos]))
            return cursor.fetchone()[0]

    def as_csv(self, delimiter, decimal_mark, include_personal_data):
        query = self.to_sql(decimal_mark=decimal_mark, include_personal_data=include_personal_data).replace('"', '\\"')
        command = mara_db.shell.query_command(self.data_set.database_alias,echo_queries=False) \
                  + f''' --command="COPY ({query}) TO STDOUT WITH DELIMITER E'{delimiter}' CSV HEADER;"'''

        return subprocess.check_output(command, shell=True)


    def _query_cte_for_distribution_queries(self, column_name):
        return f'''
query AS (SELECT "{column_name}" AS value
          FROM {self.data_set.database_schema}.{self.data_set.database_table}
          WHERE "{column_name}" IS NOT NULL 
                {('AND ' + ' AND '.join([self.filter_to_sql(filter) for filter in self.filters])) if self.filters else ''}),
'''

    def number_distribution(self, column_name):
        """Returns a frequency histogram for a number column"""
        bucket_count = 50
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'''
WITH
{self._query_cte_for_distribution_queries(column_name)}
                
min_max AS (SELECT min(value) :: NUMERIC AS min,
                   max(value) :: NUMERIC AS max
            FROM query),

range AS (SELECT CASE WHEN min <> 0 OR max <> 0 THEN power(10, round(log(greatest(abs(min), abs(max)))-1.7)) ELSE 0 END AS base 
          FROM min_max),

rounded_min_max AS (SELECT CASE WHEN min <> 0 THEN floor( min / base ) * base ELSE 0 END AS min,
                    CASE WHEN max <> 0 THEN ceil( max / base ) * base ELSE 0 END AS max
                    FROM min_max, range),

stats AS (SELECT min, max,
                 CASE WHEN min = max THEN 1 ELSE ((max - min) / {bucket_count}.0) :: NUMERIC END AS bucket_width
          FROM rounded_min_max),

buckets AS (SELECT i, min+i*bucket_width AS min, min+(i+1)*bucket_width AS max 
            FROM stats, generate_series(0, ((max-min)/bucket_width)::INTEGER, 1) i),

histogram AS (SELECT trunc((value-min)/bucket_width) AS bucket,
                     count(*) AS count
              FROM query, stats
              GROUP BY 1)

SELECT min::float, max::float, count
FROM buckets
LEFT JOIN histogram ON bucket = i
ORDER BY i;''')
            return cursor.fetchall()

    def date_distribution(self, column_name):
        """Returns a frequency histogram for a date column"""
        bucket_count = 50
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'''
WITH
{self._query_cte_for_distribution_queries(column_name)}

stats AS (SELECT min(value::DATE)-current_date AS min,
                 max(value::DATE)-current_date AS max,
                 greatest(ceil((max(value::DATE) - min(value::DATE)) / {bucket_count}.0)::INTEGER, 1) AS bucket_width
          FROM query),

buckets AS (SELECT trunc((d-min)/bucket_width) AS i, current_date+d AS min, current_date+d+bucket_width AS max
            FROM stats, generate_series(min, max, bucket_width) d),

histogram AS (SELECT trunc((value::DATE - current_date-min)/bucket_width) AS bucket,
                     count(*) AS count
              FROM query, stats
              GROUP BY 1)

SELECT min, max, count
       
FROM buckets
LEFT JOIN histogram ON bucket = i
ORDER BY i''')
            return cursor.fetchall()

    def text_distribution(self, column_name):
        """Returns the most frequent values and their counts for a column"""
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'''
WITH
{self._query_cte_for_distribution_queries(column_name)}

counts AS (SELECT value, count(*)
           FROM query
           GROUP BY value)

SELECT value AS label, count
FROM counts
ORDER BY count DESC
LIMIT 10''')
            return cursor.fetchall()

    def text_array_distribution(self, column_name):
        """Returns the most frequent values and their counts for a text array column"""
        with mara_db.postgresql.postgres_cursor_context(self.data_set.database_alias) as cursor:
            cursor.execute(f'''
WITH
{self._query_cte_for_distribution_queries(column_name)}

counts AS (SELECT value, count(*)
           FROM (SELECT unnest(value) AS value FROM query) t
           GROUP BY value)

SELECT value AS label, count
FROM counts
ORDER BY count DESC
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
