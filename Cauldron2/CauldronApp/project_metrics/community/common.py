import json
import logging

import pandas
from datetime import datetime, timedelta

from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, tools, Range1d
from bokeh.palettes import Blues, Greens, Greys, Reds
from bokeh.plotting import figure
from bokeh.transform import dodge

from ..utils import configure_figure

logger = logging.getLogger(__name__)


def authors_entering_leaving_bokeh(elastic, from_date, to_date):
    """Get a visualization of people entering and leaving the project"""
    s = Search(using=elastic, index='git') \
        .query(~Q('match', files=0)) \
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
                           '-/blob/master/guides/metrics/community/onboarding-last-active.md')
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


seconds_in_year = 365 * 24 * 60 * 60

def get_seniority(first_contribution_date, ref_date):
    """Returns the seniority of an author given the date of
    their first contribution and a reference date"""
    if first_contribution_date > ref_date:
        return None

    elapsedTime = ref_date - first_contribution_date
    years = elapsedTime.total_seconds() / seconds_in_year

    return round(years * 2) / 2


def is_still_active(last_contribution_date, ref_date):
    """Check if an author is still active, that is, less
    than 3 months since their last contribution"""
    if last_contribution_date > ref_date:
        return None

    elapsedTime = ref_date - last_contribution_date
    return elapsedTime < timedelta(90)


def authors_aging_bokeh(elastic):
    """Shows how many new people joined the community during
    a corresponding period of time (attracted) and how many
    of these people are still active in the community (retained)"""
    s = Search(using=elastic, index='git') \
        .query(~Q('match', files=0)) \
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
    plot.title.text = 'Authors aging (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/authors-aging.md')

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


def authors_retained_ratio_bokeh(elastic):
    """Shows the ratio between retained and non-retained people
    in a community"""
    s = Search(using=elastic, index='git') \
        .query(~Q('match', files=0)) \
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
    plot.title.text = 'Authors retained ratio (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/authors-retained-ratio.md')

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


def organizational_diversity(elastic, from_date, to_date):
    """Shows the number of git authors who contribute to a project
    grouped by their organization domain"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('domains', 'terms', field='author_domain', size=10, order={'authors': 'desc'}) \
          .metric('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
        domains_buckets = response.aggregations.domains.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        domains_buckets = []

    data = {
        'domain': [],
        'value': []
    }
    for domain in domains_buckets:
        data['domain'].append(domain.key)
        data['value'].append(domain.authors.value)

    # Request for other domains
    domains_ignored = [Q('match_phrase', author_domain=domain) for domain in data['domain']]

    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .filter('exists', field='author_domain') \
        .query(Q('bool', must_not=domains_ignored)) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
        authors_other_domain = response.aggregations.authors.value
    except ElasticsearchException as e:
        logger.warning(e)
        authors_other_domain = 0

    data['domain'].append('other')
    data['value'].append(authors_other_domain)

    plot = figure(x_range=data['domain'],
                  x_axis_label='Domain',
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    plot.title.text = 'Organizational diversity (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/organizational-diversity.md')

    source = ColumnDataSource(data=dict(
        domains=data['domain'],
        authors=data['value']
    ))

    plot.vbar(x='domains', top='authors',
              source=source,
              width=0.3,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('domain', '@domains'),
            ('authors', '@authors')
        ],
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))
