import datetime
import json
import math
import logging
import operator
from datetime import timedelta

from bokeh.embed import json_item
from bokeh.models import ColumnDataSource, Range1d, tools
from bokeh.palettes import Category20c, Blues
from bokeh.plotting import figure
from bokeh.transform import cumsum
from elasticsearch import ElasticsearchException
from elasticsearch_dsl import Search, MultiSearch, Q

from CauldronApp.models import Project

from .utils import configure_figure, get_interval

logger = logging.getLogger(__name__)


def issues_time_to_close(elastic, urls, from_date, to_date):
    """ Get median time to close issues (only issues closed in the time range)"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', closed_at={'gte': from_date_es, "lte": to_date_es})\
        .filter('match', state='closed')\
        .query(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
        .query(Q('terms', origin=urls))
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


def get_authors_bucket(elastic, urls, from_date, to_date, interval):
    """ Makes a query to ES to get the number of authors grouped by date """
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .query(Q('terms', origin=urls)) \
        .extra(size=0)

    s.aggs.bucket('dates', 'date_histogram', field='grimoire_creation_date', calendar_interval=interval) \
          .bucket('categories', 'filters',
                  filters={'commit_authors': Q('match', is_git_commit=1),
                           'issue_submitters': (Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)),
                           'review_submitters': (Q('match', pull_request=True) | Q('match', merge_request=True)),
                           'meetup_users': Q('match', is_meetup_rsvp=1)
                           },
                  ) \
          .bucket('authors', 'cardinality', field='author_uuid')

    try:
        response = s.execute()
        buckets = response.aggregations.dates.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        buckets = []

    return buckets


# This code could be useful someday, DON'T REMOVE IT
def author_evolution_bokeh_compare(elastics, urls, from_date, to_date):
    """ Get a projects comparison of evolution of authors """
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    authors_buckets = dict()
    for project_id in elastics:
        elastic = elastics[project_id]
        authors_buckets[project_id] = get_authors_bucket(elastic, urls, from_date_es, to_date_es, interval_elastic)

    data = dict()
    for project_id in authors_buckets:
        authors_bucket = authors_buckets[project_id]

        # Create the data structure
        timestamps, commit_authors, issue_submitters, review_submitters, meetup_users = [], [], [], [], []
        for item in authors_bucket:
            timestamps.append(item.key)
            categories = item.categories.buckets
            commit_authors.append(categories.commit_authors.authors.value)
            issue_submitters.append(categories.issue_submitters.authors.value)
            review_submitters.append(categories.review_submitters.authors.value)
            meetup_users.append(categories.meetup_users.authors.value)

        data[f'timestamps_{project_id}'] = timestamps
        data[f'commit_authors_{project_id}'] = commit_authors
        data[f'issue_submitters_{project_id}'] = issue_submitters
        data[f'review_submitters_{project_id}'] = review_submitters
        data[f'meetup_users_{project_id}'] = meetup_users

    # Create the Bokeh visualization
    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Authors'
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
            names.append(f'commit_authors_{project_id}')
            tooltips.append((interval_name, f'@timestamps_{project_id}{{%F}}'))
            formatters[f'@timestamps_{project_id}'] = 'datetime'

        for i, category in enumerate(('commit_authors', 'issue_submitters', 'review_submitters', 'meetup_users')):
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


def author_evolution_bokeh(elastic, urls, from_date, to_date):
    """Get evolution of Authors"""
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    interval_name, interval_elastic, _ = get_interval(from_date, to_date)

    authors_buckets = get_authors_bucket(elastic, urls, from_date_es, to_date_es, interval_elastic)

    # Create the Bokeh visualization
    timestamps, commit_authors, issue_submitters, review_submitters, meetup_users = [], [], [], [], []
    for item in authors_buckets:
        timestamps.append(item.key)
        categories = item.categories.buckets
        commit_authors.append(categories.commit_authors.authors.value)
        issue_submitters.append(categories.issue_submitters.authors.value)
        review_submitters.append(categories.review_submitters.authors.value)
        meetup_users.append(categories.meetup_users.authors.value)

    plot = figure(x_axis_type="datetime",
                  x_axis_label='Time',
                  y_axis_label='# Authors',
                  height=300,
                  sizing_mode="stretch_width",
                  tools='')
    plot.title.text = '# Authors'
    configure_figure(plot, 'https://gitlab.com/cauldronio/cauldron/'
                           '-/blob/master/guides/metrics/overview/authors-evolution.md')
    if len(timestamps) > 0:
        plot.x_range = Range1d(from_date - timedelta(days=1), to_date + timedelta(days=1))

    source = ColumnDataSource(data=dict(
        timestamps=timestamps,
        commit_authors=commit_authors,
        issue_submitters=issue_submitters,
        review_submitters=review_submitters,
        meetup_users=meetup_users
    ))

    names = []
    tooltips=[
        (interval_name, '@timestamps{%F}'),
    ]

    if any(commit_authors):
        plot.circle(x='timestamps', y='commit_authors',
                    name='commit_authors',
                    color=Blues[6][0],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y='commit_authors',
                  line_width=4,
                  line_color=Blues[6][0],
                  legend_label='Authors',
                  source=source)

        names.append('commit_authors')
        tooltips.append(('commit_authors', '@commit_authors'))

    if any(issue_submitters):
        plot.circle(x='timestamps', y='issue_submitters',
                    name='issue_submitters',
                    color=Blues[6][1],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y='issue_submitters',
                  line_width=4,
                  line_color=Blues[6][1],
                  legend_label='Submitters (Issues)',
                  source=source)

        names.append('issue_submitters')
        tooltips.append(('issue_submitters', '@issue_submitters'))

    if any(review_submitters):
        plot.circle(x='timestamps', y='review_submitters',
                    name='review_submitters',
                    color=Blues[6][2],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y='review_submitters',
                  line_width=4,
                  line_color=Blues[6][2],
                  legend_label='Submitters (Reviews)',
                  source=source)

        names.append('review_submitters')
        tooltips.append(('review_submitters', '@review_submitters'))

    if any(meetup_users):
        plot.circle(x='timestamps', y='meetup_users',
                    name='meetup_users',
                    color=Blues[6][3],
                    size=8,
                    source=source)

        plot.line(x='timestamps', y='meetup_users',
                  line_width=4,
                  line_color=Blues[6][3],
                  legend_label='Attendees (Meetup)',
                  source=source)

        names.append('meetup_users')
        tooltips.append(('meetup_attendees', '@meetup_users'))

    plot.add_tools(tools.HoverTool(
        names=names,
        tooltips=tooltips,
        formatters={
            '@timestamps': 'datetime'
        },
        mode='mouse',
        toggleable=False
    ))

    plot.legend.location = "top_left"

    return json.dumps(json_item(plot))


def review_duration(elastic, urls, from_date, to_date):
    """
    Median time to merge a PR or MR
    """
    from_date_es = from_date.strftime("%Y-%m-%d")
    to_date_es = to_date.strftime("%Y-%m-%d")
    s = Search(using=elastic, index='all')\
        .filter('range', grimoire_creation_date={'gte': from_date_es, "lte": to_date_es}) \
        .query(Q('terms', origin=urls)) \
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


def report_total_metrics(elastic, categories):
    metrics = {
        'items': {},
        'authors': {}
    }
    response_keys = []
    ms = MultiSearch(using=elastic)

    if 'commits' in categories:
        # Items
        s = Search(index='git') \
            .filter(~Q('match', files=0)) \
            .extra(size=0)
        s.aggs.bucket('commits', 'cardinality', field='hash')
        s.aggs.bucket('authors', 'cardinality', field='author_uuid')
        ms = ms.add(s)
        response_keys.append({'name': 'commits',
                              'results': {'items': 'aggregations.commits.value',
                                          'authors': 'aggregations.authors.value'}})

    if 'issues' in categories:
        s = Search(index='all') \
            .filter(Q('match', pull_request=False) | Q('match', is_gitlab_issue=1)) \
            .extra(size=0)
        s.aggs.bucket('authors', 'cardinality', field='author_uuid')
        ms = ms.add(s)
        response_keys.append({'name': 'issues',
                              'results': {'items': 'hits.total.value',
                                          'authors': 'aggregations.authors.value'}})

    if 'reviews' in categories:
        s = Search(index='all') \
            .filter(Q('match', pull_request=True) | Q('match', merge_request=True)) \
            .extra(size=0)
        s.aggs.bucket('authors', 'cardinality', field='author_uuid')
        ms = ms.add(s)
        response_keys.append({'name': 'reviews',
                              'results': {'items': 'hits.total.value',
                                          'authors': 'aggregations.authors.value'}})

    if 'questions' in categories:
        s = Search(index='stackexchange') \
            .filter(Q('match', is_stackexchange_question='1')) \
            .extra(size=0)
        s.aggs.bucket('authors', 'cardinality', field='author')
        ms = ms.add(s)
        response_keys.append({'name': 'questions',
                              'results': {'items': 'hits.total.value',
                                          'authors': 'aggregations.authors.value'}})

    if 'events' in categories:
        s = Search(index='meetup') \
            .extra(size=0)
        s.aggs.bucket('meetups', 'sum', field='is_meetup_meetup')
        s.aggs.bucket('people', 'cardinality', field='author_uuid')
        ms = ms.add(s)
        response_keys.append({'name': 'events',
                              'results': {'items': 'aggregations.meetups.value',
                                          'authors': 'aggregations.people.value'}})

    try:
        response = ms.execute()
    except ElasticsearchException as e:
        logger.warning(e)
        response = None

    for keys_results, result in zip(response_keys, response):
        try:
            items = operator.attrgetter(keys_results['results']['items'])(result)
            authors = operator.attrgetter(keys_results['results']['authors'])(result)
        except AttributeError:
            items = '?'
            authors = '?'

        metrics['items'][keys_results['name']] = int(items)
        metrics['authors'][keys_results['name']] = int(authors)

    return metrics


def last_years_evolution(elastic):
    from_date = datetime.datetime.utcnow() - datetime.timedelta(days=5*365)
    to_date = datetime.datetime.utcnow()
    s = Search(using=elastic, index='all') \
        .filter('range', grimoire_creation_date={'gte': from_date, "lte": to_date}) \
        .extra(size=0)
    s.aggs.bucket('data', 'date_histogram',
                  field='grimoire_creation_date',
                  interval="month",
                  min_doc_count=0,
                  extended_bounds={
                      "min": from_date,
                      "max": to_date
                  })

    try:
        response = s.execute()
        buckets = response.aggregations.data.buckets
    except ElasticsearchException as e:
        logger.warning(e)
        buckets = []

    # timestamps = []
    items = []
    for item in buckets:
        # timestamps.append(item.key)
        items.append(item.doc_count)

    return items
