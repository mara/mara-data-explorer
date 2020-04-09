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


def oauth2_client_config():
    """
    The client configuration as it originally appeared in a client secrets file,
    acquired from the required Google oauth2 credentials.

    Optional for the Export-to-Spreadsheet feature. If None, the feature will be disabled.
    For setting up such credentials, see here:
    https://developers.google.com/identity/protocols/oauth2/web-server

    Example:
    {"web":{
        "client_id": "...",
        "project_id": "...",
        "auth_uri": "...",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "...",
        "redirect_uris": ["..."]}
    }
    """
    return None
