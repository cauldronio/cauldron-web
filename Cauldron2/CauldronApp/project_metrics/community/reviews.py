import logging
import json

import pandas
from datetime import datetime, timedelta
from functools import reduce

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues, Greens, Greys, Reds, Category10
from bokeh.plotting import figure
from bokeh.transform import dodge

from CauldronApp.models import Project

from .common import get_seniority, is_still_active
from ..utils import configure_figure, get_interval

logger = logging.getLogger(__name__)


def active_submitters(elastic, urls, from_date, to_date):
    """Get number of review submitters for a project in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .filter(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)
    if urls:
        s = s.filter(Q('terms', origin=urls))
    s.aggs.bucket('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.authors.value or 0
    else:
        return 'X'


def authors_entering(elastic, urls, from_date, to_date):
    """Get number of authors of PRs/MRs entering in a project for a period of time"""
    s = Search(using=elastic, index='all') \
        .filter(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .filter(Q('terms', origin=urls)) \
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
        return 'X'


def review_submitters_buckets(elastic, urls, from_date, to_date, interval):
    """Makes a query to ES to get the number of review submitters grouped by date"""
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .filter(Q('terms', origin=urls)) \
        .extra(size=0)
    s.aggs.bucket("dates", 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
        dates_buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        dates_buckets = []

    return dates_buckets


def review_submitters_bokeh_compare(elastics, urls, from_date, to_date):
    """Generates a projects comparison about review submitters along the time"""
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    authors_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]
        authors_buckets[project_id] = review_submitters_buckets(elastic, urls, from_date, to_date, interval_elastic)

    data = []
    for project_id in authors_buckets:
        authors_bucket = authors_buckets[project_id]

        # Create the data structure
        timestamps, authors = [], []
        for item in authors_bucket:
            timestamps.append(item.key)
            authors.append(item.authors.value)

        data.append(pandas.DataFrame(list(zip(timestamps, authors)),
                    columns =['timestamps', f'authors_{project_id}']))

    # Merge the dataframes in case they have different lengths
    data = reduce(lambda df1,df2: pandas.merge(df1,df2,on='timestamps',how='outer',sort=True).fillna(0), data)

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Review submitters'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/authors-reviews.md')
    if not data.empty:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=data)

    names = []
    tooltips = [(interval_name, '@timestamps{%F}')]
    for idx, project_id in enumerate(authors_buckets):
        try:
            project = Project.objects.get(pk=project_id)
            project_name = project.name
        except Project.DoesNotExist:
            project_name = "Unknown"

        if idx == 0:
            names.append(f'authors_{project_id}')

        tooltips.append((f'submitters {project_name}', f'@authors_{project_id}'))

        plot.circle(x='timestamps', y=f'authors_{project_id}',
                    name=f'authors_{project_id}',
                    color=Category10[5][idx],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y=f'authors_{project_id}',
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


def authors_active_bokeh(elastic, urls, from_date, to_date):
    """Generates a visualization showing the review submitters along the time"""
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)

    authors_buckets = review_submitters_buckets(elastic, urls, from_date, to_date, interval_elastic)

    # Create the Bokeh visualization
    timestamp, authors = [], []
    for item in authors_buckets:
        timestamp.append(item.key)
        authors.append(item.authors.value)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Submitters',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/authors-reviews.md')
    plot.title.text = 'Active submitters (PRs/MRs)'
    if len(timestamp) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        authors=authors,
        timestamp=timestamp
    ))

    plot.vbar(x='timestamp', top='authors',
              source=source,
              width=bar_width,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamp{%F}'),
            ('submitters', '@authors')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def authors_entering_leaving_bokeh(elastic, urls, from_date, to_date):
    """Get a visualization of review submitters entering and leaving
    the project"""
    s = Search(using=elastic, index='all') \
        .filter(Q('terms', origin=urls)) \
        .filter(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_contribution', 'min', field='grimoire_creation_date') \
          .metric('last_contribution', 'max', field='grimoire_creation_date')

    try:
        response = s.execute()
        authors_buckets = response.aggregations.authors.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_buckets = []

    authors_first = {}
    authors_last = {}
    for author in authors_buckets:
        authors_first[author.key] = author.first_contribution.value / 1000
        authors_last[author.key] = author.last_contribution.value / 1000

    authors_first_df = pandas.DataFrame(authors_first.items(), columns=['author_id', 'first_contribution'])
    authors_last_df = pandas.DataFrame(authors_last.items(), columns=['author_id', 'last_contribution'])

    from_date_ts = datetime.timestamp(from_date)
    to_date_ts = datetime.timestamp(to_date)

    authors_first_range = authors_first_df[authors_first_df["first_contribution"].between(from_date_ts, to_date_ts)]
    authors_last_range = authors_last_df[authors_last_df["last_contribution"].between(from_date_ts, to_date_ts)]

    authors_first_range['first_contribution'] = pandas.to_datetime(authors_first_range['first_contribution'], unit='s')
    authors_first_range['first_contribution'] = authors_first_range['first_contribution'].apply(lambda x: x.date() - timedelta(days=x.weekday()))
    authors_grouped_first = authors_first_range.groupby('first_contribution').size().reset_index(name='first_contribution_counts')
    authors_grouped_first = authors_grouped_first.rename(columns={"first_contribution": "date"})

    authors_last_range['last_contribution'] = pandas.to_datetime(authors_last_range['last_contribution'], unit='s')
    authors_last_range['last_contribution'] = authors_last_range['last_contribution'].apply(lambda x: x.date() - timedelta(days=x.weekday()))
    authors_grouped_last = authors_last_range.groupby('last_contribution').size().reset_index(name='last_contribution_counts')
    authors_grouped_last = authors_grouped_last.rename(columns={"last_contribution": "date"})

    authors = pandas.merge(authors_grouped_first, authors_grouped_last, on='date', how='outer')
    authors = authors.sort_values('date').fillna(0)

    timestamps, authors_entering, authors_leaving, difference = [], [], [], []
    for index, row in authors.iterrows():
        timestamps.append(datetime.combine(row['date'], datetime.min.time()).timestamp() * 1000)

        authors_entering.append(row['first_contribution_counts'])
        authors_leaving.append(row['last_contribution_counts'] * -1)
        difference.append(authors_entering[-1] + authors_leaving[-1])

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Submitters',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = 'Submitters onboarding / last active (PRs/MRs)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/onboarding-last-active-reviews.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        onboardings=authors_entering,
        leavings=authors_leaving,
        difference=difference,
        timestamps=timestamps,
        zeros=[0]*len(timestamps)
    ))

    plot.varea('timestamps', y1='zeros', y2='onboardings',
               source=source,
               color=Blues[3][0],
               legend_label='Onboarding')
    plot.varea('timestamps', y1='zeros', y2='leavings',
               source=source,
               color=Blues[3][1],
               legend_label='Last activity')
    plot.line('timestamps', 'difference',
              line_width=4,
              line_color=Reds[3][0],
              legend_label='difference',
              source=source)

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('date', '@timestamps{%F}'),
            ('onboardings', '@onboardings'),
            ('last activity', '@leavings'),
            ('difference', '@difference')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    plot.legend.location = "top_left"
    return json.dumps(json_item(plot))


def authors_aging_bokeh(elastic, urls, snap_date):
    """Shows how many new review submitters joined the community during
    a corresponding period of time (attracted) and how many
    of these people are still active in the community (retained)"""
    snap_date_es = snap_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={"lt": snap_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_contribution', 'min', field='grimoire_creation_date') \
          .metric('last_contribution', 'max', field='grimoire_creation_date')

    try:
        response = s.execute()
        authors_buckets = response.aggregations.authors.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_buckets = []

    authors_first = {}
    authors_last = {}
    for author in authors_buckets:
        authors_first[author.key] = author.first_contribution.value / 1000
        authors_last[author.key] = author.last_contribution.value / 1000

    authors_first_df = pandas.DataFrame(authors_first.items(), columns=['author_id', 'first_contribution'])
    authors_last_df = pandas.DataFrame(authors_last.items(), columns=['author_id', 'last_contribution'])

    authors = pandas.merge(authors_first_df, authors_last_df, on='author_id')

    authors['first_contribution'] = pandas.to_datetime(authors['first_contribution'], unit='s')
    authors['last_contribution'] = pandas.to_datetime(authors['last_contribution'], unit='s')
    authors['seniority'] = authors['first_contribution'].apply(lambda x: get_seniority(x, snap_date))
    authors['still_active'] = authors['last_contribution'].apply(lambda x: is_still_active(x, snap_date))

    authors_attracted = authors.groupby('seniority').size().reset_index(name='attracted')

    authors_retained = authors.loc[authors['still_active']].groupby('seniority').size().reset_index(name='retained')

    authors_grouped = pandas.merge(authors_attracted, authors_retained, on='seniority', how='outer')
    authors_grouped = authors_grouped.fillna(0)

    seniority, attracted, retained = [], [], []
    for index, row in authors_grouped.iterrows():
        seniority.append(row['seniority'])
        attracted.append(row['attracted'])
        retained.append(row['retained'])

    plot = figure(x_axis_label='# People',
                  y_axis_label='Years',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.x_range.start = 0
    plot.title.text = f'Submitters aging as of {snap_date_es} (PRs/MRs)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/aging-reviews.md')

    source = ColumnDataSource(data=dict(
        seniority=seniority,
        attracted=attracted,
        retained=retained
    ))

    plot.hbar(y=dodge('seniority', 0.075), height=0.15,
              right='attracted',
              source=source,
              color=Greens[3][0],
              legend_label='Attracted')
    plot.hbar(y=dodge('seniority', -0.075), height=0.15,
              right='retained',
              source=source,
              color=Blues[3][0],
              legend_label='Retained')

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('seniority', '@seniority{0.0}'),
            ('attracted', '@attracted'),
            ('retained', '@retained')
        ],
        mode='hline',
        toggleable=False
    ))

    plot.legend.location = "top_right"
    return json.dumps(json_item(plot))


def authors_retained_ratio_bokeh(elastic, urls, snap_date):
    """Shows the ratio between retained and non-retained
    review submitters in a community"""
    snap_date_es = snap_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={"lt": snap_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter(Q('match', pull_request=True) | Q('match', merge_request=True)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_contribution', 'min', field='grimoire_creation_date') \
          .metric('last_contribution', 'max', field='grimoire_creation_date')

    try:
        response = s.execute()
        authors_buckets = response.aggregations.authors.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_buckets = []

    authors_first = {}
    authors_last = {}
    for author in authors_buckets:
        authors_first[author.key] = author.first_contribution.value / 1000
        authors_last[author.key] = author.last_contribution.value / 1000

    authors_first_df = pandas.DataFrame(authors_first.items(), columns=['author_id', 'first_contribution'])
    authors_last_df = pandas.DataFrame(authors_last.items(), columns=['author_id', 'last_contribution'])

    authors = pandas.merge(authors_first_df, authors_last_df, on='author_id')

    authors['first_contribution'] = pandas.to_datetime(authors['first_contribution'], unit='s')
    authors['last_contribution'] = pandas.to_datetime(authors['last_contribution'], unit='s')
    authors['seniority'] = authors['first_contribution'].apply(lambda x: get_seniority(x, snap_date))
    authors['still_active'] = authors['last_contribution'].apply(lambda x: is_still_active(x, snap_date))

    authors_attracted = authors.groupby('seniority').size().reset_index(name='attracted')

    authors_retained = authors.loc[authors['still_active']].groupby('seniority').size().reset_index(name='retained')

    authors_grouped = pandas.merge(authors_attracted, authors_retained, on='seniority', how='outer')
    authors_grouped = authors_grouped.fillna(0)

    seniority, retained_ratio, non_retained_ratio = [], [], []
    for index, row in authors_grouped.iterrows():
        seniority.append(row['seniority'])
        retained_ratio.append(row['retained']/row['attracted'])
        non_retained_ratio.append(1-row['retained']/row['attracted'])

    plot = figure(x_range=(0, 1.25),
                  x_axis_label='Ratio',
                  y_axis_label='Years',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = f'Submitters retained ratio as of {snap_date_es} (PRs/MRs)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/retained-ratio-reviews.md')

    source = ColumnDataSource(data=dict(
        seniority=seniority,
        retained_ratio=retained_ratio,
        non_retained_ratio=non_retained_ratio
    ))

    plot.hbar_stack(y='seniority', height=0.3,
                    stackers=['retained_ratio', 'non_retained_ratio'],
                    source=source,
                    color=[Blues[3][0], Greys[4][1]],
                    legend_label=['Retained', 'Non retained'])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('seniority', '@seniority{0.0}'),
            ('retained', '@retained_ratio{0.00}'),
            ('non retained', '@non_retained_ratio{0.00}')
        ],
        toggleable=False
    ))

    plot.legend.location = "top_right"
    return json.dumps(json_item(plot))
