import ssl
import logging
import datetime
from dateutil.relativedelta import relativedelta

from elasticsearch.connection import create_ssl_context
from elasticsearch import Elasticsearch

from .activity import commits as activity_commits
from .activity import issues as activity_issues
from .activity import reviews as activity_reviews

from .community import commits as community_commits
from .community import issues as community_issues
from .community import reviews as community_reviews
from .community import common as community_common

from .utils import year_over_year
from . import other

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


def get_elastic_project(dashboard):
    jwt_key = utils.get_jwt_key(f"Project {dashboard.id}", dashboard.projectrole.backend_role)

    context = create_ssl_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    elastic = Elasticsearch(hosts=[settings.ES_IN_HOST], scheme=settings.ES_IN_PROTO, port=settings.ES_IN_PORT,
                            headers={"Authorization": f"Bearer {jwt_key}"}, ssl_context=context, timeout=5)

    return elastic


def get_metrics(dashboard, from_date, to_date):

    metrics = {}

    metrics.update(get_metrics_in_range(dashboard, from_date, to_date))
    metrics.update(get_metrics_static(dashboard))

    return metrics


def get_metrics_static(dashboard):
    elastic = get_elastic_project(dashboard)

    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = {}
    # Activity git numbers
    metrics['commits_last_month'] = activity_commits.git_commits(elastic, one_month_ago, now)
    metrics['commits_last_year'] = activity_commits.git_commits(elastic, one_year_ago, now)
    metrics['commits_yoy'] = year_over_year(metrics['commits_last_year'],
                                            activity_commits.git_commits(elastic, two_year_ago, one_year_ago))
    metrics['lines_commit_last_month'] = activity_commits.git_lines_commit(elastic, one_month_ago, now)
    metrics['lines_commit_last_year'] = activity_commits.git_lines_commit(elastic, one_year_ago, now)
    metrics['lines_commit_yoy'] = year_over_year(metrics['lines_commit_last_year'],
                                                 activity_commits.git_lines_commit(elastic, two_year_ago, one_year_ago))
    try:
        metrics['lines_commit_file_last_month'] = metrics['lines_commit_last_month'] / activity_commits.git_files_touched(elastic, one_month_ago, now)
    except ZeroDivisionError:
        metrics['lines_commit_file_last_month'] = 0
    try:
        metrics['lines_commit_file_last_year'] = metrics['lines_commit_last_year'] / activity_commits.git_files_touched(elastic, one_year_ago, now)
    except ZeroDivisionError:
        metrics['lines_commit_file_last_year'] = 0
    try:
        lines_commit_file_two_year_ago = activity_commits.git_lines_commit(elastic, two_year_ago, one_year_ago) / activity_commits.git_files_touched(elastic, two_year_ago, one_year_ago)
    except ZeroDivisionError:
        lines_commit_file_two_year_ago = 0
    metrics['lines_commit_file_yoy'] = year_over_year(metrics['lines_commit_file_last_year'],
                                                      lines_commit_file_two_year_ago)

    # Activity issue numbers
    metrics['issues_open_last_month'] = activity_issues.issues_opened(elastic, one_month_ago, now)
    metrics['issues_open_last_year'] = activity_issues.issues_opened(elastic, one_year_ago, now)
    metrics['issues_open_yoy'] = year_over_year(metrics['issues_open_last_year'],
                                                activity_issues.issues_opened(elastic, two_year_ago, one_year_ago))
    metrics['issues_closed_last_month'] = activity_issues.issues_closed(elastic, one_month_ago, now)
    metrics['issues_closed_last_year'] = activity_issues.issues_closed(elastic, one_year_ago, now)
    metrics['issues_closed_yoy'] = year_over_year(metrics['issues_closed_last_year'],
                                                  activity_issues.issues_closed(elastic, two_year_ago, one_year_ago))
    metrics['issues_open_today'] = activity_issues.issues_open_on(elastic, now)
    metrics['issues_open_month_ago'] = activity_issues.issues_open_on(elastic, one_month_ago)
    metrics['issues_open_year_ago'] = activity_issues.issues_open_on(elastic, one_year_ago)

    # Activity issues graphs
    metrics['issues_open_age_bokeh'] = activity_issues.issues_open_age_opened_bokeh(elastic)

    # Activity reviews numbers
    metrics['reviews_open_last_month'] = activity_reviews.reviews_opened(elastic, one_month_ago, now)
    metrics['reviews_open_last_year'] = activity_reviews.reviews_opened(elastic, one_year_ago, now)
    metrics['reviews_open_yoy'] = year_over_year(metrics['reviews_open_last_year'],
                                                 activity_reviews.reviews_opened(elastic, two_year_ago, one_year_ago))
    metrics['reviews_closed_last_month'] = activity_reviews.reviews_closed(elastic, one_month_ago, now)
    metrics['reviews_closed_last_year'] = activity_reviews.reviews_closed(elastic, one_year_ago, now)
    metrics['reviews_closed_yoy'] = year_over_year(metrics['reviews_closed_last_year'],
                                                   activity_reviews.reviews_closed(elastic, two_year_ago, one_year_ago))
    metrics['reviews_open_today'] = activity_reviews.reviews_open_on(elastic, now)
    metrics['reviews_open_month_ago'] = activity_reviews.reviews_open_on(elastic, one_month_ago)
    metrics['reviews_open_year_ago'] = activity_reviews.reviews_open_on(elastic, one_year_ago)

    # Activity reviews graphs
    metrics['reviews_open_age_bokeh'] = activity_reviews.reviews_open_age_opened_bokeh(elastic)

    # Community graphs
    # TODO: Remember to update the documentation about the snapshot date when the time comes
    metrics['commits_authors_aging_bokeh'] = community_commits.authors_aging_bokeh(elastic, now)
    metrics['issues_authors_aging_bokeh'] = community_issues.authors_aging_bokeh(elastic, now)
    metrics['reviews_authors_aging_bokeh'] = community_reviews.authors_aging_bokeh(elastic, now)
    metrics['commits_authors_retained_ratio_bokeh'] = community_commits.authors_retained_ratio_bokeh(elastic, now)
    metrics['issues_authors_retained_ratio_bokeh'] = community_issues.authors_retained_ratio_bokeh(elastic, now)
    metrics['reviews_authors_retained_ratio_bokeh'] = community_reviews.authors_retained_ratio_bokeh(elastic, now)

    return metrics


def get_metrics_in_range(dashboard, from_date, to_date):
    elastic = get_elastic_project(dashboard)

    metrics = {}
    # Activity git graphs
    metrics['commits_bokeh'] = activity_commits.git_commits_bokeh(elastic, from_date, to_date)
    metrics['commits_lines_changed_boked'] = activity_commits.git_lines_changed_bokeh(elastic, from_date, to_date)
    metrics['commits_hour_day_bokeh'] = activity_commits.git_commits_hour_day_bokeh(elastic, from_date, to_date)
    metrics['commits_weekday_bokeh'] = activity_commits.git_commits_weekday_bokeh(elastic, from_date, to_date)
    metrics['commits_heatmap_bokeh'] = activity_commits.git_commits_heatmap_bokeh(elastic, from_date, to_date)
    # Activity issue graphs
    metrics['issues_open_closed_bokeh'] = activity_issues.issues_open_closed_bokeh(elastic, from_date, to_date)
    metrics['issues_open_weekday_bokeh'] = activity_issues.issues_open_weekday_bokeh(elastic, from_date, to_date)
    metrics['issues_closed_weekday_bokeh'] = activity_issues.issues_closed_weekday_bokeh(elastic, from_date, to_date)
    metrics['issues_opened_heatmap_bokeh'] = activity_issues.issues_opened_heatmap_bokeh(elastic, from_date, to_date)
    metrics['issues_closed_heatmap_bokeh'] = activity_issues.issues_closed_heatmap_bokeh(elastic, from_date, to_date)
    # Activity reviews graphs
    metrics['reviews_open_closed_bokeh'] = activity_reviews.reviews_open_closed_bokeh(elastic, from_date, to_date)
    metrics['reviews_open_weekday_bokeh'] = activity_reviews.reviews_open_weekday_bokeh(elastic, from_date, to_date)
    metrics['reviews_closed_weekday_bokeh'] = activity_reviews.reviews_closed_weekday_bokeh(elastic, from_date, to_date)
    metrics['reviews_opened_heatmap_bokeh'] = activity_reviews.reviews_opened_heatmap_bokeh(elastic, from_date, to_date)
    metrics['reviews_closed_heatmap_bokeh'] = activity_reviews.reviews_closed_heatmap_bokeh(elastic, from_date, to_date)
    # Overview/Other
    metrics['author_evolution_bokeh'] = other.author_evolution_bokeh(elastic, from_date, to_date)
    metrics['reviews_opened'] = activity_reviews.reviews_opened(elastic, from_date, to_date)
    metrics['commits_range'] = activity_commits.git_commits(elastic, from_date, to_date)
    metrics['issues_time_to_close'] = other.issues_time_to_close(elastic, from_date, to_date)
    metrics['issues_created_range'] = activity_issues.issues_opened(elastic, from_date, to_date)
    metrics['issues_closed_range'] = activity_issues.issues_closed(elastic, from_date, to_date)
    metrics['review_duration'] = other.review_duration(elastic, from_date, to_date)

    # Community numbers
    metrics['active_people_git'] = community_commits.authors_active(elastic, from_date, to_date)
    metrics['active_people_issues'] = community_issues.active_submitters(elastic, from_date, to_date)
    metrics['active_people_patches'] = community_reviews.active_submitters(elastic, from_date, to_date)
    metrics['onboardings_git'] = community_commits.authors_entering(elastic, from_date, to_date)
    metrics['onboardings_issues'] = community_issues.authors_entering(elastic, from_date, to_date)
    metrics['onboardings_patches'] = community_reviews.authors_entering(elastic, from_date, to_date)

    # Community graphs
    metrics['commits_authors_active_bokeh'] = community_commits.authors_active_bokeh(elastic, from_date, to_date)
    metrics['issues_authors_active_bokeh'] = community_issues.authors_active_bokeh(elastic, from_date, to_date)
    metrics['reviews_authors_active_bokeh'] = community_reviews.authors_active_bokeh(elastic, from_date, to_date)
    metrics['commits_authors_entering_leaving_bokeh'] = community_commits.authors_entering_leaving_bokeh(elastic, from_date, to_date)
    metrics['issues_authors_entering_leaving_bokeh'] = community_issues.authors_entering_leaving_bokeh(elastic, from_date, to_date)
    metrics['reviews_authors_entering_leaving_bokeh'] = community_reviews.authors_entering_leaving_bokeh(elastic, from_date, to_date)
    metrics['organizational_diversity_authors_bokeh'] = community_common.organizational_diversity_authors(elastic, from_date, to_date)
    metrics['organizational_diversity_commits_bokeh'] = community_common.organizational_diversity_commits(elastic, from_date, to_date)

    return metrics
