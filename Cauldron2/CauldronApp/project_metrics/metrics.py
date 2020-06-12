import ssl
import logging

from elasticsearch.connection import create_ssl_context
from elasticsearch import Elasticsearch

from .activity import commits
from .activity import issues
from .activity import reviews
from .utils import year_over_year

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
      If it is a Bokeh visualization, you will need to add the variable in the script in the end of the file.
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

    metrics = {}
    # Activity git numbers
    metrics['commits_last_month'] = commits.git_commits(elastic, 'now-1M', 'now')
    metrics['commits_last_year'] = commits.git_commits(elastic, 'now-1y', 'now')
    metrics['commits_yoy'] = year_over_year(metrics['commits_last_year'],
                                            commits.git_commits(elastic, 'now-2y', 'now-1y'))
    metrics['lines_commit_last_month'] = commits.git_lines_commit(elastic, 'now-1M', 'now')
    metrics['lines_commit_last_year'] = commits.git_lines_commit(elastic, 'now-1y', 'now')
    metrics['lines_commit_yoy'] = year_over_year(metrics['lines_commit_last_year'],
                                                 commits.git_lines_commit(elastic, 'now-2y', 'now-1y'))
    try:
        metrics['lines_commit_file_last_month'] = metrics['lines_commit_last_month'] / commits.git_files_touched(elastic, 'now-1M', 'now')
    except ZeroDivisionError:
        metrics['lines_commit_file_last_month'] = 0
    try:
        metrics['lines_commit_file_last_year'] = metrics['lines_commit_last_year'] / commits.git_files_touched(elastic, 'now-1y', 'now')
    except ZeroDivisionError:
        metrics['lines_commit_file_last_year'] = 0
    try:
        lines_commit_file_two_year_ago = commits.git_lines_commit(elastic, 'now-2y', 'now-1y') / commits.git_files_touched(elastic, 'now-2y', 'now-1y')
    except ZeroDivisionError:
        lines_commit_file_two_year_ago = 0
    metrics['lines_commit_file_yoy'] = year_over_year(metrics['lines_commit_file_last_year'],
                                                      lines_commit_file_two_year_ago)
    # Activity git graphs
    metrics['commits_bokeh'] = commits.git_commits_bokeh(elastic, from_date, to_date)
    metrics['commits_hour_day_bokeh'] = commits.git_commits_hour_day_bokeh(elastic)
    metrics['commits_weekday_bokeh'] = commits.git_commits_weekday_bokeh(elastic)
    metrics['commits_lines_changed_boked'] = commits.git_lines_changed_bokeh(elastic, from_date, to_date)
    # Activity issue numbers
    metrics['issues_open_last_month'] = issues.issues_opened(elastic, 'now-1M', 'now')
    metrics['issues_open_last_year'] = issues.issues_opened(elastic, 'now-1y', 'now')
    metrics['issues_open_yoy'] = year_over_year(metrics['issues_open_last_year'],
                                                issues.issues_opened(elastic, 'now-2y', 'now-1y'))
    metrics['issues_closed_last_month'] = issues.issues_closed(elastic, 'now-1M', 'now')
    metrics['issues_closed_last_year'] = issues.issues_closed(elastic, 'now-1y', 'now')
    metrics['issues_closed_yoy'] = year_over_year(metrics['issues_closed_last_year'],
                                                  issues.issues_closed(elastic, 'now-2y', 'now-1y'))
    metrics['issues_open_today'] = issues.issues_open_on(elastic, 'now')
    metrics['issues_open_month_ago'] = issues.issues_open_on(elastic, 'now-1M')
    metrics['issues_open_year_ago'] = issues.issues_open_on(elastic, 'now-1y')
    # Activity issue graphs
    metrics['issues_open_closed_bokeh'] = issues.issues_open_closed_bokeh(elastic, from_date, to_date)
    metrics['issues_open_age_bokeh'] = issues.issues_open_age_opened_bokeh(elastic)
    metrics['issues_open_weekday_bokeh'] = issues.issues_open_weekday_bokeh(elastic)
    metrics['issues_closed_weekday_bokeh'] = issues.issues_closed_weekday_bokeh(elastic)
    # Activity reviews numbers
    metrics['reviews_open_last_month'] = reviews.reviews_opened(elastic, 'now-1M', 'now')
    metrics['reviews_open_last_year'] = reviews.reviews_opened(elastic, 'now-1y', 'now')
    metrics['reviews_open_yoy'] = year_over_year(metrics['reviews_open_last_year'],
                                                 reviews.reviews_opened(elastic, 'now-2y', 'now-1y'))
    metrics['reviews_closed_last_month'] = reviews.reviews_closed(elastic, 'now-1M', 'now')
    metrics['reviews_closed_last_year'] = reviews.reviews_closed(elastic, 'now-1y', 'now')
    metrics['reviews_closed_yoy'] = year_over_year(metrics['reviews_closed_last_year'],
                                                   reviews.reviews_closed(elastic, 'now-2y', 'now-1y'))
    metrics['reviews_open_today'] = reviews.reviews_open_on(elastic, 'now')
    metrics['reviews_open_month_ago'] = reviews.reviews_open_on(elastic, 'now-1M')
    metrics['reviews_open_year_ago'] = reviews.reviews_open_on(elastic, 'now-1y')
    # Activity issue graphs
    metrics['reviews_open_closed_bokeh'] = reviews.reviews_open_closed_bokeh(elastic, from_date, to_date)
    metrics['reviews_open_age_bokeh'] = reviews.reviews_open_age_opened_bokeh(elastic)
    metrics['reviews_open_weekday_bokeh'] = reviews.reviews_open_weekday_bokeh(elastic)
    metrics['reviews_closed_weekday_bokeh'] = reviews.reviews_closed_weekday_bokeh(elastic)
    return metrics
