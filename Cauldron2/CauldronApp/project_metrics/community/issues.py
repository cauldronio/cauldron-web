import logging
import json

import pandas
from datetime import datetime, timedelta

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues, Greens, Greys, Reds
from bokeh.plotting import figure
from bokeh.transform import dodge

from .common import get_seniority, is_still_active
from ..utils import configure_figure, get_interval

logger = logging.getLogger(__name__)


def active_submitters(elastic, from_date, to_date):
    """Get number of issue authors for a project in a period of time"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)
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


def authors_active_bokeh(elastic, from_date, to_date):
    """Get evolution of Authors in issues"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, bar_width = get_interval(from_date, to_date)
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)

    s.aggs.bucket("bucket1", 'date_histogram', field='grimoire_creation_date', calendar_interval=interval_elastic)\
        .bucket('authors', 'cardinality', field='author_uuid')
    try:
        response = s.execute()
        authors_buckets = response.aggregations.bucket1.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_buckets = []

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
                           '-/blob/master/guides/metrics/community/authors-issues.md')
    plot.title.text = 'Active submitters (Issues)'
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


def authors_entering(elastic, from_date, to_date):
    """Get number of issue authors entering in a project for a period of time"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'terms', field='author_uuid', size=30000) \
          .metric('first_issue', 'min', field='grimoire_creation_date')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        authors = {}
        for author in response.aggregations.authors.buckets:
            authors[author.key] = author.first_issue.value / 1000

        authors_df = pandas.DataFrame(authors.items(), columns=['author_id', 'first_issue'])

        from_date_ts = datetime.timestamp(from_date)
        to_date_ts = datetime.timestamp(to_date)

        return len(authors_df[authors_df["first_issue"].between(from_date_ts, to_date_ts)].index)
    else:
        return 'X'


def authors_entering_leaving_bokeh(elastic, from_date, to_date):
    """Get a visualization of issue submitters entering and leaving
    the project"""
    s = Search(using=elastic, index='all') \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
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
    plot.title.text = 'Submitters onboarding / last active (Issues)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/onboarding-last-active-issues.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date, to_date)

    source = ColumnDataSource(data=dict(
        onboardings=authors_entering,
        leavings=authors_leaving,
        difference=difference,
        timestamps=timestamps
    ))

    plot.varea('timestamps', 'onboardings',
               source=source,
               color=Blues[3][0],
               legend_label='Onboarding')
    plot.varea('timestamps', 'leavings',
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


def authors_aging_bokeh(elastic, snap_date):
    """Shows how many new issue submitters joined the community during
    a corresponding period of time (attracted) and how many
    of these people are still active in the community (retained)"""
    snap_date_es = snap_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={"lte": snap_date_es}) \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
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
    authors['seniority'] = authors['first_contribution'].apply(lambda x: get_seniority(x, datetime.now()))
    authors['still_active'] = authors['last_contribution'].apply(lambda x: is_still_active(x, datetime.now()))

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
    plot.title.text = 'Submitters aging (Issues)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/aging-issues.md')

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


def authors_retained_ratio_bokeh(elastic, snap_date):
    """Shows the ratio between retained and non-retained
    issue submitters in a community"""
    snap_date_es = snap_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={"lte": snap_date_es}) \
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
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
    authors['seniority'] = authors['first_contribution'].apply(lambda x: get_seniority(x, datetime.now()))
    authors['still_active'] = authors['last_contribution'].apply(lambda x: is_still_active(x, datetime.now()))

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
    plot.title.text = 'Submitters retained ratio (Issues)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/retained-ratio-issues.md')

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
