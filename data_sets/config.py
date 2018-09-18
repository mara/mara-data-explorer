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