import json
import math
import logging
from datetime import timedelta

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, Range1d, tools
from bokeh.palettes import Category20c, Blues
from bokeh.plotting import figure
from bokeh.transform import cumsum
from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, Q

from CauldronApp.models import Project

from .utils import configure_figure, get_interval

logger = logging.getLogger(__name__)


def issues_time_to_close(elastic, from_date, to_date):
    """ Get median time to close issues (only issues closed in the time range)"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es})\
        .filter('match', state='closed')\
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1))
    s.aggs.bucket('ttc_percentiles', 'percentiles', field='time_to_close_days', percents=[50])

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.aggregations.ttc_percentiles.values['50.0'] is not None:
        return round(response.aggregations.ttc_percentiles.values['50.0'], 2)
    else:
        return 'X'


# This one is not responsive at all... we keep it here in case we find a solution
def author_domains_bokeh(elastic, from_date, to_date):
    """
    Pie chart for domain diversity
    """
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    # request for domains
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es})\
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
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es})\
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


def get_authors_bucket(elastic, from_date, to_date, interval):
    """ Makes a query to ES to get the number of authors grouped by date """
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .extra(size=0)

    s.aggs.bucket('bucket1', 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('bucket2', 'filters',
                  filters={'Maintainers': Q('match', is_git_commit=1),
                           'Contributors': (Q('match', pull_request=True) | Q('match', merge_request=True)),
                           'Users': (Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)),
                           'Observers': Q('match', is_meetup_rsvp=1)
                           },
                  ) \
          .bucket('bucket3', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
        authors_bucket = response.aggregations.bucket1.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        authors_bucket = []

    return authors_bucket


# This code could be useful someday, DON'T REMOVE IT
def author_evolution_bokeh_compare(elastics, from_date, to_date):
    """ Get a projects comparison of evolution of authors """
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    authors_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]
        authors_buckets[project_id] = get_authors_bucket(elastic, from_date_es, to_date_es, interval_elastic)

    data = dict()
    for project_id in authors_buckets:
        authors_bucket = authors_buckets[project_id]

        # Create the data structure
        contributors, maintainers, observers, users, timestamps = [], [], [], [], []
        for item in authors_bucket:
            timestamps.append(item.key)
            values = item.bucket2.buckets
            contributors.append(values.Contributors.bucket3.value)
            maintainers.append(values.Maintainers.bucket3.value)
            observers.append(values.Observers.bucket3.value)
            users.append(values.Users.bucket3.value)

        data[f'contributors_{project_id}'] = contributors
        data[f'maintainers_{project_id}'] = maintainers
        data[f'observers_{project_id}'] = observers
        data[f'users_{project_id}'] = users
        data[f'timestamps_{project_id}'] = timestamps

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Authors per category over time'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/overview/authors-evolution.md')
    if any(data.values()):
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=data)

    names = []
    tooltips = []
    formatters = dict()
    for idx, project_id in enumerate(authors_buckets):
        try:
            project = Project.objects.get(pk=project_id)
            project_name = project.name
        except Project.DoesNotExist:
            project_name = "Unknown"

        if idx == 0:
            names.append(f'maintainers_{project_id}')
            tooltips.append((interval_name, f'@timestamps_{project_id}{{%F}}'))
            formatters[f'@timestamps_{project_id}'] = 'datetime'

        for i, category in enumerate(('contributors', 'maintainers', 'observers', 'users')):
            tooltips.append((f'{category} {project_name}', f'@{category}_{project_id}'))
            plot.line(x=f'timestamps_{project_id}', y=f'{category}_{project_id}',
                      name=f'{category}_{project_id}',
                      line_width=4,
                      line_color=Category20c[20][4 * idx + i],
                      legend_label=f'{category} {project_name}',
                      source=source)

    plot.add_tools(tools.HoverTool(
        names=names,
        tooltips=tooltips,
        formatters=formatters,
        mode='vline',
        toggleable=False
    ))

    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def author_evolution_bokeh(elastic, from_date, to_date):
    """Get evolution of Authors"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    authors_buckets = get_authors_bucket(elastic, from_date_es, to_date_es, interval_elastic)

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
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Authors per category over time'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/overview/authors-evolution.md')
    if len(x) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        x=x,
        contrib=contrib,
        maintainers=maintainers,
        observers=observers,
        users=users
    ))

    plot.circle(x='x', y='contrib',
                color=Blues[6][0],
                size=8,
                source=source)

    plot.line(x='x', y='contrib',
              line_width=4,
              line_color=Blues[6][0],
              legend_label='contributors',
              source=source)

    plot.circle(x='x', y='maintainers',
                name='maintainers',
                color=Blues[6][1],
                size=8,
                source=source)

    plot.line(x='x', y='maintainers',
              line_width=4,
              line_color=Blues[6][1],
              legend_label='maintainers',
              source=source)

    plot.circle(x='x', y='observers',
                color=Blues[6][2],
                size=8,
                source=source)

    plot.line(x='x', y='observers',
              line_width=4,
              line_color=Blues[6][2],
              legend_label='observers',
              source=source)

    plot.circle(x='x', y='users',
                color=Blues[6][3],
                size=8,
                source=source)

    plot.line(x='x', y='users',
              line_width=4,
              line_color=Blues[6][3],
              legend_label='users',
              source=source)

    plot.add_tools(tools.HoverTool(
        names=['maintainers'],
        tooltips=[
            (interval_name, '@x{%F}'),
            ('contributors', '@contrib'),
            ('maintainers', '@maintainers'),
            ('observers', '@observers'),
            ('users', '@users')
        ],
        formatters={
            '@x': 'datetime'
        },
        mode='vline',
        toggleable=False
    ))

    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def review_duration(elastic, from_date, to_date):
    """
    Median time to merge a PR or MR
    """
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query((Q('match', pull_request=True) & Q('match', state='closed')) |
               (Q('match', merge_request=True) & Q('match', state='merged')))
    s.aggs.bucket('ttc_percentiles', 'percentiles', field='time_to_close_days', percents=[50])

    try:
        response = s.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    if response is not None and response.aggregations.ttc_percentiles.values['50.0'] is not None:
        return round(response.aggregations.ttc_percentiles.values['50.0'], 2)
    else:
        return 'X'
