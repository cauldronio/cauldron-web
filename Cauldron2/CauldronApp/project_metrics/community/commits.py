import logging
import json

import pandas
from datetime import datetime, timedelta
from functools import reduce

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues, Greens, Greys, Reds, Category10, Oranges
from bokeh.plotting import figure
from bokeh.transform import dodge

from CauldronApp.models import Project

from .common import get_seniority, is_still_active, get_contributor_type
from ..utils import configure_figure, get_interval

logger = logging.getLogger(__name__)


def authors_active(elastic, urls, from_date, to_date):
    """Get number of git authors active for a project in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .filter(~Q('match', files=0)) \
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


def get_authors_bucket(elastic, urls, from_date, to_date, interval):
    """ Makes a query to ES to get the number of authors grouped by date """
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .filter(Q('terms', origin=urls)) \
        .filter(~Q('match', files=0)) \
        .extra(size=0)

    s.aggs.bucket("bucket1", 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
        authors_bucket = response.aggregations.bucket1.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_bucket = []

    return authors_bucket


def git_authors_bokeh_compare(elastics, urls, from_date, to_date):
    """ Get a projects comparison of the number of git authors active
    for a project in a period of time """
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    authors_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]
        authors_buckets[project_id] = get_authors_bucket(elastic, urls, from_date_es, to_date_es, interval_elastic)

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
    plot.title.text = '# Git authors'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/authors-commits.md')
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

        tooltips.append((f'authors {project_name}', f'@authors_{project_id}'))

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
    """Get evolution of Authors in commits"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)

    authors_buckets = get_authors_bucket(elastic, urls, from_date_es, to_date_es, interval_elastic)

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
                           '-/blob/master/guides/metrics/community/authors-commits.md')
    plot.title.text = 'Active authors (Git)'
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
            ('authors', '@authors')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def authors_entering(elastic, urls, from_date, to_date):
    """Get number of git authors entering in a project for a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter(~Q('match', files=0)) \
        .filter(Q('terms', origin=urls)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_commit', 'min', field='grimoire_creation_date')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        authors = {}
        for author in response.aggregations.authors.buckets:
            authors[author.key] = author.first_commit.value / 1000

        authors_df = pandas.DataFrame(authors.items(), columns=['author_id', 'first_commit'])

        from_date_ts = datetime.timestamp(from_date)
        to_date_ts = datetime.timestamp(to_date)

        return len(authors_df[authors_df["first_commit"].between(from_date_ts, to_date_ts)].index)
    else:
        return 'X'


def authors_entering_leaving_bokeh(elastic, urls, from_date, to_date):
    """Get a visualization of git authors entering and leaving the project"""
    s = Search(using=elastic, index='git') \
        .filter(Q('terms', origin=urls)) \
        .filter(~Q('match', files=0)) \
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
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = 'Authors onboarding / last active (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/onboarding-last-active-git.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        onboardings=authors_entering,
        leavings=authors_leaving,
        difference=difference,
        timestamps=timestamps,
        zeros=[0]*len(timestamps)
    ))

    plot.varea(x='timestamps', y1='zeros', y2='onboardings',
               source=source,
               color=Blues[3][0],
               legend_label='Onboarding')
    plot.varea(x='timestamps', y2='zeros', y1='leavings',
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
    """Shows how many new git authors joined the community during
    a corresponding period of time (attracted) and how many
    of these people are still active in the community (retained)"""
    snap_date_es = snap_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={"lt": snap_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter(~Q('match', files=0)) \
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
    plot.title.text = f'Authors aging as of {snap_date_es} (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/aging-git.md')

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
    git authors in a community"""
    snap_date_es = snap_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={"lt": snap_date_es}) \
        .filter(Q('terms', origin=urls)) \
        .filter(~Q('match', files=0)) \
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
    plot.title.text = f'Authors retained ratio as of {snap_date_es} (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/retained-ratio-git.md')

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


def drive_through_and_repeat_contributor_counts(elastic, urls, from_date, to_date):
    """Shows the drive-through and repeat contributors (git) counts in a community"""

    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)

    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={"lt": to_date}) \
        .filter(Q('terms', origin=urls)) \
        .filter(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_contribution', 'min', field='grimoire_creation_date') \
          .metric('total_contributions', 'cardinality', field='hash')

    try:
        response = s.execute()
        authors_buckets = response.aggregations.authors.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_buckets = []

    authors_first_contribution = {}
    authors_total_contributions = {}
    for author in authors_buckets:
        authors_first_contribution[author.key] = author.first_contribution.value / 1000
        authors_total_contributions[author.key] = author.total_contributions.value

    authors_first_contribution_df = pandas.DataFrame(authors_first_contribution.items(), columns=['author_id', 'first_contribution'])
    authors_total_contributions_df = pandas.DataFrame(authors_total_contributions.items(), columns=['author_id', 'total_contributions'])

    # Filter by date
    from_date_ts = datetime.timestamp(from_date)
    to_date_ts = datetime.timestamp(to_date)
    authors_first_contribution_df = authors_first_contribution_df[authors_first_contribution_df["first_contribution"].between(from_date_ts, to_date_ts)]

    authors = pandas.merge(authors_first_contribution_df, authors_total_contributions_df, on='author_id')

    # Round to day of the week or the month if necessary
    authors['first_contribution'] = pandas.to_datetime(authors['first_contribution'], unit='s')
    if interval_elastic == '1M':
        authors['first_contribution'] = authors['first_contribution'].apply(lambda x: x.date() - timedelta(days=(x.day-1)))
    elif interval_elastic == '1w':
        authors['first_contribution'] = authors['first_contribution'].apply(lambda x: x.date() - timedelta(days=x.weekday()))

    authors['contributor_type'] = authors['total_contributions'].apply(lambda x: get_contributor_type(x))

    # Group by drive-through authors
    drive_through_authors = authors.loc[authors['contributor_type'] == 'drive-through']
    drive_through_authors = drive_through_authors.groupby('first_contribution').size().reset_index(name='drive_through_authors')

    # Group by repeat authors
    repeat_authors = authors.loc[authors['contributor_type'] == 'repeat']
    repeat_authors = repeat_authors.groupby('first_contribution').size().reset_index(name='repeat_authors')

    authors = pandas.merge(drive_through_authors, repeat_authors, on='first_contribution', how='outer')
    authors = authors.sort_values('first_contribution')
    # Only the NaN values of drive_through_authors are turned into 0 to avoid
    # an ugly effect in the chart
    authors['drive_through_authors'] = authors['drive_through_authors'].fillna(0)

    timestamps, drive_through_authors, repeat_authors = [], [], []
    for index, row in authors.iterrows():
        timestamps.append(datetime.combine(row['first_contribution'], datetime.min.time()).timestamp() * 1000)
        drive_through_authors.append(row['drive_through_authors'])
        repeat_authors.append(row['repeat_authors'])

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Contributors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.y_range.start = 0
    plot.title.text = f'Drive-through and Repeat Contributor Counts'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/drive-through-and-repeat-contributor-counts.md')

    source = ColumnDataSource(data=dict(
        timestamps=timestamps,
        drive_through=drive_through_authors,
        repeat=repeat_authors
    ))

    plot.vbar_stack(x='timestamps', width=bar_width,
                    stackers=['drive_through', 'repeat'],
                    source=source,
                    color=[Blues[3][0], Oranges[4][1]],
                    legend_label=['Drive-through', 'Repeat'])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            (interval_name, '@timestamps{%F}'),
            ('drive_through', '@drive_through'),
            ('repeat', '@repeat')
        ],
        formatters={
            '@timestamps': 'datetime'
        },
        toggleable=False
    ))

    plot.legend.location = "top_left"
    return json.dumps(json_item(plot))
