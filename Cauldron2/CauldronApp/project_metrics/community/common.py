import json
import logging

import pandas
from datetime import datetime

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues
from bokeh.plotting import figure

from ..utils import configure_figure

logger = logging.getLogger(__name__)


def authors_entering_leaving_bokeh(elastic, from_date, to_date):
    """Get a visualization of people entering and leaving the project"""
    s = Search(using=elastic, index='all') \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_contribution', 'min', field='grimoire_creation_date') \
          .metric('last_contribution', 'max', field='grimoire_creation_date')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        authors_first = {}
        authors_last = {}
        for author in response.aggregations.authors.buckets:
            authors_first[author.key] = author.first_contribution.value / 1000
            authors_last[author.key] = author.last_contribution.value / 1000

        authors_first_df = pandas.DataFrame(authors_first.items(), columns=['author_id', 'first_contribution'])
        authors_last_df = pandas.DataFrame(authors_last.items(), columns=['author_id', 'last_contribution'])

        from_date_ts = datetime.timestamp(from_date)
        to_date_ts = datetime.timestamp(to_date)

        authors_first_range = authors_first_df[authors_first_df["first_contribution"].between(from_date_ts, to_date_ts)]
        authors_last_range = authors_last_df[authors_last_df["last_contribution"].between(from_date_ts, to_date_ts)]

        authors_first_range['first_contribution'] = pandas.to_datetime(authors_first_range['first_contribution'],
                                                                       unit='s')
        authors_grouped_first = authors_first_range.set_index('first_contribution').resample('W').count()
        authors_last_range['last_contribution'] = pandas.to_datetime(authors_last_range['last_contribution'],
                                                                     unit='s')
        authors_grouped_last = authors_last_range.set_index('last_contribution').resample('W').count()
    else:
        authors_grouped_first = []
        authors_grouped_last = []
