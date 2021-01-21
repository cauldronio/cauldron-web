import json
import logging
from datetime import datetime, timedelta
import pandas
from functools import reduce

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues, Reds
from bokeh.plotting import figure

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from ..utils import configure_figure, get_interval, get_time_diff_days

logger = logging.getLogger(__name__)


def median_time_to_close(elastic, urls, from_date, to_date):
    """Gives the median time to close for closed (and merged) reviews in a period"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('range', closed_at={'gte': from_date, 'lte': to_date}) |
               Q('range', merged_at={'gte': from_date, 'lte': to_date})) \
        .query(Q('terms', origin=urls)) \
        .extra(size=0)
    s.aggs.bucket('ttc_percentiles', 'percentiles', field='time_to_close_days', percents=[50])

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.aggregations.ttc_percentiles.values['50.0'] is not None:
        return round(response.aggregations.ttc_percentiles.values['50.0'], 2)
    else:
        return '?'


def average_open_time(elastic, urls, date):
    """Gives the average time that open reviews have been open"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .query(Q('range', created_at={'lte': date}) &
              (Q('range', closed_at={'gte': date}) |
               Q('range', merged_at={'gte': date}) |
               Q('terms', state=['open', 'opened']))) \
        .source('created_at')

    try:
        response = s.scan()
    except ElasticsearchException as e:
        logger.warning(e)
        response = []

    date_list = []
    for hit in response:
        date_list.append(hit.created_at)

    dates = pandas.DataFrame(date_list, columns=['created_at'])
    if dates.empty:
        return '?'

    dates['time_open'] = dates['created_at'].apply(lambda x: get_time_diff_days(x, datetime.utcnow().replace(tzinfo=None)))
    mean = dates['time_open'].mean()

    return round(mean, 2)


def median_open_time(elastic, urls, date):
    """Gives the median time that open reviews have been open"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .query(Q('range', created_at={'lte': date}) &
              (Q('range', closed_at={'gte': date}) |
               Q('range', merged_at={'gte': date}) |
               Q('terms', state=['open', 'opened']))) \
        .source('created_at')

    try:
        response = s.scan()
    except ElasticsearchException as e:
        logger.warning(e)
        response = []

    date_list = []
    for hit in response:
        date_list.append(hit.created_at)

    dates = pandas.DataFrame(date_list, columns=['created_at'])
    if dates.empty:
        return '?'

    dates['time_open'] = dates['created_at'].apply(lambda x: get_time_diff_days(x, datetime.utcnow().replace(tzinfo=None)))
    median = dates['time_open'].median()

    return round(median, 2)


def open_reviews(elastic, urls, date):
    # TODO: This metric is equal to activity/reviews_open_on
    """Gives the number of open reviews in a given date"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .query(Q('range', created_at={'lte': date}) &
              (Q('range', closed_at={'gte': date}) |
               Q('range', merged_at={'gte': date}) |
               Q('terms', state=['open', 'opened'])))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = '?'

    return response


def ttc_created_reviews_bokeh(elastic, urls, from_date, to_date):
    """Generates a visualization showing the average and the median
    time to close of created reviews in a given period"""
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .filter('range', created_at={'gte': from_date, "lte": to_date}) \
        .extra(size=0)
    s.aggs.bucket('dates', 'date_histogram', field='created_at', calendar_interval=interval_elastic) \
          .metric('ttc_avg', 'avg', field='time_to_close_days') \
          .metric('ttc_median', 'percentiles', field='time_to_close_days', percents=[50])

    try:
        response = s.execute()
        date_buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        date_buckets = []

    # Create the Bokeh visualization
    timestamps, ttc_avg, ttc_median = [], [], []
    for item in date_buckets:
        timestamps.append(item.key)
        ttc_avg.append(item.ttc_avg.value)
        ttc_median.append(item.ttc_median.values['50.0'])

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='Days',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/performance/ttc-created-reviews.md')
    plot.title.text = 'Time to close (Reviews created)'
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        ttc_avg=ttc_avg,
        ttc_median=ttc_median,
        timestamps=timestamps
    ))

    plot.vbar(x='timestamps', top='ttc_avg',
              name='ttc_avg',
              source=source,
              width=bar_width,
              color=Blues[3][0],
              legend_label='Average')

    plot.line('timestamps', 'ttc_median',
              line_width=4,
              line_color=Reds[3][0],
              legend_label='Median',
              source=source)

    plot.add_tools(tools.HoverTool(
        names=['ttc_avg'],
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('ttc_avg', '@ttc_avg{0.00}'),
            ('ttc_median', '@ttc_median{0.00}')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))
    plot.legend.location = "top_right"

    return json.dumps(json_item(plot))


def reviews_still_open_by_creation_date_bokeh(elastic, urls):
    """Get a visualization of current open reviews age"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .query(Q('terms', state=['open', 'opened']))
    s.aggs.bucket("open_reviews", 'date_histogram', field='created_at', calendar_interval='1M')

    try:
        response = s.execute()
        open_buckets = response.aggregations.open_reviews.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        open_buckets = []

    # Create the Bokeh visualization
    timestamp, reviews = [], []
    for month in open_buckets:
        timestamp.append(month.key)
        reviews.append(month.doc_count)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Reviews still open by creation date'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/performance/reviews-still-open-by-creation-date.md')

    source = ColumnDataSource(data=dict(
        reviews=reviews,
        timestamp=timestamp
    ))

    # width = 1000 ms/s * 60 s/m * 60 m/h * 24 h/d * 30 d/M * 0.8 width
    plot.vbar(x='timestamp', top='reviews',
              source=source,
              width=2073600000,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('month', '@timestamp{%b %Y}'),
            ('reviews', '@reviews')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def ttc_closed_reviews_bokeh(elastic, urls, from_date, to_date):
    """Generates a visualization showing the average and the median
    time to close of closed reviews in a given period"""
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .filter('range', closed_at={'gte': from_date, "lte": to_date}) \
        .extra(size=0)
    s.aggs.bucket('dates', 'date_histogram', field='closed_at', calendar_interval=interval_elastic) \
          .metric('ttc_avg', 'avg', field='time_to_close_days') \
          .metric('ttc_median', 'percentiles', field='time_to_close_days', percents=[50])

    try:
        response = s.execute()
        dates_buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        dates_buckets = []

    # Create the Bokeh visualization
    timestamps, ttc_avg, ttc_median = [], [], []
    for item in dates_buckets:
        timestamps.append(item.key)
        ttc_avg.append(item.ttc_avg.value)
        ttc_median.append(item.ttc_median.values['50.0'])

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='Days',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/performance/ttc-closed-reviews.md')
    plot.title.text = 'Time to close (Reviews closed)'
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        ttc_avg=ttc_avg,
        ttc_median=ttc_median,
        timestamps=timestamps
    ))

    plot.vbar(x='timestamps', top='ttc_avg',
              name='ttc_avg',
              source=source,
              width=bar_width,
              color=Blues[3][0],
              legend_label='Average')

    plot.line('timestamps', 'ttc_median',
              line_width=4,
              line_color=Reds[3][0],
              legend_label='Median',
              source=source)

    plot.add_tools(tools.HoverTool(
        names=['ttc_avg'],
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('ttc_avg', '@ttc_avg{0.00}'),
            ('ttc_median', '@ttc_median{0.00}')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))
    plot.legend.location = "top_right"

    return json.dumps(json_item(plot))


def closed_created_reviews_ratio_bokeh(elastic, urls, from_date, to_date):
    """Generates a visualization showing the ratio between closed (and merged) and
    created reviews in a given date"""

    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .extra(size=0)
    s.aggs.bucket('created_reviews', 'filter', Q('range', created_at={'gte': from_date, "lte": to_date})) \
          .bucket('dates', 'date_histogram', field='created_at', calendar_interval=interval_elastic)
    s.aggs.bucket('closed_reviews', 'filter', Q('range', closed_at={'gte': from_date, "lte": to_date})) \
          .bucket('dates', 'date_histogram', field='closed_at', calendar_interval=interval_elastic)
    s.aggs.bucket('merged_reviews', 'filter', Q('range', merged_at={'gte': from_date, "lte": to_date})) \
          .bucket('dates', 'date_histogram', field='merged_at', calendar_interval=interval_elastic)

    try:
        response = s.execute()
        created_buckets = response.aggregations.created_reviews.dates.buckets
        closed_buckets = response.aggregations.closed_reviews.dates.buckets
        merged_buckets = response.aggregations.merged_reviews.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        created_buckets = []
        closed_buckets = []
        merged_buckets = []

    # Create the data structure for created reviews
    reviews_created, timestamps_created = [], []
    for date in created_buckets:
        timestamps_created.append(date.key)
        reviews_created.append(date.doc_count)

    # Create the data structure for closed reviews
    reviews_closed, timestamps_closed = [], []
    for date in closed_buckets:
        timestamps_closed.append(date.key)
        reviews_closed.append(date.doc_count)

    # Create the data structure for merged reviews
    reviews_merged, timestamps_merged = [], []
    for date in merged_buckets:
        timestamps_merged.append(date.key)
        reviews_merged.append(date.doc_count)

    data = []
    data.append(pandas.DataFrame(list(zip(timestamps_created, reviews_created)), columns =['timestamps', 'reviews_created']))
    data.append(pandas.DataFrame(list(zip(timestamps_closed, reviews_closed)), columns =['timestamps', 'reviews_closed']))
    data.append(pandas.DataFrame(list(zip(timestamps_merged, reviews_merged)), columns =['timestamps', 'reviews_merged']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)
    # We are counting the rejected and merged reviews as closed reviews
    data['reviews_closed'] = data['reviews_closed'] + data['reviews_merged']

    data['ratio'] = data['reviews_closed'] / data['reviews_created']

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='Ratio',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = 'Reviews closed / created ratio'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/performance/reviews-closed-created-ratio.md')
    if not data.empty:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        ratio=data['ratio'],
        timestamps=data['timestamps']
    ))

    plot.circle(x='timestamps', y='ratio',
                color=Blues[3][0],
                size=8,
                source=source)

    plot.line(x='timestamps', y='ratio',
              line_width=4,
              line_color=Blues[3][0],
              source=source)

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('ratio', '@ratio{0.00}')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))
