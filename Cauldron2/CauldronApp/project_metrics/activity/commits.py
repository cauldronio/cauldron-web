import json
import logging
from collections import defaultdict
from datetime import timedelta
import calendar
import pandas
from functools import reduce

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.models import BasicTicker, ColorBar, LinearColorMapper, PrintfTickFormatter
from bokeh.palettes import Blues, Category10
from bokeh.plotting import figure

from CauldronApp.models import Dashboard

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from ..utils import configure_figure, configure_heatmap, get_interval, weekday_vbar_figure, WEEKDAY

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
        return 'X'


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
        return 'X'


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
        return 'X'


def git_commits_bucket(elastic, from_date, to_date, interval):
    """ Makes a query to ES to get the number of commits grouped by date """
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket("commits", 'date_histogram', field='grimoire_creation_date',
                  calendar_interval=interval)

    try:
        response = s.execute()
        commits_bucket = response.aggregations.commits.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        commits_bucket = []

    return commits_bucket

def git_commits_bokeh_compare(elastics, from_date, to_date):
    """ Get a projects comparison of evolution of contributions by commits"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)

    commits_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]
        commits_buckets[project_id] = git_commits_bucket(elastic, from_date_es, to_date_es, interval_elastic)

    data = []
    for project_id in commits_buckets:
        commits_bucket = commits_buckets[project_id]

        # Create the data structure
        commits, timestamps = [], []
        for week in commits_bucket:
            timestamps.append(week.key)
            commits.append(week.doc_count)

        data.append(pandas.DataFrame(list(zip(timestamps, commits)),
                    columns =['timestamps', f'commits_{project_id}']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Commits',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Commits over time'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/commits-over-time.md')
    if not data.empty:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=data)

    names = []
    tooltips = [(interval_name, '@timestamps{%F}')]
    for idx, project_id in enumerate(commits_buckets):
        try:
            dash = Dashboard.objects.get(pk=project_id)
            dash_name = dash.name
        except Dashboard.DoesNotExist:
            dash_name = "Unknown"

        if idx == 0:
            names.append(f'commits_{project_id}')

        tooltips.append((f'commits {dash_name}', f'@commits_{project_id}'))

        plot.line(x='timestamps', y=f'commits_{project_id}',
                  name=f'commits_{project_id}',
                  line_width=4,
                  line_color=Category10[5][idx],
                  legend_label=dash_name,
                  source=source)

    plot.add_tools(tools.HoverTool(
        names=names,
        tooltips=tooltips,
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def git_commits_bokeh(elastic, from_date, to_date):
    """ Get evolution of contributions by commits"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)

    commits_bucket = git_commits_bucket(elastic, from_date_es, to_date_es, interval_elastic)

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
                           '-/blob/master/guides/metrics/activity/commits-over-time.md')
    if len(timestamp) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        commits=commits,
        timestamp=timestamp
    ))

    # width = 1000 ms/s * 60 s/m * 60 m/h * 24 h/d * 7 d/w * 0.9 width
    plot.vbar(x='timestamp', top='commits',
              source=source,
              width=bar_width,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamp{%F}'),
            ('commits', '@commits')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def git_commits_weekday_bokeh(elastic, from_date, to_date):
    """Get commits per week day in the specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
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
                                        '-/blob/master/guides/metrics/activity/commits-by-weekday.md')

    return json.dumps(json_item(plot))


def git_commits_hour_day_bokeh(elastic, from_date, to_date):
    """Get commits per hour of the day in the specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(~Q('match', files=0)) \
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
                           '-/blob/master/guides/metrics/activity/commits-by-hour-of-day.md')

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


def git_commits_heatmap_bokeh(elastic, from_date, to_date):
    """Get commits per week day and per hour of the day in the
    specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")

    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('weekdays', 'terms', field='commit_date_weekday', size=7, order={'_term': 'asc'}) \
          .bucket('hours', 'terms', field='commit_date_hour', size=24, order={'_term': 'asc'})

    try:
        response = s.execute()
        weekdays = response.aggregations.weekdays.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        weekdays = []

    days = list(calendar.day_abbr)
    hours = list(map(str, range(24)))

    data = dict.fromkeys(days)
    for day in days:
        data[day] = dict.fromkeys(hours, 0)

    for weekday in weekdays:
        day = days[weekday.key - 1]
        data[day] = dict.fromkeys(hours, 0)
        for hour in weekday.hours:
            data[day][str(hour.key)] = hour.doc_count

    data = pandas.DataFrame(data)
    data.index.name = "Hour"
    data.columns.name = "Day"

    df = pandas.DataFrame(data.stack(), columns=['commits']).reset_index()

    colors = ["#ffffff", "#dfdfff", "#bfbfff", "#9f9fff", "#7f7fff", "#5f5fff", "#3f3fff", "#1f1fff", "#0000ff"]
    mapper = LinearColorMapper(palette=colors, low=df.commits.min(), high=df.commits.max())

    TOOLS = "hover,save,pan,box_zoom,reset,wheel_zoom"

    plot = figure(title="# Commits by hour and weekday (local time of commit author)",
                  x_range=days, y_range=list(reversed(hours)),
                  x_axis_location="above", height=400,
                  sizing_mode="stretch_width",
                  tools=TOOLS, toolbar_location='below',
                  tooltips=[('date', '@Day @ @Hour{00}:00'), ('commits', '@commits')])

    configure_heatmap(plot, 'https://gitlab.com/cauldronio/cauldron/'
                            '-/blob/master/guides/metrics/activity/commits-heatmap.md')

    plot.rect(x="Day", y="Hour", width=1, height=1,
              source=df,
              fill_color={'field': 'commits', 'transform': mapper},
              line_color=None)

    color_bar = ColorBar(color_mapper=mapper,
                         ticker=BasicTicker(desired_num_ticks=len(colors)),
                         formatter=PrintfTickFormatter(format="%d"),
                         label_standoff=6, border_line_color=None,
                         location=(0, 0))
    plot.add_layout(color_bar, 'right')

    return json.dumps(json_item(plot))


def git_lines_changed_bokeh(elastic, from_date, to_date):
    """Evolution of lines added vs lines removed in Bokeh"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es})\
        .extra(size=0)

    s.aggs.bucket('changed', 'date_histogram', field='grimoire_creation_date', calendar_interval=interval_elastic)\
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
                           '-/blob/master/guides/metrics/activity/lines-added-removed.md')
    if len(timestamp) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        lines_added=lines_added,
        lines_removed=lines_removed,
        timestamp=timestamp,
        zeros=[0] * len(timestamp)
    ))

    plot.varea('timestamp', y1='zeros', y2='lines_added',
               source=source,
               color=Blues[3][0],
               legend_label='Lines added')
    plot.varea('timestamp', y1='zeros', y2='lines_removed',
               source=source,
               color=Blues[3][1],
               legend_label='Lines removed')

    plot.legend.location = "top_left"
    return json.dumps(json_item(plot))
