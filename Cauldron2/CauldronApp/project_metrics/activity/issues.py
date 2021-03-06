import json
import logging
from collections import defaultdict
from datetime import timedelta
import calendar
import pandas
import re
from functools import reduce

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.models import BasicTicker, ColorBar, LinearColorMapper, PrintfTickFormatter
from bokeh.palettes import Blues, Category10
from bokeh.plotting import figure

from CauldronApp.models import Project

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from ..utils import configure_figure, configure_heatmap, get_interval, weekday_vbar_figure, WEEKDAY

logger = logging.getLogger(__name__)


def issues_opened(elastic, urls, from_date, to_date):
    """Get number of created issues in GitHub and GitLab in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))
    if urls:
        s = s.filter(Q('terms', origin=urls))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 'X'


def issues_closed(elastic, urls, from_date, to_date):
    """Get number of closed issues in GitHub and GitLab in period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es})\
        .filter('match', state='closed')\
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))
    if urls:
        s = s.filter(Q('terms', origin=urls))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 'X'


def issues_open_on(elastic, urls, date):
    """Get the number of issues that were open on a specific day"""
    s = Search(using=elastic, index='all') \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .filter(Q('terms', origin=urls)) \
        .filter(Q('range', created_at={'lte': date}) &
               (Q('range', closed_at={'gte': date}) | Q('terms', state=['open', 'opened'])))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 'X'


def issues_created_bokeh_compare(elastics, from_date, to_date):
    """Generates a projects comparison about issues created"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    dates_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]

        s = Search(using=elastic, index='all') \
            .filter('range', created_at={'gte': from_date, 'lte': to_date}) \
            .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
            .extra(size=0)
        s.aggs.bucket('dates', 'date_histogram', field='created_at', calendar_interval=interval_elastic)

        try:
            response = s.execute()
            buckets = response.aggregations.dates.buckets
        except ElasticsearchException as e:
            logger.warning(e)
            buckets = []

        dates_buckets[project_id] = buckets

    data = []
    for project_id in dates_buckets:
        dates_bucket = dates_buckets[project_id]

        # Create the data structure
        issues, timestamps = [], []
        for item in dates_bucket:
            timestamps.append(item.key)
            issues.append(item.doc_count)

        data.append(pandas.DataFrame(list(zip(timestamps, issues)),
                    columns =['timestamps', f'issues_{project_id}']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Issues created'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/issues-created-chart.md')
    if not data.empty:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=data)

    names = []
    tooltips = [(interval_name, '@timestamps{%F}')]
    for idx, project_id in enumerate(dates_buckets):
        try:
            project = Project.objects.get(pk=project_id)
            project_name = project.name
        except Project.DoesNotExist:
            project_name = "Unknown"

        if idx == 0:
            names.append(f'issues_{project_id}')

        tooltips.append((f'issues created ({project_name})', f'@issues_{project_id}'))

        plot.circle(x='timestamps', y=f'issues_{project_id}',
                    name=f'issues_{project_id}',
                    color=Category10[5][idx],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y=f'issues_{project_id}',
                  line_width=4,
                  line_color=Category10[5][idx],
                  legend_label=project_name,
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


def issues_closed_bokeh_compare(elastics, from_date, to_date):
    """Generates a projects comparison about issues closed"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    dates_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]

        s = Search(using=elastic, index='all') \
            .filter('range', closed_at={'gte': from_date, 'lte': to_date}) \
            .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
            .extra(size=0)
        s.aggs.bucket('dates', 'date_histogram', field='closed_at', calendar_interval=interval_elastic)

        try:
            response = s.execute()
            buckets = response.aggregations.dates.buckets
        except ElasticsearchException as e:
            logger.warning(e)
            buckets = []

        dates_buckets[project_id] = buckets

    data = []
    for project_id in dates_buckets:
        dates_bucket = dates_buckets[project_id]

        # Create the data structure
        issues, timestamps = [], []
        for item in dates_bucket:
            timestamps.append(item.key)
            issues.append(item.doc_count)

        data.append(pandas.DataFrame(list(zip(timestamps, issues)),
                    columns =['timestamps', f'issues_{project_id}']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Issues closed'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/issues-closed-chart.md')
    if not data.empty:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=data)

    names = []
    tooltips = [(interval_name, '@timestamps{%F}')]
    for idx, project_id in enumerate(dates_buckets):
        try:
            project = Project.objects.get(pk=project_id)
            project_name = project.name
        except Project.DoesNotExist:
            project_name = "Unknown"

        if idx == 0:
            names.append(f'issues_{project_id}')

        tooltips.append((f'issues closed ({project_name})', f'@issues_{project_id}'))

        plot.circle(x='timestamps', y=f'issues_{project_id}',
                    name=f'issues_{project_id}',
                    color=Category10[5][idx],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y=f'issues_{project_id}',
                  line_width=4,
                  line_color=Category10[5][idx],
                  legend_label=project_name,
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


def issues_open_closed_bokeh(elastic, urls, from_date, to_date):
    """Visualization of opened and closed issues in the specified time rage"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)
    s = Search(using=elastic, index='all') \
        .filter('bool', filter=(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))) \
        .filter(Q('terms', origin=urls)) \
        .extra(size=0)
    s.aggs.bucket('range_open', 'filter', Q('range', created_at={'gte': from_date_es, "lte": to_date}))\
        .bucket('open', 'date_histogram', field='created_at', calendar_interval=interval_elastic)
    s.aggs.bucket('range_closed', 'filter', Q('range', closed_at={'gte': from_date_es, "lte": to_date}))\
        .bucket('closed', 'date_histogram', field='closed_at', calendar_interval=interval_elastic)

    try:
        response = s.execute()
        closed_buckets = response.aggregations.range_closed.closed.buckets
        open_buckets = response.aggregations.range_open.open.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        closed_buckets = []
        open_buckets = []

    # Create the data structure
    timestamps_closed, issues_closed = [], []
    for citem in closed_buckets:
        timestamps_closed.append(citem.key)
        issues_closed.append(citem.doc_count)

    timestamps_created, issues_created = [], []
    for oitem in open_buckets:
        timestamps_created.append(oitem.key)
        issues_created.append(oitem.doc_count)

    data = []
    data.append(pandas.DataFrame(list(zip(timestamps_closed, issues_closed)),
                columns =['timestamps', 'issues_closed']))
    data.append(pandas.DataFrame(list(zip(timestamps_created, issues_created)),
                columns =['timestamps', 'issues_created']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/issues-created-closed.md')
    plot.title.text = '# Issues created/closed'
    if not data.empty:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=data)

    plot.circle(x='timestamps', y='issues_closed',
                color=Blues[3][0],
                size=8,
                source=source)

    plot.line(x='timestamps', y='issues_closed',
              line_width=4,
              line_color=Blues[3][0],
              legend_label='issues closed',
              source=source)

    plot.circle(x='timestamps', y='issues_created',
                name='issues_created',
                color=Blues[3][1],
                size=8,
                source=source)

    plot.line(x='timestamps', y='issues_created',
              line_width=4,
              line_color=Blues[3][1],
              legend_label='issues created',
              source=source)

    plot.add_tools(tools.HoverTool(
        names=['issues_created'],
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('issues created', '@issues_created'),
            ('issues closed', '@issues_closed')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def issues_open_age_opened_bokeh(elastic):
    """Get a visualization of current open issues age"""
    s = Search(using=elastic, index='all') \
        .filter('bool', filter=((Q('match', pull_request=False) |
                               Q('match', is_gitlab_issue=1)) &
                               Q('terms', state=['open', 'opened'])))\
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
                           '-/blob/master/guides/metrics/activity/open-issues-age.md')

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


def issues_open_weekday_bokeh(elastic, urls, from_date, to_date):
    """Get issues open per week day in the specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter('bool', filter=(Q('match', pull_request=False) |
                               Q('match', is_gitlab_issue=1))) \
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
                                        '-/blob/master/guides/metrics/activity/issues-open-by-weekday.md')

    return json.dumps(json_item(plot))


def issues_closed_weekday_bokeh(elastic, urls, from_date, to_date):
    """Get issues closed per week day in the specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter('bool', filter=((Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) &
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
                                        '-/blob/master/guides/metrics/activity/issues-closed-by-weekday.md')

    return json.dumps(json_item(plot))


def issues_opened_heatmap_bokeh(elastic, urls, from_date, to_date):
    """Get issues opened per week day and per hour of the day in the
    specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")

    s = Search(using=elastic, index='all') \
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)
    s.aggs.bucket('weekdays', 'terms', script="doc['created_at'].value.dayOfWeek", size=7, order={'_term': 'asc'}) \
          .bucket('hours', 'terms', script="doc['created_at'].value.getHourOfDay()", size=24, order={'_term': 'asc'})

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
        day = days[int(weekday.key) - 1]
        for hour in weekday.hours.buckets:
            data[day][hour.key] = hour.doc_count

    data = pandas.DataFrame(data)
    data.index.name = "Hour"
    data.columns.name = "Day"

    df = pandas.DataFrame(data.stack(), columns=['issues']).reset_index()

    colors = ["#ffffff", "#dfdfff", "#bfbfff", "#9f9fff", "#7f7fff", "#5f5fff", "#3f3fff", "#1f1fff", "#0000ff"]
    mapper = LinearColorMapper(palette=colors, low=df.issues.min(), high=df.issues.max())

    TOOLS = "hover,save,pan,box_zoom,reset,wheel_zoom"

    plot = figure(title="Issues Opened Heatmap",
                  x_range=days, y_range=list(reversed(hours)),
                  x_axis_location="above", height=400,
                  sizing_mode="stretch_width",
                  tools=TOOLS, toolbar_location='below',
                  tooltips=[('date', '@Day @ @Hour{00}:00'), ('issues', '@issues')])

    configure_heatmap(plot, 'https://gitlab.com/cauldronio/cauldron/'
                            '-/blob/master/guides/metrics/activity/issues-opened-heatmap.md')

    plot.rect(x="Day", y="Hour", width=1, height=1,
              source=df,
              fill_color={'field': 'issues', 'transform': mapper},
              line_color=None)

    color_bar = ColorBar(color_mapper=mapper,
                         ticker=BasicTicker(desired_num_ticks=len(colors)),
                         formatter=PrintfTickFormatter(format="%d"),
                         label_standoff=6, border_line_color=None,
                         location=(0, 0))
    plot.add_layout(color_bar, 'right')

    return json.dumps(json_item(plot))


def issues_closed_heatmap_bokeh(elastic, urls, from_date, to_date):
    """Get issues closed per week day and per hour of the day in the
    specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")

    s = Search(using=elastic, index='all') \
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)
    s.aggs.bucket('weekdays', 'terms', script="doc['closed_at'].value.dayOfWeek", size=7, order={'_term': 'asc'}) \
          .bucket('hours', 'terms', script="doc['closed_at'].value.getHourOfDay()", size=24, order={'_term': 'asc'})

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
        day = days[int(weekday.key) - 1]
        data[day] = dict.fromkeys(hours, 0)
        for hour in weekday.hours.buckets:
            data[day][hour.key] = hour.doc_count

    data = pandas.DataFrame(data)
    data.index.name = "Hour"
    data.columns.name = "Day"

    df = pandas.DataFrame(data.stack(), columns=['issues']).reset_index()

    colors = ["#ffffff", "#dfdfff", "#bfbfff", "#9f9fff", "#7f7fff", "#5f5fff", "#3f3fff", "#1f1fff", "#0000ff"]
    mapper = LinearColorMapper(palette=colors, low=df.issues.min(), high=df.issues.max())

    TOOLS = "hover,save,pan,box_zoom,reset,wheel_zoom"

    plot = figure(title="Issues Closed Heatmap",
                  x_range=days, y_range=list(reversed(hours)),
                  x_axis_location="above", height=400,
                  sizing_mode="stretch_width",
                  tools=TOOLS, toolbar_location='below',
                  tooltips=[('date', '@Day @ @Hour{00}:00'), ('issues', '@issues')])

    configure_heatmap(plot, 'https://gitlab.com/cauldronio/cauldron/'
                            '-/blob/master/guides/metrics/activity/issues-closed-heatmap.md')

    plot.rect(x="Day", y="Hour", width=1, height=1,
              source=df,
              fill_color={'field': 'issues', 'transform': mapper},
              line_color=None)

    color_bar = ColorBar(color_mapper=mapper,
                         ticker=BasicTicker(desired_num_ticks=len(colors)),
                         formatter=PrintfTickFormatter(format="%d"),
                         label_standoff=6, border_line_color=None,
                         location=(0, 0))
    plot.add_layout(color_bar, 'right')

    return json.dumps(json_item(plot))


def issues_created_by_repository(elastic, from_date, to_date):
    """Shows the number of issues created in a project
    grouped by repository"""
    s = Search(using=elastic, index='all') \
        .filter('range', created_at={'gte': from_date, 'lte': to_date}) \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)
    s.aggs.bucket('repositories', 'terms', field='repository', size=10)

    try:
        response = s.execute()
        repos_buckets = response.aggregations.repositories.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        repos_buckets = []

    data = {
        'repo': [],
        'value': []
    }
    for repo in repos_buckets:
        data['repo'].append(repo.key)
        data['value'].append(repo.doc_count)

    # Request for other repositories
    repos_ignored = [Q('match_phrase', repository=repo) for repo in data['repo']]

    s = Search(using=elastic, index='all') \
        .filter('range', created_at={'gte': from_date, 'lte': to_date}) \
        .filter('exists', field='repository') \
        .filter(Q('bool', must_not=repos_ignored)) \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)

    try:
        issues_other_repos = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        issues_other_repos = 0

    data['repo'].append('other')
    data['value'].append(issues_other_repos)

    # Remove the 'https://' string
    data['repo'] = [re.sub(r'^https?:\/\/', '', url) for url in data['repo']]

    # Flip the list
    data['repo'].reverse()
    data['value'].reverse()

    plot = figure(y_range=data['repo'],
                  y_axis_label='Repository',
                  x_axis_label='# Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    plot.title.text = '# Issues created by repository'
    configure_figure(plot,
                     'https://gitlab.com/cauldronio/cauldron/'
                     '-/blob/master/guides/metrics/activity/issues-created-by-repository.md',
                     vertical=False)

    source = ColumnDataSource(data=dict(
        repos=data['repo'],
        issues=data['value']
    ))

    plot.hbar(y='repos', right='issues',
              source=source,
              height=0.5,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('repo', '@repos'),
            ('issues', '@issues')
        ],
        mode='hline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def issues_closed_by_repository(elastic, from_date, to_date):
    """Shows the number of issues closed in a project
    grouped by repository"""
    s = Search(using=elastic, index='all') \
        .filter('range', closed_at={'gte': from_date, 'lte': to_date}) \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)
    s.aggs.bucket('repositories', 'terms', field='repository', size=10)

    try:
        response = s.execute()
        repos_buckets = response.aggregations.repositories.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        repos_buckets = []

    data = {
        'repo': [],
        'value': []
    }
    for repo in repos_buckets:
        data['repo'].append(repo.key)
        data['value'].append(repo.doc_count)

    # Request for other repositories
    repos_ignored = [Q('match_phrase', repository=repo) for repo in data['repo']]

    s = Search(using=elastic, index='all') \
        .filter('range', closed_at={'gte': from_date, 'lte': to_date}) \
        .filter('exists', field='repository') \
        .filter(Q('bool', must_not=repos_ignored)) \
        .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)

    try:
        issues_other_repos = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        issues_other_repos = 0

    data['repo'].append('other')
    data['value'].append(issues_other_repos)

    # Remove the 'https://' string
    data['repo'] = [re.sub(r'^https?:\/\/', '', url) for url in data['repo']]

    # Flip the list
    data['repo'].reverse()
    data['value'].reverse()

    plot = figure(y_range=data['repo'],
                  y_axis_label='Repository',
                  x_axis_label='# Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    plot.title.text = '# Issues closed by repository'
    configure_figure(plot,
                     'https://gitlab.com/cauldronio/cauldron/'
                     '-/blob/master/guides/metrics/activity/issues-closed-by-repository.md',
                     vertical=False)

    source = ColumnDataSource(data=dict(
        repos=data['repo'],
        issues=data['value']
    ))

    plot.hbar(y='repos', right='issues',
              source=source,
              height=0.5,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('repo', '@repos'),
            ('issues', '@issues')
        ],
        mode='hline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))
