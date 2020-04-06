"""Definition and configuration of data sets"""

import functools

from data_sets import data_set


@functools.lru_cache(maxsize=None)
def data_sets() -> ['data_set.DataSet']:
    """All available data sets"""
    return []


def charts_color() -> str:
    """The color (rgb hex code) to be used in charts"""
    return '#008000'


def google_oauth2_client_secrets_file():
    """
    The client-secret-id json file as acquired from the required Google oauth2 credentials.
    Optional for the Export-to-Spreadsheet feature. If None, the feature will be disabled.
    For setting up such credentials, see here:
    https://github.com/googleapis/google-api-python-client/issues/678
    """
    return None
