import json
import math
import logging

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource
from bokeh.palettes import Category20c
from bokeh.plotting import figure
from bokeh.transform import cumsum
from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

logger = logging.getLogger(__name__)


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