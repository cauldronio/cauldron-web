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


def git_commits(elastic, from_date, to_date):
    """Get number of commits for a project"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('commits', 'cardinality', field='hash')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.commits.value or 0
    else:
        return 0


def git_lines_commit(elastic, from_date, to_date):
    """Get lines changed per commit in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('lines_avg', 'avg', field='lines_changed')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.lines_avg.value or 0
    else:
        return 0


def git_files_touched(elastic, from_date, to_date):
    """Get sum of files changed in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .extra(size=0)
    s.aggs.bucket('files_sum', 'sum', field='files')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.files_sum.value or 0
    else:
        return 0


def git_commits_bokeh(elastic, from_date, to_date):
    """ Get evolution of contributions by commits"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket("commits_per_day", 'date_histogram', field='grimoire_creation_date', calendar_interval='1w')

    try:
        response = s.execute()
        commits_bucket = response.aggregations.commits_per_day.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        commits_bucket = []

    # Create the Bokeh visualization
    timestamp, commits = [], []
    for week in commits_bucket:
        timestamp.append(week.key)
        commits.append(week.doc_count)

    plot = figure(x_axis_type="datetime",
                  y_axis_label='# Commits',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Commits over time'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md#-commits-over-time')
    plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        commits=commits,
        timestamp=timestamp
    ))

    # width = 1000 ms/s * 60 s/m * 60 m/h * 24 h/d * 7 d/w * 0.9 width
    plot.vbar(x='timestamp', top='commits',
              source=source,
              width=544320000,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('week', '@timestamp{%F}'),
            ('commits', '@commits')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def git_commits_weekday_bokeh(elastic):
    """Get commits per week day in the specified range of time"""
    s = Search(using=elastic, index='git') \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('commit_weekday', 'terms', script="doc['commit_date'].value.dayOfWeek", size=7)

    try:
        response = s.execute()
        commits_bucket = response.aggregations.commit_weekday.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        commits_bucket = []

    # Create the Bokeh visualization
    commits_dict = defaultdict(int)
    for weekday_item in commits_bucket:
        commits_dict[weekday_item.key] = weekday_item.doc_count

    commits = []
    for i, k in enumerate(WEEKDAY):
        commits.append(commits_dict[str(i+1)])

    plot = weekday_vbar_figure(top=commits,
                               y_axis_label='# Commits',
                               title='# Commits by weekday',
                               tooltips=[
                                   ('weekday', '@x'),
                                   ('commits', '@top')
                               ],
                               url_help='https://gitlab.com/cauldronio/cauldron/'
                                        '-/blob/master/guides/project_metrics.md#-commits-by-weekday')

    return json.dumps(json_item(plot))


def git_commits_hour_day_bokeh(elastic):
    """Get commits per hour of the day in the specified range of time"""
    s = Search(using=elastic, index='git')\
        .extra(size=0)
    s.aggs.bucket('commit_hour_day', 'terms', script="doc['commit_date'].value.getHourOfDay()", size=24)

    try:
        response = s.execute()
        commits_bucket = response.aggregations.commit_hour_day.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        commits_bucket = []

    # Create the Bokeh visualization
    hour, commits = [], []
    for week in commits_bucket:
        hour.append(int(week.key))
        commits.append(week.doc_count)

    plot = figure(y_axis_label='# Commits',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Commits by hour of the day'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md#-commits-by-hour-of-day')

    source = ColumnDataSource(data=dict(
        commits=commits,
        hour=hour,
    ))

    plot.vbar(x='hour', top='commits',
              source=source,
              width=.9,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('hour', '@hour'),
            ('commits', '@commits')
        ],
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def git_lines_changed_bokeh(elastic, from_date, to_date):
    """Evolution of lines added vs lines removed in Bokeh"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es})\
        .extra(size=0)

    s.aggs.bucket('changed', 'date_histogram', field='grimoire_creation_date', calendar_interval='1w')\
        .pipeline('removed_sum', 'sum', script={'source': 'doc.lines_removed.value * -1'})\
        .bucket('added_sum', 'sum', field='lines_added')

    try:
        response = s.execute()
        commits_bucket = response.aggregations.changed.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        commits_bucket = []

    # Create the Bokeh visualization
    lines_added, lines_removed, timestamp = [], [], []
    for week in commits_bucket:
        lines_added.append(week.added_sum.value)
        lines_removed.append(week.removed_sum.value)
        timestamp.append(week.key)

    plot = figure(x_axis_type="datetime",
                  y_axis_label='# Lines',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Lines added/removed'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/project_metrics.md#-lines-added-vs-removed')
    plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        lines_added=lines_added,
        lines_removed=lines_removed,
        timestamp=timestamp
    ))

    plot.varea('timestamp', 'lines_added',
               source=source,
               color=Blues[3][0],
               legend_label='Lines added')
    plot.varea('timestamp', 'lines_removed',
               source=source,
               color=Blues[3][1],
               legend_label='Lines removed')

    plot.legend.location = "top_left"
    return json.dumps(json_item(plot))
