import ssl
import json

from elasticsearch_dsl import Search, Q
from elasticsearch.connection import create_ssl_context
from elasticsearch import exceptions as elastic_exceptions
from elasticsearch import Elasticsearch

from bokeh.plotting import figure, ColumnDataSource
from bokeh.embed import json_item

from CauldronApp import utils
from Cauldron2 import settings


def bokeh_vbar_figure(x, y, **kwargs):
    plot = figure(sizing_mode="stretch_both", height=250, **kwargs)
    plot.vbar(x=x, width=0.5, bottom=0, top=y)
    return json.dumps(json_item(plot))


def get_metrics(dashboard):
    """
    Fetch from Elastic Search the dashboard metrics
    :param dashboard:
    :return:
    """
    jwt_key = utils.get_jwt_key(f"Project {dashboard.id}", dashboard.projectrole.backend_role)

    context = create_ssl_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    elastic = Elasticsearch(hosts=[settings.ES_IN_HOST], scheme=settings.ES_IN_PROTO, port=settings.ES_IN_PORT,
                            headers={"Authorization": f"Bearer {jwt_key}"}, ssl_context=context, timeout=5)

    metrics = {}

    if dashboard.repository_set.filter(backend='git').count() > 0:
        metrics['git'] = git_metrics(elastic)
    else:
        metrics['git'] = None

    if dashboard.repository_set.filter(backend='github').count() > 0:
        metrics['github'] = github_metrics(elastic)
    else:
        metrics['github'] = None

    if dashboard.repository_set.filter(backend='gitlab').count() > 0:
        metrics['gitlab'] = gitlab_metrics(elastic)
    else:
        metrics['gitlab'] = None

    if dashboard.repository_set.filter(backend='meetup').count() > 0:
        metrics['meetup'] = meetup_metrics(elastic)
    else:
        metrics['meetup'] = None

    if dashboard.repository_set.count() > 0:
        metrics['authors'] = author_metrics(elastic)
    else:
        metrics['authors'] = None

    return metrics


def git_metrics(elastic):
    """
    Get metrics related to git.
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['commits'] = Search(using=elastic, index="git").count()
    except elastic_exceptions.AuthorizationException:
        metrics['commits'] = 'unauthorized'
    except elastic_exceptions.ConnectionTimeout:
        metrics['commits'] = 'timeout'

    try:
        s = Search(using=elastic, index='git').filter('range', grimoire_creation_date={'gte': "now-1y/d"}).extra(size=0)
        s.aggs.bucket("commits_per_day", 'date_histogram', field='grimoire_creation_date', calendar_interval='1d')
        response = s.execute()
        response_unpacked = response.aggregations['commits_per_day']['buckets']
        x = [week.key for week in response_unpacked]
        y = [week.doc_count for week in response_unpacked]
        metrics['commits_graph'] = bokeh_vbar_figure(x, y,
                                                     title="# Commits last year",
                                                     x_axis_type="datetime")
    except elastic_exceptions.AuthorizationException:
        metrics['commits_graph'] = 'unauthorized'
    except elastic_exceptions.ConnectionTimeout:
        metrics['commits_graph'] = 'timeout'

    return metrics


def github_metrics(elastic):
    """
    Get metrics related to GitHub.
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['issues'] = Search(using=elastic, index="github").filter("term", pull_request=False).count()
    except elastic_exceptions.AuthorizationException:
        metrics['issues'] = 'unauthorized'
    except elastic_exceptions.ConnectionTimeout:
        metrics['issues'] = 'timeout'

    try:
        metrics['prs'] = Search(using=elastic, index="github").filter("term", pull_request=True).count()
    except elastic_exceptions.AuthorizationException:
        metrics['prs'] = 'unauthorized'
    except elastic_exceptions.ConnectionTimeout:
        metrics['prs'] = 'timeout'

    return metrics


def gitlab_metrics(elastic):
    """
    Get metrics related to Gitlab
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['issues'] = Search(using=elastic, index="gitlab_issues").count()
    except elastic_exceptions.AuthorizationException:
        metrics['issues'] = 'unauthorized'
    except elastic_exceptions.ConnectionTimeout:
        metrics['issues'] = 'timeout'

    try:
        metrics['mrs'] = Search(using=elastic, index="gitlab_mrs").count()
    except elastic_exceptions.AuthorizationException:
        metrics['mrs'] = 'unauthorized'
    except elastic_exceptions.ConnectionTimeout:
        metrics['mrs'] = 'timeout'

    return metrics


def meetup_metrics(elastic):
    """
    Get metrics related to Meetup
    The elastic connection should contain the authorization header
    """
    metrics = {}
    try:
        metrics['events'] = Search(using=elastic, index="meetup").count()
    except elastic_exceptions.AuthorizationException:
        metrics['events'] = 'unauthorized'
    except elastic_exceptions.ConnectionTimeout:
        metrics['events'] = 'timeout'

    return metrics


def author_metrics(elastic):
    """
    Get metrics related to Authors
    The elastic connection should contain the authorization header
    """
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': "now-1y/d"}).extra(size=0)
    s.aggs.bucket('bucket1', 'date_histogram', field='grimoire_creation_date', calendar_interval='1w')\
          .bucket('bucket2', 'filters',
                  filters={'Maintainers': Q('bool', must=[Q('query_string', query="is_git_commit:1")]),
                           'Contributors': Q('bool', must=[Q('query_string', query="pull_request:true")]),
                           'Users': Q('bool', must=[Q('query_string', query="pull_request:false")]),
                           'Observers': Q('bool', must=[Q('query_string', query="is_meetup_rsvp:1")])
                           },
                  )\
          .bucket('bucket3', 'cardinality', field='author_uuid')
    try:
        response = s.execute()
    except elastic_exceptions.AuthorizationException:
        response = None
    except elastic_exceptions.ConnectionTimeout:
        response = None

    if response is not None and response.success():
        x, contrib, maintainers, observers, users = [], [], [], [], []
        for item in response.aggregations.bucket1.buckets:
            x.append(item.key)
            values = item.bucket2.buckets
            contrib.append(values.Contributors.bucket3.value)
            maintainers.append(values.Maintainers.bucket3.value)
            observers.append(values.Observers.bucket3.value)
            users.append(values.Users.bucket3.value)

        plot = figure(sizing_mode="stretch_both",
                      height=250,
                      title="# Authors last year",
                      x_axis_type="datetime")
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
    else:
        return None
