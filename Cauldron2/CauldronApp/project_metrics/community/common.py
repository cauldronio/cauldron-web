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


def organizational_diversity_authors(elastic, from_date, to_date):
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

    # Flip the list
    data['domain'].reverse()
    data['value'].reverse()

    plot = figure(y_range=data['domain'],
                  y_axis_label='Domain',
                  x_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    plot.title.text = 'Organizational diversity (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/organizational-diversity-authors.md',
                     vertical=False)

    source = ColumnDataSource(data=dict(
        domains=data['domain'],
        authors=data['value']
    ))

    plot.hbar(y='domains', right='authors',
              source=source,
              width=10,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('domain', '@domains'),
            ('authors', '@authors')
        ],
        mode='hline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def organizational_diversity_commits(elastic, from_date, to_date):
    """Shows the number of git commits of a project
    grouped by the organization domain of their authors"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('domains', 'terms', field='author_domain', size=10, order={'commits': 'desc'}) \
          .metric('commits', 'cardinality', field='hash')

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
        data['value'].append(domain.commits.value)

    # Request for other domains
    domains_ignored = [Q('match_phrase', author_domain=domain) for domain in data['domain']]

    s = Search(using=elastic, index='git') \
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .filter('exists', field='author_domain') \
        .query(Q('bool', must_not=domains_ignored)) \
        .query(~Q('match', files=0)) \
        .extra(size=0)
    s.aggs.bucket('commits', 'cardinality', field='hash')

    try:
        response = s.execute()
        commits_other_domain = response.aggregations.commits.value
    except ElasticsearchException as e:
        logger.warning(e)
        commits_other_domain = 0

    data['domain'].append('other')
    data['value'].append(commits_other_domain)

    # Flip the list
    data['domain'].reverse()
    data['value'].reverse()

    plot = figure(y_range=data['domain'],
                  y_axis_label='Domain',
                  x_axis_label='# Commits',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')

    plot.title.text = 'Organizational diversity (Git)'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/community/organizational-diversity-commits.md',
                     vertical=False)

    source = ColumnDataSource(data=dict(
        domains=data['domain'],
        commits=data['value']
    ))

    plot.hbar(y='domains', right='commits',
              source=source,
              width=10,
              color=Blues[3][0])

    plot.add_tools(tools.HoverTool(
        tooltips=[
            ('domain', '@domains'),
            ('commits', '@commits')
        ],
        mode='hline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))
