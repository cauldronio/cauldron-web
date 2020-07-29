import logging
import json

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


def active_submitters(elastic, from_date, to_date):
    """Get number of review submitters for a project in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.authors.value or 0
    else:
        return 0


def authors_entering(elastic, from_date, to_date):
    """Get number of authors of PRs/MRs entering in a project for a period of time"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_review', 'min', field='grimoire_creation_date')
    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        authors = {}
        for author in response.aggregations.authors.buckets:
            authors[author.key] = author.first_review.value / 1000

        authors_df = pandas.DataFrame(authors.items(), columns=['author_id', 'first_review'])

        from_date_ts = datetime.timestamp(from_date)
        to_date_ts = datetime.timestamp(to_date)

        return len(authors_df[authors_df["first_review"].between(from_date_ts, to_date_ts)].index)
    else:
        return 0


def authors_active_bokeh(elastic, from_date, to_date):
    """Get evolution of Authors in PRs and MRs"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)

    s.aggs.bucket("bucket1", 'date_histogram', field='grimoire_creation_date', calendar_interval='1w')\
        .bucket('authors', 'cardinality', field='author_uuid')
    try:
        response = s.execute()
        authors_buckets = response.aggregations.bucket1.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_buckets = []

    # Create the Bokeh visualization
    timestamp, authors = [], []
    for item in authors_buckets:
        timestamp.append(item.key)
        authors.append(item.authors.value)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md')
    plot.title.text = '# Merge and Pull requests authors'
    if len(timestamp) > 0:
        plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        authors=authors,
        timestamp=timestamp
    ))

    plot.vbar(x='timestamp', top='authors',
              source=source,
              width=302400000,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('month', '@timestamp{%b %Y}'),
            ('authors', '@authors')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))

