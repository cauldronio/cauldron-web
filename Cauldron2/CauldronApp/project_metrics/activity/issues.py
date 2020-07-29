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


def issues_opened(elastic, from_date, to_date):
    """Get number of created issues in GitHub and GitLab in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 0


def issues_closed(elastic, from_date, to_date):
    """Get number of closed issues in GitHub and GitLab in period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es})\
        .filter('match', state='closed')\
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 0


def issues_open_on(elastic, date):
    """Get the number of issues that were open on a specific day"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))\
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


def issues_open_closed_bokeh(elastic, from_date, to_date):
    """Visualization of opened and closed issues in the specified time rage"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .query('bool', filter=(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)))\
        .extra(size=0)
    s.aggs.bucket('range_open', 'filter', Q('range', created_at={'gte': from_date_es, "lte": to_date}))\
        .bucket('open', 'date_histogram', field='created_at', calendar_interval='1w')
    s.aggs.bucket('range_closed', 'filter', Q('range', closed_at={'gte': from_date_es, "lte": to_date}))\
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
    c_timestamp, closed_issues, o_timestamp, open_issues = [], [], [], []
    for citem, oitem in zip(closed_buckets, open_buckets):
        c_timestamp.append(citem.key)
        o_timestamp.append(oitem.key)
        closed_issues.append(citem.doc_count)
        open_issues.append(oitem.doc_count)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md#-issues-openclosed')
    plot.title.text = '# Issues open/closed'
    if len(o_timestamp) > 0 or len(c_timestamp) > 0:
        plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        o_timestamp=o_timestamp,
        c_timestamp=c_timestamp,
        open_issues=open_issues,
        closed_issues=closed_issues
    ))

    plot.line(x='c_timestamp', y='closed_issues',
              line_width=4,
              line_color=Blues[3][0],
              legend_label='closed issues',
              source=source)
    plot.line(x='o_timestamp', y='open_issues',
              name='open_issues',
              line_width=4,
              line_color=Blues[3][1],
              legend_label='created issues',
              source=source)

    plot.add_tools(tools.HoverTool(
        names=['open_issues'],
        tooltips=[
            ('date', '@o_timestamp{%F}'),
            ('created issues', '@open_issues'),
            ('closed issues', '@closed_issues')
        ],
        formatters={
            '@o_timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def issues_open_age_opened_bokeh(elastic):
    """Get a visualization of current open issues age"""
    s = Search(using=elastic, index='all') \
        .query('bool', filter=((Q('match', pull_request=False) |
                               Q('match', is_gitlab_issue=1)) &
                               Q('match', state='open')))\
        .extra(size=0)
    s.aggs.bucket("open_issues", 'date_histogram', field='created_at', calendar_interval='1M')

    try:
        response = s.execute()
        open_buckets = response.aggregations.open_issues.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        open_buckets = []

    # Create the Bokeh visualization
    timestamp, issues = [], []
    for month in open_buckets:
        timestamp.append(month.key)
        issues.append(month.doc_count)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Open issues age'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md#-open-issues-age')

    source = ColumnDataSource(data=dict(
        issues=issues,
        timestamp=timestamp
    ))

    # width = 1000 ms/s * 60 s/m * 60 m/h * 24 h/d * 30 d/M * 0.8 width
    plot.vbar(x='timestamp', top='issues',
              source=source,
              width=2073600000,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('month', '@timestamp{%b %Y}'),
            ('issues', '@issues')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def issues_open_weekday_bokeh(elastic):
    """Get issues open per week day"""
    s = Search(using=elastic, index='all') \
        .query('bool', filter=(Q('match', pull_request=False) |
                               Q('match', is_gitlab_issue=1)))\
        .extra(size=0)
    s.aggs.bucket('issue_weekday', 'terms', script="doc['created_at'].value.dayOfWeek", size=7)

    try:
        response = s.execute()
        issues_bucket = response.aggregations.issue_weekday.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        issues_bucket = []

    # Create the Bokeh visualization
    issues_dict = defaultdict(int)
    for weekday_item in issues_bucket:
        issues_dict[weekday_item.key] = weekday_item.doc_count

    issues = []
    for i, k in enumerate(WEEKDAY):
        issues.append(issues_dict[str(i + 1)])

    plot = weekday_vbar_figure(top=issues,
                               y_axis_label='# Issues',
                               title='# Issues open by weekday',
                               tooltips=[
                                   ('weekday', '@x'),
                                   ('issues', '@top')
                               ],
                               url_help='https://gitlab.com/cauldronio/cauldron/'
                                        '-/blob/master/guides/project_metrics.md#-issues-open-by-weekday')

    return json.dumps(json_item(plot))


def issues_closed_weekday_bokeh(elastic):
    """Get issues closed per week day"""
    s = Search(using=elastic, index='all') \
        .query('bool', filter=((Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) &
                               Q('exists', field='closed_at'))) \
        .extra(size=0)
    s.aggs.bucket('issue_weekday', 'terms', script="doc['closed_at'].value.dayOfWeek", size=7)

    try:
        response = s.execute()
        issues_bucket = response.aggregations.issue_weekday.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        issues_bucket = []

    # Create the Bokeh visualization
    issues_dict = defaultdict(int)
    for weekday_item in issues_bucket:
        issues_dict[weekday_item.key] = weekday_item.doc_count

    issues = []
    for i, k in enumerate(WEEKDAY):
        issues.append(issues_dict[str(i + 1)])

    plot = weekday_vbar_figure(top=issues,
                               y_axis_label='# Issues',
                               title='# Issues closed by weekday',
                               tooltips=[
                                   ('weekday', '@x'),
                                   ('issues', '@top')
                               ],
                               url_help='https://gitlab.com/cauldronio/cauldron/'
                                        '-/blob/master/guides/project_metrics.md#-issues-closed-by-weekday')

    return json.dumps(json_item(plot))