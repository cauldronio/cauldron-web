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


def reviews_opened(elastic, urls, from_date, to_date):
    """Get number of Merge requests and Pull requests opened in the specified range"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 'X'


def reviews_closed(elastic, urls, from_date, to_date):
    """Get number of Merge requests and Pull requests closed in the specified range"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 'X'


def reviews_open_on(elastic, urls, date):
    """Get the number of reviews that were open on a specific day"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .query(Q('terms', origin=urls)) \
        .query(Q('range', created_at={'lte': date}) &
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


def reviews_created_bokeh_compare(elastics, from_date, to_date):
    """Generates a projects comparison about reviews created"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    dates_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]

        s = Search(using=elastic, index='all') \
            .filter('range', created_at={'gte': from_date, 'lte': to_date}) \
            .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
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
        reviews, timestamps = [], []
        for item in dates_bucket:
            timestamps.append(item.key)
            reviews.append(item.doc_count)

        data.append(pandas.DataFrame(list(zip(timestamps, reviews)),
                    columns =['timestamps', f'reviews_{project_id}']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Reviews created over time'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/reviews-created-chart.md')
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
            names.append(f'reviews_{project_id}')

        tooltips.append((f'reviews created ({project_name})', f'@reviews_{project_id}'))

        plot.circle(x='timestamps', y=f'reviews_{project_id}',
                    name=f'reviews_{project_id}',
                    color=Category10[5][idx],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y=f'reviews_{project_id}',
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


def reviews_closed_bokeh_compare(elastics, from_date, to_date):
    """Generates a projects comparison about reviews closed"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    dates_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]

        s = Search(using=elastic, index='all') \
            .filter('range', closed_at={'gte': from_date, 'lte': to_date}) \
            .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
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
        reviews, timestamps = [], []
        for item in dates_bucket:
            timestamps.append(item.key)
            reviews.append(item.doc_count)

        data.append(pandas.DataFrame(list(zip(timestamps, reviews)),
                    columns =['timestamps', f'reviews_{project_id}']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Reviews closed over time'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/reviews-closed-chart.md')
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
            names.append(f'reviews_{project_id}')

        tooltips.append((f'reviews closed ({project_name})', f'@reviews_{project_id}'))

        plot.circle(x='timestamps', y=f'reviews_{project_id}',
                    name=f'reviews_{project_id}',
                    color=Category10[5][idx],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y=f'reviews_{project_id}',
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


def reviews_open_closed_bokeh(elastic, urls, from_date, to_date):
    """Visualization of opened and closed reviews in the specified time rage"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)
    s = Search(using=elastic, index='all') \
        .query('bool', filter=(Q('match', pull_request=True) | Q('match', merge_request=True))) \
        .query(Q('terms', origin=urls)) \
        .extra(size=0)
    s.aggs.bucket('range_open', 'filter', Q('range', created_at={'gte': from_date_es, "lte": to_date_es})) \
        .bucket('open', 'date_histogram', field='created_at', calendar_interval=interval_elastic)
    s.aggs.bucket('range_closed', 'filter', Q('range', closed_at={'gte': from_date_es, "lte": to_date_es})) \
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
    timestamps_closed, reviews_closed = [], []
    for citem in closed_buckets:
        timestamps_closed.append(citem.key)
        reviews_closed.append(citem.doc_count)

    timestamps_created, reviews_created = [], []
    for oitem in open_buckets:
        timestamps_created.append(oitem.key)
        reviews_created.append(oitem.doc_count)

    data = []
    data.append(pandas.DataFrame(list(zip(timestamps_closed, reviews_closed)),
                columns =['timestamps', 'reviews_closed']))
    data.append(pandas.DataFrame(list(zip(timestamps_created, reviews_created)),
                columns =['timestamps', 'reviews_created']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Reviews open/closed'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/activity/reviews-open-closed.md')
    if not data.empty:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=data)

    plot.circle(x='timestamps', y='reviews_closed',
                color=Blues[3][0],
                size=8,
                source=source)

    plot.line(x='timestamps', y='reviews_closed',
              line_width=4,
              line_color=Blues[3][0],
              legend_label='reviews closed',
              source=source)

    plot.circle(x='timestamps', y='reviews_created',
                name='reviews_created',
                color=Blues[3][1],
                size=8,
                source=source)

    plot.line(x='timestamps', y='reviews_created',
              line_width=4,
              line_color=Blues[3][1],
              legend_label='reviews created',
              source=source)

    plot.add_tools(tools.HoverTool(
        names=['reviews_created'],
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('reviews created', '@reviews_created'),
            ('reviews closed', '@reviews_closed')
        ],
        formatters={
            '@timestamps': 'datetime'
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
               Q('terms', state=['open', 'opened']))) \
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
                           '-/blob/master/guides/metrics/activity/open-reviews-age.md')

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


def reviews_open_weekday_bokeh(elastic, urls, from_date, to_date):
    """Get reviews open per week day in the specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('terms', origin=urls)) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
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
                                        '-/blob/master/guides/metrics/activity/reviews-open-by-weekday.md')

    return json.dumps(json_item(plot))


def reviews_closed_weekday_bokeh(elastic, urls, from_date, to_date):
    """Get reviews closed by week day in the specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('terms', origin=urls)) \
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
                                        '-/blob/master/guides/metrics/activity/reviews-closed-by-weekday.md')

    return json.dumps(json_item(plot))


def reviews_opened_heatmap_bokeh(elastic, urls, from_date, to_date):
    """Get reviews opened per week day and per hour of the day in the
    specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")

    s = Search(using=elastic, index='all') \
        .filter('range', created_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('terms', origin=urls)) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
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

    df = pandas.DataFrame(data.stack(), columns=['reviews']).reset_index()

    colors = ["#ffffff", "#dfdfff", "#bfbfff", "#9f9fff", "#7f7fff", "#5f5fff", "#3f3fff", "#1f1fff", "#0000ff"]
    mapper = LinearColorMapper(palette=colors, low=df.reviews.min(), high=df.reviews.max())

    TOOLS = "hover,save,pan,box_zoom,reset,wheel_zoom"

    plot = figure(title="Reviews Opened Heatmap",
                  x_range=days, y_range=list(reversed(hours)),
                  x_axis_location="above", height=400,
                  sizing_mode="stretch_width",
                  tools=TOOLS, toolbar_location='below',
                  tooltips=[('date', '@Day @ @Hour{00}:00'), ('reviews', '@reviews')])

    configure_heatmap(plot, 'https://gitlab.com/cauldronio/cauldron/'
                            '-/blob/master/guides/metrics/activity/reviews-opened-heatmap.md')

    plot.rect(x="Day", y="Hour", width=1, height=1,
              source=df,
              fill_color={'field': 'reviews', 'transform': mapper},
              line_color=None)

    color_bar = ColorBar(color_mapper=mapper,
                         ticker=BasicTicker(desired_num_ticks=len(colors)),
                         formatter=PrintfTickFormatter(format="%d"),
                         label_standoff=6, border_line_color=None,
                         location=(0, 0))
    plot.add_layout(color_bar, 'right')

    return json.dumps(json_item(plot))


def reviews_closed_heatmap_bokeh(elastic, urls, from_date, to_date):
    """Get reviews closed per week day and per hour of the day in the
    specified range of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")

    s = Search(using=elastic, index='all') \
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('terms', origin=urls)) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
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
        for hour in weekday.hours.buckets:
            data[day][hour.key] = hour.doc_count

    data = pandas.DataFrame(data)
    data.index.name = "Hour"
    data.columns.name = "Day"

    df = pandas.DataFrame(data.stack(), columns=['reviews']).reset_index()

    colors = ["#ffffff", "#dfdfff", "#bfbfff", "#9f9fff", "#7f7fff", "#5f5fff", "#3f3fff", "#1f1fff", "#0000ff"]
    mapper = LinearColorMapper(palette=colors, low=df.reviews.min(), high=df.reviews.max())

    TOOLS = "hover,save,pan,box_zoom,reset,wheel_zoom"

    plot = figure(title="Reviews Closed Heatmap",
                  x_range=days, y_range=list(reversed(hours)),
                  x_axis_location="above", height=400,
                  sizing_mode="stretch_width",
                  tools=TOOLS, toolbar_location='below',
                  tooltips=[('date', '@Day @ @Hour{00}:00'), ('reviews', '@reviews')])

    configure_heatmap(plot, 'https://gitlab.com/cauldronio/cauldron/'
                            '-/blob/master/guides/metrics/activity/reviews-closed-heatmap.md')

    plot.rect(x="Day", y="Hour", width=1, height=1,
              source=df,
              fill_color={'field': 'reviews', 'transform': mapper},
              line_color=None)

    color_bar = ColorBar(color_mapper=mapper,
                         ticker=BasicTicker(desired_num_ticks=len(colors)),
                         formatter=PrintfTickFormatter(format="%d"),
                         label_standoff=6, border_line_color=None,
                         location=(0, 0))
    plot.add_layout(color_bar, 'right')

    return json.dumps(json_item(plot))


def reviews_created_by_repository(elastic, from_date, to_date):
    """Shows the number of reviews created in a project
    grouped by repository"""
    s = Search(using=elastic, index='all') \
        .filter('range', created_at={'gte': from_date, 'lte': to_date}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
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
        .query(Q('bool', must_not=repos_ignored)) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)

    try:
        reviews_other_repos = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        reviews_other_repos = 0

    data['repo'].append('other')
    data['value'].append(reviews_other_repos)

    # Remove the 'https://' string
    data['repo'] = [re.sub(r'^https?:\/\/', '', url) for url in data['repo']]

    # Flip the list
    data['repo'].reverse()
    data['value'].reverse()

    plot = figure(y_range=data['repo'],
                  y_axis_label='Repository',
                  x_axis_label='# Reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    plot.title.text = '# Reviews started by repository'
    configure_figure(plot,
                     'https://gitlab.com/cauldronio/cauldron/'
                     '-/blob/master/guides/metrics/activity/reviews-created-by-repository.md',
                     vertical=False)

    source = ColumnDataSource(data=dict(
        repos=data['repo'],
        reviews=data['value']
    ))

    plot.hbar(y='repos', right='reviews',
              source=source,
              height=0.5,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('repo', '@repos'),
            ('reviews', '@reviews')
        ],
        mode='hline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def reviews_closed_by_repository(elastic, from_date, to_date):
    """Shows the number of reviews closed in a project
    grouped by repository"""
    s = Search(using=elastic, index='all') \
        .query(Q('range', closed_at={'gte': from_date, 'lte': to_date}) | Q('range', merged_at={'gte': from_date, 'lte': to_date})) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
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
        .query(Q('range', closed_at={'gte': from_date, 'lte': to_date}) | Q('range', merged_at={'gte': from_date, 'lte': to_date})) \
        .filter('exists', field='repository') \
        .query(Q('bool', must_not=repos_ignored)) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)

    try:
        reviews_other_repos = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        reviews_other_repos = 0

    data['repo'].append('other')
    data['value'].append(reviews_other_repos)

    # Remove the 'https://' string
    data['repo'] = [re.sub(r'^https?:\/\/', '', url) for url in data['repo']]

    # Flip the list
    data['repo'].reverse()
    data['value'].reverse()

    plot = figure(y_range=data['repo'],
                  y_axis_label='Repository',
                  x_axis_label='# Reviews',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    plot.title.text = '# Reviews closed by repository'
    configure_figure(plot,
                     'https://gitlab.com/cauldronio/cauldron/'
                     '-/blob/master/guides/metrics/activity/reviews-closed-by-repository.md',
                     vertical=False)

    source = ColumnDataSource(data=dict(
        repos=data['repo'],
        reviews=data['value']
    ))

    plot.hbar(y='repos', right='reviews',
              source=source,
              height=0.5,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('repo', '@repos'),
            ('reviews', '@reviews')
        ],
        mode='hline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))
