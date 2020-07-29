import json
import logging
from collections import defaultdict

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues
from bokeh.plotting import figure

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from ..utils import configure_figure, weekday_vbar_figure, WEEKDAY

logger = logging.getLogger(__name__)


def reviews_opened(elastic, from_date, to_date):
    """Get number of Merge requests and Pull requests opened in the specified range"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 0


def reviews_closed(elastic, from_date, to_date):
    """Get number of Merge requests and Pull requests closed in the specified range"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 0


def reviews_open_on(elastic, date):
    """Get the number of reviews that were open on a specific day"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True))\
        .query(Q('range', created_at={'lte': date}) &
               (Q('range', closed_at={'gte': date}) | Q('match', state='open')))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 0


def reviews_open_closed_bokeh(elastic, from_date, to_date):
    """Visualization of opened and closed reviews in the specified time rage"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .query('bool', filter=(Q('match', pull_request=True) | Q('match', merge_request=True))) \
        .extra(size=0)
    s.aggs.bucket('range_open', 'filter', Q('range', created_at={'gte': from_date_es, "lte": to_date_es})) \
        .bucket('open', 'date_histogram', field='created_at', calendar_interval='1w')
    s.aggs.bucket('range_closed', 'filter', Q('range', closed_at={'gte': from_date_es, "lte": to_date_es})) \
        .bucket('closed', 'date_histogram', field='closed_at', calendar_interval='1w')

    try:
        response = s.execute()
        closed_buckets = response.aggregations.range_closed.closed.buckets
        open_buckets = response.aggregations.range_open.open.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        closed_buckets = []
        open_buckets = []

    # Create the Bokeh visualization
    c_timestamp, closed_reviews, o_timestamp, open_reviews = [], [], [], []
    for citem, oitem in zip(closed_buckets, open_buckets):
        c_timestamp.append(citem.key)
        o_timestamp.append(oitem.key)
        closed_reviews.append(citem.doc_count)
        open_reviews.append(oitem.doc_count)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Reviews open/closed'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md#-reviews-openclosed')
    if len(o_timestamp) > 0 or len(c_timestamp) > 0:
        plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        o_timestamp=o_timestamp,
        c_timestamp=c_timestamp,
        open_reviews=open_reviews,
        closed_reviews=closed_reviews
    ))

    plot.line(x='c_timestamp', y='closed_reviews',
              line_width=4,
              line_color=Blues[3][0],
              legend_label='closed reviews',
              source=source)
    plot.line(x='o_timestamp', y='open_reviews',
              name='open_reviews',
              line_width=4,
              line_color=Blues[3][1],
              legend_label='created reviews',
              source=source)

    plot.add_tools(tools.HoverTool(
        names=['open_reviews'],
        tooltips=[
            ('date', '@o_timestamp{%F}'),
            ('created reviews', '@open_reviews'),
            ('closed reviews', '@closed_reviews')
        ],
        formatters={
            '@o_timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def reviews_open_age_opened_bokeh(elastic):
    """Get a visualization of current open reviews age"""
    s = Search(using=elastic, index='all') \
        .query('bool', filter=((Q('match', pull_request=True) | Q('match', merge_request=True)) &
               Q('match', state='open'))) \
        .extra(size=0)
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
                  y_axis_label='# reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Open reviews age'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md#-open-reviews-age')

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


def reviews_open_weekday_bokeh(elastic):
    """Get reviews open per week day"""
    s = Search(using=elastic, index='all') \
        .query((Q('match', pull_request=True) | Q('match', is_gitlab_issue=1))) \
        .extra(size=0)
    s.aggs.bucket('reviews_weekday', 'terms', script="doc['created_at'].value.dayOfWeek", size=7)

    try:
        response = s.execute()
        reviews_bucket = response.aggregations.reviews_weekday.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        reviews_bucket = []

    # Create the Bokeh visualization
    reviews_dict = defaultdict(int)
    for weekday_item in reviews_bucket:
        reviews_dict[weekday_item.key] = weekday_item.doc_count

    reviews = []
    for i, k in enumerate(WEEKDAY):
        reviews.append(reviews_dict[str(i + 1)])

    plot = weekday_vbar_figure(top=reviews,
                               y_axis_label='# Reviews',
                               title='# Reviews open by weekday',
                               tooltips=[
                                   ('weekday', '@x'),
                                   ('reviews', '@top')
                               ],
                               url_help='https://gitlab.com/cauldronio/cauldron/'
                                        '-/blob/master/guides/project_metrics.md#-reviews-open-by-weekday')

    return json.dumps(json_item(plot))


def reviews_closed_weekday_bokeh(elastic):
    """Get reviews closed by week day"""
    s = Search(using=elastic, index='all') \
        .query('bool', filter=((Q('match', pull_request=True) | Q('match', merge_request=True)) &
                               Q('exists', field='closed_at'))) \
        .extra(size=0)
    s.aggs.bucket('review_weekday', 'terms', script="doc['closed_at'].value.dayOfWeek", size=7)

    try:
        response = s.execute()
        reviews_bucket = response.aggregations.review_weekday.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        reviews_bucket = []

    # Create the Bokeh visualization
    reviews_dict = defaultdict(int)
    for weekday_item in reviews_bucket:
        reviews_dict[weekday_item.key] = weekday_item.doc_count

    reviews = []
    for i, k in enumerate(WEEKDAY):
        reviews.append(reviews_dict[str(i + 1)])

    plot = weekday_vbar_figure(top=reviews,
                               y_axis_label='# Reviews',
                               title='# Reviews closed by weekday',
                               tooltips=[
                                   ('weekday', '@x'),
                                   ('reviews', '@top')
                               ],
                               url_help='https://gitlab.com/cauldronio/cauldron/'
                                        '-/blob/master/guides/project_metrics.md#-reviews-closed-by-weekday')

    return json.dumps(json_item(plot))
