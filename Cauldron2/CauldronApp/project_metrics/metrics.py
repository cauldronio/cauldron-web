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

from .performance import issues as performance_issues
from .performance import reviews as performance_reviews

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
    - Add the output of the function to the dictionary returned by 'get_category_metrics' in the corresponding category
Open CauldronApp/static/js/project.js
    - Include your metric in the function `updateMetricsData`. It is called when the user
      updates the date picker range.
"""


def get_elastic_project(project):
    jwt_key = utils.get_jwt_key(f"Project {project.id}", project.projectrole.backend_role)

    context = create_ssl_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    elastic = Elasticsearch(hosts=[settings.ES_IN_HOST], scheme=settings.ES_IN_PROTO, port=settings.ES_IN_PORT,
                            headers={"Authorization": f"Bearer {jwt_key}"}, ssl_context=context, timeout=5)

    return elastic


def get_compare_metrics(projects, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    for project in projects:
        elastic = get_elastic_project(project)
        metrics[project.id] = {
            'commits_range': activity_commits.git_commits(elastic, from_date, to_date),
            'reviews_opened': activity_reviews.reviews_opened(elastic, from_date, to_date),
            'review_duration': other.review_duration(elastic, from_date, to_date),
            'issues_created_range': activity_issues.issues_opened(elastic, from_date, to_date),
            'issues_closed_range': activity_issues.issues_closed(elastic, from_date, to_date),
            'issues_time_to_close': other.issues_time_to_close(elastic, from_date, to_date),
            'commits_last_month': activity_commits.git_commits(elastic, one_month_ago, now),
            'commits_last_year': activity_commits.git_commits(elastic, one_year_ago, now),
            'lines_commit_last_month': activity_commits.git_lines_commit(elastic, one_month_ago, now),
            'lines_commit_last_year': activity_commits.git_lines_commit(elastic, one_year_ago, now),
            'issues_open_last_month': activity_issues.issues_opened(elastic, one_month_ago, now),
            'issues_open_last_year': activity_issues.issues_opened(elastic, one_year_ago, now),
            'issues_closed_last_month': activity_issues.issues_closed(elastic, one_month_ago, now),
            'issues_closed_last_year': activity_issues.issues_closed(elastic, one_year_ago, now),
            'issues_open_today': activity_issues.issues_open_on(elastic, now),
            'issues_open_month_ago': activity_issues.issues_open_on(elastic, one_month_ago),
            'issues_open_year_ago': activity_issues.issues_open_on(elastic, one_year_ago),
            'reviews_open_last_month': activity_reviews.reviews_opened(elastic, one_month_ago, now),
            'reviews_open_last_year': activity_reviews.reviews_opened(elastic, one_year_ago, now),
            'reviews_closed_last_month': activity_reviews.reviews_closed(elastic, one_month_ago, now),
            'reviews_closed_last_year': activity_reviews.reviews_closed(elastic, one_year_ago, now),
            'reviews_open_today': activity_reviews.reviews_open_on(elastic, now),
            'reviews_open_month_ago': activity_reviews.reviews_open_on(elastic, one_month_ago),
            'reviews_open_year_ago': activity_reviews.reviews_open_on(elastic, one_year_ago),
            'active_people_git': community_commits.authors_active(elastic, from_date, to_date),
            'active_people_issues': community_issues.active_submitters(elastic, from_date, to_date),
            'active_people_patches': community_reviews.active_submitters(elastic, from_date, to_date),
            'onboardings_git': community_commits.authors_entering(elastic, from_date, to_date),
            'onboardings_issues': community_issues.authors_entering(elastic, from_date, to_date),
            'onboardings_patches': community_reviews.authors_entering(elastic, from_date, to_date),
        }

        metrics[project.id]['commits_yoy'] = year_over_year(metrics[project.id]['commits_last_year'],
                                                            activity_commits.git_commits(elastic, two_year_ago, one_year_ago))

        metrics[project.id]['lines_commit_yoy'] = year_over_year(metrics[project.id]['lines_commit_last_year'],
                                                                 activity_commits.git_lines_commit(elastic, two_year_ago, one_year_ago))

        metrics[project.id]['issues_open_yoy'] = year_over_year(metrics[project.id]['issues_open_last_year'],
                                                                activity_issues.issues_opened(elastic, two_year_ago, one_year_ago))

        metrics[project.id]['issues_closed_yoy'] = year_over_year(metrics[project.id]['issues_closed_last_year'],
                                                                  activity_issues.issues_closed(elastic, two_year_ago, one_year_ago))

        metrics[project.id]['reviews_open_yoy'] = year_over_year(metrics[project.id]['reviews_open_last_year'],
                                                                 activity_reviews.reviews_opened(elastic, two_year_ago, one_year_ago))

        metrics[project.id]['reviews_closed_yoy'] = year_over_year(metrics[project.id]['reviews_closed_last_year'],
                                                                   activity_reviews.reviews_closed(elastic, two_year_ago, one_year_ago))

        try:
            metrics[project.id]['lines_commit_file_last_month'] = metrics[project.id]['lines_commit_last_month'] / activity_commits.git_files_touched(elastic, one_month_ago, now)
        except (ZeroDivisionError, TypeError):
            metrics[project.id]['lines_commit_file_last_month'] = 0

        try:
            metrics[project.id]['lines_commit_file_last_year'] = metrics[project.id]['lines_commit_last_year'] / activity_commits.git_files_touched(elastic, one_year_ago, now)
        except (ZeroDivisionError, TypeError):
            metrics[project.id]['lines_commit_file_last_year'] = 0

        try:
            lines_commit_file_two_year_ago = activity_commits.git_lines_commit(elastic, two_year_ago, one_year_ago) / activity_commits.git_files_touched(elastic, two_year_ago, one_year_ago)
        except (ZeroDivisionError, TypeError):
            lines_commit_file_two_year_ago = 0

        metrics[project.id]['lines_commit_file_yoy'] = year_over_year(metrics[project.id]['lines_commit_file_last_year'],
                                                                  lines_commit_file_two_year_ago)

    return metrics


def get_compare_charts(projects, from_date, to_date):
    elastics = dict()
    for project in projects:
        elastic = get_elastic_project(project)
        elastics[project.id] = elastic

    charts = {
        'git_commits_bokeh_compare': activity_commits.git_commits_bokeh_compare(elastics, from_date, to_date),
        'git_authors_bokeh_compare': community_commits.git_authors_bokeh_compare(elastics, from_date, to_date),
    }

    return charts


def get_category_metrics(project, category, from_date, to_date):
    # ['overview',
    # 'activity-overview', 'activity-git', 'activity-issues', 'activity-reviews',
    # 'community-overview', 'community-git', 'community-issues', 'community-reviews']
    elastic = get_elastic_project(project)
    if category == 'overview':
        return overview_metrics(elastic, from_date, to_date)
    elif category == 'activity-overview':
        return activity_overview_metrics(elastic, from_date, to_date)
    elif category == 'activity-git':
        return activity_git_metrics(elastic, from_date, to_date)
    elif category == 'activity-issues':
        return activity_issues_metrics(elastic, from_date, to_date)
    elif category == 'activity-reviews':
        return activity_reviews_metrics(elastic, from_date, to_date)
    elif category == 'community-overview':
        return community_overview_metrics(elastic, from_date, to_date)
    elif category == 'community-git':
        return community_git_metrics(elastic, from_date, to_date)
    elif category == 'community-issues':
        return community_issues_metrics(elastic, from_date, to_date)
    elif category == 'community-reviews':
        return community_reviews_metrics(elastic, from_date, to_date)
    elif category == 'performance-overview':
        return performance_overview_metrics(elastic, from_date, to_date)
    elif category == 'performance-issues':
        return performance_issues_metrics(elastic, from_date, to_date)
    elif category == 'performance-reviews':
        return performance_reviews_metrics(elastic, from_date, to_date)
    else:
        return overview_metrics(elastic, from_date, to_date)


def overview_metrics(elastic, from_date, to_date):
    metrics = dict()
    metrics['commits_range'] = activity_commits.git_commits(elastic, from_date, to_date)
    metrics['reviews_opened'] = activity_reviews.reviews_opened(elastic, from_date, to_date)
    metrics['review_duration'] = other.review_duration(elastic, from_date, to_date)
    metrics['issues_created_range'] = activity_issues.issues_opened(elastic, from_date, to_date)
    metrics['issues_closed_range'] = activity_issues.issues_closed(elastic, from_date, to_date)
    metrics['issues_time_to_close'] = other.issues_time_to_close(elastic, from_date, to_date)
    metrics['commits_bokeh_overview'] = activity_commits.git_commits_bokeh(elastic, from_date, to_date)
    metrics['author_evolution_bokeh'] = other.author_evolution_bokeh(elastic, from_date, to_date)
    metrics['issues_open_closed_bokeh_overview'] = activity_issues.issues_open_closed_bokeh(elastic, from_date, to_date)
    metrics['reviews_open_closed_bokeh_overview'] = activity_reviews.reviews_open_closed_bokeh(elastic, from_date, to_date)
    return metrics


def activity_overview_metrics(elastic, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics commits
    metrics['commits_activity_overview'] = activity_commits.git_commits(elastic, from_date, to_date)
    lines_commit = activity_commits.git_lines_commit(elastic, from_date, to_date)
    metrics['lines_commit_activity_overview'] = f"{lines_commit:.2f}"
    try:
        lines_commit_file = lines_commit / activity_commits.git_files_touched(elastic, from_date, to_date)
        metrics['lines_commit_file_activity_overview'] = f"{lines_commit_file:.2f}"
    except ZeroDivisionError:
        metrics['lines_commit_file_activity_overview'] = 0
    # Metrics Issues
    metrics['issues_created_activity_overview'] = activity_issues.issues_opened(elastic, from_date, to_date)
    metrics['issues_closed_activity_overview'] = activity_issues.issues_closed(elastic, from_date, to_date)
    metrics['issues_open_activity_overview'] = activity_issues.issues_open_on(elastic, to_date)
    # Metrics reviews
    metrics['reviews_created_activity_overview'] = activity_reviews.reviews_opened(elastic, from_date, to_date)
    metrics['reviews_closed_activity_overview'] = activity_reviews.reviews_closed(elastic, from_date, to_date)
    metrics['reviews_open_activity_overview'] = activity_reviews.reviews_open_on(elastic, to_date)
    # Visualizations
    metrics['commits_activity_overview_bokeh'] = activity_commits.git_commits_bokeh_line(elastic, from_date, to_date)
    metrics['issues_open_closed_activity_overview_bokeh'] = activity_issues.issues_open_closed_bokeh(elastic, from_date, to_date)
    metrics['reviews_open_closed_activity_overview_bokeh'] = activity_reviews.reviews_open_closed_bokeh(elastic, from_date, to_date)
    return metrics


def activity_git_metrics(elastic, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['commits_last_month'] = activity_commits.git_commits(elastic, one_month_ago, now)
    metrics['commits_last_year'] = activity_commits.git_commits(elastic, one_year_ago, now)
    commits_yoy = year_over_year(metrics['commits_last_year'],
                                 activity_commits.git_commits(elastic, two_year_ago, one_year_ago))
    metrics['commits_yoy'] = f"{commits_yoy:+.2f}%"

    lines_commit_last_month = activity_commits.git_lines_commit(elastic, one_month_ago, now)
    metrics['lines_commit_last_month'] = f"{lines_commit_last_month:.2f}"

    lines_commit_last_year = activity_commits.git_lines_commit(elastic, one_year_ago, now)
    metrics['lines_commit_last_year'] = f"{lines_commit_last_year:.2f}"

    lines_commit_yoy = year_over_year(lines_commit_last_year,
                                      activity_commits.git_lines_commit(elastic, two_year_ago, one_year_ago))
    metrics['lines_commit_yoy'] = f"{lines_commit_yoy:+.2f}%"
    try:
        lines_commit_file_last_month = lines_commit_last_month / activity_commits.git_files_touched(elastic, one_month_ago, now)
        metrics['lines_commit_file_last_month'] = f"{lines_commit_file_last_month:.2f}"
    except (ZeroDivisionError, TypeError):
        metrics['lines_commit_file_last_month'] = 0
    try:
        lines_commit_file_last_year = lines_commit_last_year / activity_commits.git_files_touched(elastic, one_year_ago, now)
        metrics['lines_commit_file_last_year'] = f"{lines_commit_file_last_year:.2f}"
    except (ZeroDivisionError, TypeError):
        lines_commit_file_last_year = 0
        metrics['lines_commit_file_last_year'] = 0
    try:
        lines_commit_file_two_year_ago = activity_commits.git_lines_commit(elastic, two_year_ago, one_year_ago) / activity_commits.git_files_touched(elastic, two_year_ago, one_year_ago)
    except (ZeroDivisionError, TypeError):
        lines_commit_file_two_year_ago = 0
    lines_commit_file_yoy = year_over_year(lines_commit_file_last_year,
                                           lines_commit_file_two_year_ago)
    metrics['lines_commit_file_yoy'] = f"{lines_commit_file_yoy:+.2f}%"
    # Visualizations
    metrics['commits_bokeh'] = activity_commits.git_commits_bokeh(elastic, from_date, to_date)
    metrics['commits_lines_changed_bokeh'] = activity_commits.git_lines_changed_bokeh(elastic, from_date, to_date)
    metrics['commits_hour_day_bokeh'] = activity_commits.git_commits_hour_day_bokeh(elastic, from_date, to_date)
    metrics['commits_weekday_bokeh'] = activity_commits.git_commits_weekday_bokeh(elastic, from_date, to_date)
    metrics['commits_heatmap_bokeh'] = activity_commits.git_commits_heatmap_bokeh(elastic, from_date, to_date)
    return metrics


def activity_issues_metrics(elastic, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['issues_open_last_month'] = activity_issues.issues_opened(elastic, one_month_ago, now)
    metrics['issues_open_last_year'] = activity_issues.issues_opened(elastic, one_year_ago, now)
    issues_open_yoy = year_over_year(metrics['issues_open_last_year'],
                                     activity_issues.issues_opened(elastic, two_year_ago, one_year_ago))
    metrics['issues_open_yoy'] = f"{issues_open_yoy:+.2f}%"
    metrics['issues_closed_last_month'] = activity_issues.issues_closed(elastic, one_month_ago, now)
    metrics['issues_closed_last_year'] = activity_issues.issues_closed(elastic, one_year_ago, now)
    issues_closed_yoy = year_over_year(metrics['issues_closed_last_year'],
                                       activity_issues.issues_closed(elastic, two_year_ago, one_year_ago))
    metrics['issues_closed_yoy'] = f"{issues_closed_yoy:+.2f}%"
    # Visualizations
    metrics['issues_open_closed_bokeh'] = activity_issues.issues_open_closed_bokeh(elastic, from_date, to_date)
    metrics['issues_open_weekday_bokeh'] = activity_issues.issues_open_weekday_bokeh(elastic, from_date, to_date)
    metrics['issues_closed_weekday_bokeh'] = activity_issues.issues_closed_weekday_bokeh(elastic, from_date, to_date)
    metrics['issues_opened_heatmap_bokeh'] = activity_issues.issues_opened_heatmap_bokeh(elastic, from_date, to_date)
    metrics['issues_closed_heatmap_bokeh'] = activity_issues.issues_closed_heatmap_bokeh(elastic, from_date, to_date)
    return metrics


def activity_reviews_metrics(elastic, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['reviews_open_last_month'] = activity_reviews.reviews_opened(elastic, one_month_ago, now)
    metrics['reviews_open_last_year'] = activity_reviews.reviews_opened(elastic, one_year_ago, now)
    reviews_open_yoy = year_over_year(metrics['reviews_open_last_year'],
                                      activity_reviews.reviews_opened(elastic, two_year_ago, one_year_ago))
    metrics['reviews_open_yoy'] = f"{reviews_open_yoy:+.2f}%"
    metrics['reviews_closed_last_month'] = activity_reviews.reviews_closed(elastic, one_month_ago, now)
    metrics['reviews_closed_last_year'] = activity_reviews.reviews_closed(elastic, one_year_ago, now)
    reviews_closed_yoy = year_over_year(metrics['reviews_closed_last_year'],
                                        activity_reviews.reviews_closed(elastic, two_year_ago, one_year_ago))
    metrics['reviews_closed_yoy'] = f"{reviews_closed_yoy:+.2f}%"
    # Visualizations
    metrics['reviews_open_closed_bokeh'] = activity_reviews.reviews_open_closed_bokeh(elastic, from_date, to_date)
    metrics['reviews_open_weekday_bokeh'] = activity_reviews.reviews_open_weekday_bokeh(elastic, from_date, to_date)
    metrics['reviews_closed_weekday_bokeh'] = activity_reviews.reviews_closed_weekday_bokeh(elastic, from_date, to_date)
    metrics['reviews_opened_heatmap_bokeh'] = activity_reviews.reviews_opened_heatmap_bokeh(elastic, from_date, to_date)
    metrics['reviews_closed_heatmap_bokeh'] = activity_reviews.reviews_closed_heatmap_bokeh(elastic, from_date, to_date)
    return metrics


def community_overview_metrics(elastic, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_git_community_overview'] = community_commits.authors_active(elastic, from_date, to_date)
    metrics['active_people_issues_community_overview'] = community_issues.active_submitters(elastic, from_date, to_date)
    metrics['active_people_patches_community_overview'] = community_reviews.active_submitters(elastic, from_date, to_date)
    metrics['onboardings_git_community_overview'] = community_commits.authors_entering(elastic, from_date, to_date)
    metrics['onboardings_issues_community_overview'] = community_issues.authors_entering(elastic, from_date, to_date)
    metrics['onboardings_patches_community_overview'] = community_reviews.authors_entering(elastic, from_date, to_date)

    metrics['commits_authors_active_community_overview_bokeh'] = community_commits.authors_active_bokeh(elastic, from_date, to_date)
    metrics['issues_authors_active_community_overview_bokeh'] = community_issues.authors_active_bokeh(elastic, from_date, to_date)
    metrics['reviews_authors_active_community_overview_bokeh'] = community_reviews.authors_active_bokeh(elastic, from_date, to_date)
    return metrics


def community_git_metrics(elastic, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_git'] = community_commits.authors_active(elastic, from_date, to_date)
    metrics['onboardings_git'] = community_commits.authors_entering(elastic, from_date, to_date)

    metrics['commits_authors_active_bokeh'] = community_commits.authors_active_bokeh(elastic, from_date, to_date)
    metrics['commits_authors_entering_leaving_bokeh'] = community_commits.authors_entering_leaving_bokeh(elastic, from_date, to_date)
    metrics['organizational_diversity_authors_bokeh'] = community_common.organizational_diversity_authors(elastic, from_date, to_date)
    metrics['organizational_diversity_commits_bokeh'] = community_common.organizational_diversity_commits(elastic, from_date, to_date)
    metrics['commits_authors_aging_bokeh'] = community_commits.authors_aging_bokeh(elastic, to_date)
    metrics['commits_authors_retained_ratio_bokeh'] = community_commits.authors_retained_ratio_bokeh(elastic, to_date)
    return metrics


def community_issues_metrics(elastic, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_issues'] = community_issues.active_submitters(elastic, from_date, to_date)
    metrics['onboardings_issues'] = community_issues.authors_entering(elastic, from_date, to_date)

    metrics['issues_authors_active_bokeh'] = community_issues.authors_active_bokeh(elastic, from_date, to_date)
    metrics['issues_authors_entering_leaving_bokeh'] = community_issues.authors_entering_leaving_bokeh(elastic, from_date, to_date)
    metrics['issues_authors_aging_bokeh'] = community_issues.authors_aging_bokeh(elastic, to_date)
    metrics['issues_authors_retained_ratio_bokeh'] = community_issues.authors_retained_ratio_bokeh(elastic, to_date)
    return metrics


def community_reviews_metrics(elastic, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_patches'] = community_reviews.active_submitters(elastic, from_date, to_date)
    metrics['onboardings_patches'] = community_reviews.authors_entering(elastic, from_date, to_date)

    metrics['reviews_authors_active_bokeh'] = community_reviews.authors_active_bokeh(elastic, from_date, to_date)
    metrics['reviews_authors_entering_leaving_bokeh'] = community_reviews.authors_entering_leaving_bokeh(elastic, from_date, to_date)
    metrics['reviews_authors_aging_bokeh'] = community_reviews.authors_aging_bokeh(elastic, to_date)
    metrics['reviews_authors_retained_ratio_bokeh'] = community_reviews.authors_retained_ratio_bokeh(elastic, to_date)
    return metrics


def performance_overview_metrics(elastic, from_date, to_date):
    now = datetime.datetime.now()

    metrics = dict()
    # Metrics
    metrics['issues_time_open_average_performance_overview'] = performance_issues.average_open_time(elastic, now)
    metrics['issues_time_open_median_performance_overview'] = performance_issues.median_open_time(elastic, now)
    metrics['open_issues_performance_overview'] = performance_issues.open_issues(elastic, now)
    metrics['reviews_time_open_average_performance_overview'] = performance_reviews.average_open_time(elastic, now)
    metrics['reviews_time_open_median_performance_overview'] = performance_reviews.median_open_time(elastic, now)
    metrics['open_reviews_performance_overview'] = performance_reviews.open_reviews(elastic, now)
    # Visualizations
    metrics['issues_created_ttc_performance_overview_bokeh'] = performance_issues.ttc_created_issues_bokeh(elastic, from_date, to_date)
    metrics['issues_closed_ttc_performance_overview_bokeh'] = performance_issues.ttc_closed_issues_bokeh(elastic, from_date, to_date)
    metrics['reviews_created_ttc_performance_overview_bokeh'] = performance_reviews.ttc_created_reviews_bokeh(elastic, from_date, to_date)
    metrics['reviews_closed_ttc_performance_overview_bokeh'] = performance_reviews.ttc_closed_reviews_bokeh(elastic, from_date, to_date)
    return metrics


def performance_issues_metrics(elastic, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_years_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['issues_time_to_close_median_last_month'] = performance_issues.median_time_to_close(elastic, one_month_ago, now)
    metrics['issues_time_to_close_median_last_year'] = performance_issues.median_time_to_close(elastic, one_year_ago, now)
    median_closing_time_yoy = year_over_year(metrics['issues_time_to_close_median_last_month'],
                                             performance_issues.median_time_to_close(elastic, two_years_ago, now))
    metrics['issues_time_to_close_median_yoy'] = f"{median_closing_time_yoy:+.2f}%"
    metrics['issues_time_open_average'] = performance_issues.average_open_time(elastic, now)
    metrics['issues_time_open_median'] = performance_issues.median_open_time(elastic, now)
    metrics['open_issues'] = performance_issues.open_issues(elastic, now)
    # Visualizations
    metrics['issues_created_ttc_bokeh'] = performance_issues.ttc_created_issues_bokeh(elastic, from_date, to_date)
    metrics['issues_still_open_bokeh'] = performance_issues.issues_still_open_by_creation_date_bokeh(elastic)
    metrics['issues_closed_ttc_bokeh'] = performance_issues.ttc_closed_issues_bokeh(elastic, from_date, to_date)
    metrics['issues_created_closed_ratio_bokeh'] = performance_issues.created_closed_issues_ratio_bokeh(elastic, from_date, to_date)
    return metrics


def performance_reviews_metrics(elastic, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_years_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['reviews_time_to_close_median_last_month'] = performance_reviews.median_time_to_close(elastic, one_month_ago, now)
    metrics['reviews_time_to_close_median_last_year'] = performance_reviews.median_time_to_close(elastic, one_year_ago, now)
    median_closing_time_yoy = year_over_year(metrics['reviews_time_to_close_median_last_month'],
                                             performance_reviews.median_time_to_close(elastic, two_years_ago, now))
    metrics['reviews_time_to_close_median_yoy'] = f"{median_closing_time_yoy:+.2f}%"
    metrics['reviews_time_open_average'] = performance_reviews.average_open_time(elastic, now)
    metrics['reviews_time_open_median'] = performance_reviews.median_open_time(elastic, now)
    metrics['open_reviews'] = performance_reviews.open_reviews(elastic, now)
    # Visualizations
    metrics['reviews_created_ttc_bokeh'] = performance_reviews.ttc_created_reviews_bokeh(elastic, from_date, to_date)
    metrics['reviews_still_open_bokeh'] = performance_reviews.reviews_still_open_by_creation_date_bokeh(elastic)
    metrics['reviews_closed_ttc_bokeh'] = performance_reviews.ttc_closed_reviews_bokeh(elastic, from_date, to_date)
    metrics['reviews_created_closed_ratio_bokeh'] = performance_reviews.created_closed_reviews_ratio_bokeh(elastic, from_date, to_date)
    return metrics
