import math
import ssl
import json
import logging

from bokeh.palettes import Category20c
from elasticsearch_dsl import Search, Q
from elasticsearch.connection import create_ssl_context
from elasticsearch.exceptions import ElasticsearchException
from elasticsearch import Elasticsearch

from bokeh.plotting import figure, ColumnDataSource
from bokeh.embed import json_item
from bokeh.models.tools import HoverTool
from bokeh.transform import cumsum

from CauldronApp import utils
from Cauldron2 import settings

logger = logging.getLogger(__name__)


""" How to create new metrics

Open CauldronApp/project_metrics.py
    - Create a new function with the following parameters: elastic, from_date, to_date. 
      The output should be a number or a JSON in case of a Bokeh function: 
      https://docs.bokeh.org/en/latest/docs/user_guide/embed.html#json-items
    - Add the output of the function to the dictionary returned by 'get_metrics'
Open CauldronApp/templates/cauldronapp/project_metrics.html
    - Define in the HTML the metric, it will have the name 'metric.<name defined in get_metrics>'. 
      If it is a Bokeh visualization, you will need to create a script to initialize the graph.
Open CauldronApp/static/js/dashbord.js
    - Include your metric in the function `updateMetricsData`. It is called when the user
      updates the date picker range.
"""


def get_metrics(dashboard, from_date='now-1y', to_date='now'):
    jwt_key = utils.get_jwt_key(f"Project {dashboard.id}", dashboard.projectrole.backend_role)

    context = create_ssl_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    elastic = Elasticsearch(hosts=[settings.ES_IN_HOST], scheme=settings.ES_IN_PROTO, port=settings.ES_IN_PORT,
                            headers={"Authorization": f"Bearer {jwt_key}"}, ssl_context=context, timeout=5)

    metrics = {'commits': git_commits(elastic, from_date, to_date),
               'reviews': submitted_reviews(elastic, from_date, to_date),
               'avg_review': review_duration(elastic, from_date, to_date),
               'open_issues': issues_open(elastic, from_date, to_date),
               'closed_issues': issues_closed(elastic, from_date, to_date),
               'issue_avg_close': issues_time_to_close(elastic, from_date, to_date),
               'issue_evolution_bokeh': issue_status_evolution_bokeh(elastic, from_date, to_date),
               'commits_evolution_bokeh': commits_evolution_bokeh(elastic, from_date, to_date),
               'prs_mrs_evolution_bokeh': prs_mrs_evolution_bokeh(elastic, from_date, to_date),
               'author_evolution_bokeh': author_evolution_bokeh(elastic, from_date, to_date)}

    return metrics


"""
CHAOSS METRICS
"""


def git_commits(elastic, from_date='now-1y', to_date='now'):
    """
    Get number of commits for a project
    """
    s = Search(using=elastic, index='git')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date})\
        .extra(size=0)
    s.aggs.bucket('commits', 'cardinality', field='hash')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.success():
        return response.aggregations.commits.value
    else:
        return 0


def submitted_reviews(elastic, from_date='now-1y', to_date='now'):
    """
    Get number of reviews (PRs and MRs) for a project
    """
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True))

    try:
        response = s.count()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None:
        return response
    else:
        return 0


def review_duration(elastic, from_date='now-1y', to_date='now'):
    """
    Average time to merge a PR or MR
    """
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .query((Q('match', pull_request=True) & Q('match', state='closed')) |
               (Q('match', merge_request=True) & Q('match', state='merged')))
    s.aggs.bucket('avg_merge', 'avg', field='time_to_close_days')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.aggregations.avg_merge.value is not None:
        return round(response.aggregations.avg_merge.value, 2)
    else:
        return 0


def issues_open(elastic, from_date='now-1y', to_date='now'):
    """
    Get number of open issues in GitHub and GitLab
    """
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
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


def issues_closed(elastic, from_date='now-1y', to_date='now'):
    """
    Get number of closed issues in GitHub and GitLab
    """
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date, "lte": to_date})\
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


def issues_time_to_close(elastic, from_date='now-1y', to_date='now'):
    """
     Get average time to close issues (only issues closed in the time range)
    """
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date, "lte": to_date})\
        .filter('match', state='closed')\
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))
    s.aggs.bucket('avg_merge', 'avg', field='time_to_close_days')

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.aggregations.avg_merge.value is not None:
        return round(response.aggregations.avg_merge.value, 2)
    else:
        return 0


# This one is not responsive at all... we keep it here in case we find a solution
def author_domains_bokeh(elastic, from_date='now-1y', to_date='now'):
    """
    Pie chart for domain diversity
    """
    # request for domains
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date})\
        .extra(size=0)

    s.aggs.bucket('bdomains', 'terms', field='author_domain', order={'authors': 'desc'})\
        .bucket('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
        domains = response.aggregations.bdomains.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        domains = []

    data = {
        'domain': [],
        'value': [],
        'angle': [],
        'color': []
    }
    for item in domains:
        data['domain'].append(item.key)
        data['value'].append(item.authors.value)

    # request for other domains
    ignore_domains = [Q('match_phrase', author_domain=domain) for domain in data['domain']]
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date})\
        .filter('exists', field='author_domain')\
        .query(Q('bool', must_not=ignore_domains))\
        .extra(size=0)

    s.aggs.bucket('authors', 'cardinality', field='author_uuid')

    try:
        response2 = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)

    data['domain'].append('other')
    data['value'].append(response2.aggregations.authors.value)

    # Create the Bokeh visualization
    data['angle'] = [n/sum(data['value'])*2*math.pi for n in data['value']]
    data['color'] = Category20c[len(data['domain'])]

    plot = figure(plot_height=300,
                  plot_width=380,
                  tools='save,reset,hover',
                  tooltips="@domain: @value")
    source = ColumnDataSource(data=data)

    plot.wedge(x=0, y=0, radius=0.8,
               start_angle=cumsum('angle', include_zero=True),
               end_angle=cumsum('angle'),
               line_color="white",
               fill_color='color',
               #legend_field='domain',
               source=source)

    #plot.axis.axis_label = None
    #plot.axis.visible = False
    #plot.grid.grid_line_color = None

    return json.dumps(json_item(plot))


# EVOLUTION METRICS


def author_evolution_bokeh(elastic, from_date='now-1y', to_date='now'):
    """
    Get evolution of Authors
    """
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date})\
        .extra(size=0)

    s.aggs.bucket('bucket1', 'date_histogram', field='grimoire_creation_date', calendar_interval='1w')\
          .bucket('bucket2', 'filters',
                  filters={'Maintainers': Q('match', is_git_commit=1),
                           'Contributors': (Q('match', pull_request=True) | Q('match', merge_request=True)),
                           'Users': (Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)),
                           'Observers': Q('match', is_meetup_rsvp=1)
                           },
                  )\
          .bucket('bucket3', 'cardinality', field='author_uuid')
    try:
        response = s.execute()
        authors_buckets = response.aggregations.bucket1.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_buckets = []

    # Create the Bokeh visualization
    x, contrib, maintainers, observers, users = [], [], [], [], []
    for item in authors_buckets:
        x.append(item.key)
        values = item.bucket2.buckets
        contrib.append(values.Contributors.bucket3.value)
        maintainers.append(values.Maintainers.bucket3.value)
        observers.append(values.Observers.bucket3.value)
        users.append(values.Users.bucket3.value)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='pan,wheel_zoom,save,reset')
    source = ColumnDataSource(data=dict(
        x=x,
        contrib=contrib,
        maintainers=maintainers,
        observers=observers,
        users=users
    ))
    names = ['contributors', 'maintainers', 'observers', 'users']
    colors = ['navy', 'royalblue', 'deepskyblue', 'lightsteelblue']
    plot.varea_stack(['contrib', 'maintainers', 'observers', 'users'],
                     x='x',
                     source=source,
                     color=colors,
                     legend_label=names)
    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def issue_status_evolution_bokeh(elastic, from_date='now-1y', to_date='now'):
    """
    Get evolution of issues status. Open vs closed.
    """
    s = Search(using=elastic, index='all') \
        .query('bool', filter=(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)))\
        .extra(size=0)

    s.aggs.bucket('range_open', 'filter', Q('range', created_at={'gte': from_date, "lte": to_date}))\
        .bucket('open', 'date_histogram', field='created_at', calendar_interval='1w')\
        .bucket('cum_sum_open', 'cumulative_sum', buckets_path="_count")

    s.aggs.bucket('range_closed', 'filter', Q('range', closed_at={'gte': from_date, "lte": to_date}))\
        .bucket('closed', 'date_histogram', field='closed_at', calendar_interval='1w') \
        .bucket('cum_sum_closed', 'cumulative_sum', buckets_path="_count")

    try:
        response = s.execute()
        closed_buckets = response.aggregations.range_closed.closed.buckets
        open_buckets = response.aggregations.range_open.open.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        closed_buckets = []
        open_buckets = []

    # Create the Bokeh visualization
    c_timestamp, closed_issues, o_timestamp, open_issues, distance = [], [], [], [], []
    for citem, oitem in zip(closed_buckets, open_buckets):
        c_timestamp.append(citem.key)
        o_timestamp.append(oitem.key)
        closed_issues.append(citem.cum_sum_closed.value)
        open_issues.append(oitem.cum_sum_open.value)
        distance.append(oitem.cum_sum_open.value - citem.cum_sum_closed.value)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='Issues',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='pan,wheel_zoom,save,reset')

    source = ColumnDataSource(data=dict(
        o_timestamp=o_timestamp,
        c_timestamp=c_timestamp,
        open_issues=open_issues,
        closed_issues=closed_issues,
        distance=distance
    ))

    plot.line(x='c_timestamp', y='closed_issues',
              line_width=4,
              line_color='firebrick',
              legend_label='closed issues',
              source=source)
    plot.line(x='o_timestamp', y='open_issues',
              name='open_issues',
              line_width=4,
              line_color='navy',
              legend_label='created issues',
              source=source)

    plot.legend.location = "top_left"

    plot.add_tools(HoverTool(
        names=['open_issues'],
        tooltips=[
            ('date', '@o_timestamp{%F}'),
            ('created issues', '@open_issues'),
            ('closed issues', '@closed_issues'),
            ('distance', '@distance')
        ],
        formatters={
            '@o_timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def commits_evolution_bokeh(elastic, from_date='now-1y', to_date='now'):
    """
     Get evolution of contributions by commits
    """
    s = Search(using=elastic, index='git')\
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date})\
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
                  x_axis_label='Time',
                  y_axis_label='Commits',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='pan,wheel_zoom,save,reset')

    source = ColumnDataSource(data=dict(
        commits=commits,
        timestamp=timestamp
    ))

    # width = 1000 ms/s * 60 s/m * 60 m/h * 24 h/d * 7 d/w * 0.9 width
    plot.vbar(x='timestamp', top='commits',
              source=source,
              width=544320000)

    plot.add_tools(HoverTool(
        tooltips=[
            ('date', '@timestamp{%F}'),
            ('commits', '@commits')
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    return json.dumps(json_item(plot))


def prs_mrs_evolution_bokeh(elastic, from_date='now-1y', to_date='now'):
    """
    Get evolution of pull requests by status
    """
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .query(Q('match', pull_request=True) | Q('match', merge_request=True))\
        .extra(size=0)

    s.aggs.bucket("per_week", 'date_histogram', field='grimoire_creation_date', calendar_interval='1w')\
        .bucket('filtered', 'filters',
                filters={
                    'closed': (Q('match', state='closed') | Q('match', state='merged')),
                    'open': Q('match', state='open')
                })

    try:
        response = s.execute()
        reviews_bucket = response.aggregations.per_week.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        reviews_bucket = []

    # Create the Bokeh visualization
    timestamp, open_reviews, closed_reviews = [], [], []
    for week in reviews_bucket:
        timestamp.append(week.key)
        open_reviews.append(week.filtered.buckets.open.doc_count)
        closed_reviews.append(week.filtered.buckets.closed.doc_count)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='PRs/MRs',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='pan,wheel_zoom,save,reset')

    source = ColumnDataSource(data=dict(
        open=open_reviews,
        closed=closed_reviews,
        timestamp=timestamp
    ))

    # width = 1000 ms/s * 60 s/m * 60 m/h * 24 h/d * 7 d/w * 0.9
    plot.vbar_stack(x='timestamp',
                    stackers=['open', 'closed'],
                    source=source,
                    width=544320000,
                    color=['navy', 'royalblue'],
                    legend_label=['open', 'closed'])

    plot.add_tools(HoverTool(
        tooltips=[
            ('date', '@timestamp{%F}'),
            ('open', '@open'),
            ('closed', '@closed'),
        ],
        formatters={
            '@timestamp': 'datetime'
        },
        toggleable=False
    ))

    return json.dumps(json_item(plot))


"""
Should these metrics be removed?
"""


def git_metrics(elastic):
    """
    Get metrics related to git.
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['commits'] = Search(using=elastic, index="git").count()
    except ElasticsearchException:
        metrics['commits'] = 'error'

    return metrics


def github_metrics(elastic):
    """
    Get metrics related to GitHub.
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['issues'] = Search(using=elastic, index="github").filter("term", pull_request=False).count()
    except ElasticsearchException:
        metrics['issues'] = 'error'

    try:
        metrics['prs'] = Search(using=elastic, index="github").filter("term", pull_request=True).count()
    except ElasticsearchException:
        metrics['prs'] = 'error'

    return metrics


def gitlab_metrics(elastic):
    """
    Get metrics related to Gitlab
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['issues'] = Search(using=elastic, index="gitlab_issues").count()
    except ElasticsearchException:
        metrics['issues'] = 'error'

    try:
        metrics['mrs'] = Search(using=elastic, index="gitlab_mrs").count()
    except ElasticsearchException:
        metrics['mrs'] = 'error'

    return metrics


def meetup_metrics(elastic):
    """
    Get metrics related to Meetup
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['events'] = Search(using=elastic, index="meetup").count()
    except ElasticsearchException:
        metrics['events'] = 'error'

    return metrics
