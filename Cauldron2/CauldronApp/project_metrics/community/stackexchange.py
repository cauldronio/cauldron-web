import json
import logging
from datetime import timedelta

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues
from bokeh.plotting import figure

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from ..utils import configure_figure, get_interval

logger = logging.getLogger(__name__)


def people_asking(elastic, urls, from_date, to_date):
    """Gives the number of people asking questions on StackExchange in a period"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_question='1')) \
        .filter(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('people_asking', 'cardinality', field='author')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.people_asking.value or 0
    else:
        return '?'


def people_answering(elastic, urls, from_date, to_date):
    """Gives the number of people answering questions on StackExchange in a period"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_answer='1')) \
        .filter(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('people_answering', 'cardinality', field='author')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.people_answering.value or 0
    else:
        return '?'


def people_asking_over_time(elastic, urls, from_date, to_date, interval):
    """Gives the number of people asking questions on StackExchange grouped by date"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_question='1')) \
        .filter(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('dates', 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('people_asking', 'cardinality', field='author')

    try:
        response = s.execute()
        dates_buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        dates_buckets = []

    timestamps, people_asking = [], []
    for period in dates_buckets:
        timestamps.append(period.key)
        people_asking.append(period.people_asking.value)

    return timestamps, people_asking


def people_answering_over_time(elastic, urls, from_date, to_date, interval):
    """Gives the number of people answering questions on StackExchange grouped by date"""
    s = Search(using=elastic, index='stackexchange') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', is_stackexchange_answer='1')) \
        .filter(Q('terms', tag=urls)) \
        .extra(size=0)
    s.aggs.bucket('dates', 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('people_answering', 'cardinality', field='author')

    try:
        response = s.execute()
        dates_buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        dates_buckets = []

    timestamps, people_answering = [], []
    for period in dates_buckets:
        timestamps.append(period.key)
        people_answering.append(period.people_answering.value)

    return timestamps, people_answering


def people_asking_bokeh(elastic, urls, from_date, to_date):
    """Get evolution of the number of people asking questions on StackExchange (line chart)"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    timestamps, people_asking = people_asking_over_time(elastic, urls, from_date, to_date, interval_elastic)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# People asking',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# People asking'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/people-asking-chart.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        people_asking=people_asking,
        timestamps=timestamps
    ))

    plot.circle(x='timestamps', y='people_asking',
                color=Blues[3][0],
                size=8,
                source=source)

    plot.line(x='timestamps', y='people_asking',
              line_width=4,
              line_color=Blues[3][0],
              source=source)

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('people_asking', '@people_asking')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def people_answering_bokeh(elastic, urls, from_date, to_date):
    """Get evolution of the number of people answering questions on StackExchange (line chart)"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    timestamps, people_answering = people_answering_over_time(elastic, urls, from_date, to_date, interval_elastic)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# People answering',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# People answering'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/people-answering-chart.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        people_answering=people_answering,
        timestamps=timestamps
    ))

    plot.circle(x='timestamps', y='people_answering',
                color=Blues[3][0],
                size=8,
                source=source)

    plot.line(x='timestamps', y='people_answering',
              line_width=4,
              line_color=Blues[3][0],
              source=source)

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('people_answering', '@people_answering')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))
