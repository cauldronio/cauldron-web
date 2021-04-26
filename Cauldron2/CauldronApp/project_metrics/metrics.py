import ssl
import logging
import datetime
from dateutil.relativedelta import relativedelta

from elasticsearch.connection import create_ssl_context
from elasticsearch import Elasticsearch

from .activity import commits as activity_commits
from .activity import issues as activity_issues
from .activity import reviews as activity_reviews
from .activity import stackexchange as activity_stackexchange

from .community import commits as community_commits
from .community import issues as community_issues
from .community import reviews as community_reviews
from .community import common as community_common
from .community import stackexchange as community_stackexchange

from .performance import issues as performance_issues
from .performance import reviews as performance_reviews

from .utils import year_over_year
from . import other

from CauldronApp import utils
from Cauldron2 import settings

logger = logging.getLogger(__name__)

""" How to create new metrics

Open CauldronApp/project_metrics.py
    - Create a new function with the following parameters: elastic, urls, from_date, to_date.
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


def get_category_compare_metrics(projects, category, urls, from_date, to_date):
    if category == 'overview':
        return compare_overview_metrics(projects, urls, from_date, to_date)
    elif category == 'activity-git':
        return compare_activity_git_metrics(projects, urls, from_date, to_date)
    elif category == 'activity-issues':
        return compare_activity_issues_metrics(projects, urls, from_date, to_date)
    elif category == 'activity-reviews':
        return compare_activity_reviews_metrics(projects, urls, from_date, to_date)
    elif category == 'community-overview':
        return compare_community_overview_metrics(projects, urls, from_date, to_date)
    else:
        return compare_overview_metrics(projects, urls, from_date, to_date)


def compare_overview_metrics(projects, urls, from_date, to_date):
    data = dict()
    data['metrics'] = dict()
    data['charts'] = dict()

    elastics = dict()
    for project in projects:
        elastic = get_elastic_project(project)
        elastics[project.id] = elastic
        # Metrics
        data['metrics'][project.id] = {
            'commits_range': activity_commits.git_commits(elastic, urls, from_date, to_date),
            'reviews_opened': activity_reviews.reviews_opened(elastic, urls, from_date, to_date),
            'review_duration': other.review_duration(elastic, urls, from_date, to_date),
            'issues_created_range': activity_issues.issues_opened(elastic, urls, from_date, to_date),
            'issues_closed_range': activity_issues.issues_closed(elastic, urls, from_date, to_date),
            'issues_time_to_close': other.issues_time_to_close(elastic, urls, from_date, to_date),
        }

    # Visualizations
    data['charts']['git_commits_bokeh_compare'] = activity_commits.git_commits_bokeh_compare(elastics, urls, from_date, to_date)
    data['charts']['issues_created_bokeh_compare'] = activity_issues.issues_created_bokeh_compare(elastics, from_date, to_date)
    data['charts']['reviews_created_bokeh_compare'] = activity_reviews.reviews_created_bokeh_compare(elastics, from_date, to_date)


    return data


def compare_activity_git_metrics(projects, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    data = dict()
    data['metrics'] = dict()
    data['charts'] = dict()

    elastics = dict()
    for project in projects:
        elastic = get_elastic_project(project)
        elastics[project.id] = elastic
        # Metrics
        data['metrics'][project.id] = {
            'commits_last_month': activity_commits.git_commits(elastic, urls, one_month_ago, now),
            'commits_last_year': activity_commits.git_commits(elastic, urls, one_year_ago, now),
            'lines_commit_last_month': activity_commits.git_lines_commit(elastic, urls, one_month_ago, now),
            'lines_commit_last_year': activity_commits.git_lines_commit(elastic, urls, one_year_ago, now),
        }

        data['metrics'][project.id]['commits_yoy'] = year_over_year(data['metrics'][project.id]['commits_last_year'],
                                                            activity_commits.git_commits(elastic, urls, two_year_ago, one_year_ago))

        data['metrics'][project.id]['lines_commit_yoy'] = year_over_year(data['metrics'][project.id]['lines_commit_last_year'],
                                                                 activity_commits.git_lines_commit(elastic, urls, two_year_ago, one_year_ago))

        try:
            data['metrics'][project.id]['lines_commit_file_last_month'] = data['metrics'][project.id]['lines_commit_last_month'] / activity_commits.git_files_touched(elastic, urls, one_month_ago, now)
        except (ZeroDivisionError, TypeError):
            data['metrics'][project.id]['lines_commit_file_last_month'] = 0

        try:
            data['metrics'][project.id]['lines_commit_file_last_year'] = data['metrics'][project.id]['lines_commit_last_year'] / activity_commits.git_files_touched(elastic, urls, one_year_ago, now)
        except (ZeroDivisionError, TypeError):
            data['metrics'][project.id]['lines_commit_file_last_year'] = 0

        try:
            lines_commit_file_two_year_ago = activity_commits.git_lines_commit(elastic, urls, two_year_ago, one_year_ago) / activity_commits.git_files_touched(elastic, urls, two_year_ago, one_year_ago)
        except (ZeroDivisionError, TypeError):
            lines_commit_file_two_year_ago = 0

        data['metrics'][project.id]['lines_commit_file_yoy'] = year_over_year(data['metrics'][project.id]['lines_commit_file_last_year'],
                                                                  lines_commit_file_two_year_ago)

    # Visualizations
    data['charts']['git_commits_bokeh_compare'] = activity_commits.git_commits_bokeh_compare(elastics, urls, from_date, to_date)

    return data


def compare_activity_issues_metrics(projects, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    data = dict()
    data['metrics'] = dict()
    data['charts'] = dict()

    elastics = dict()
    for project in projects:
        elastic = get_elastic_project(project)
        elastics[project.id] = elastic
        # Metrics
        data['metrics'][project.id] = {
            'issues_open_last_month': activity_issues.issues_opened(elastic, urls, one_month_ago, now),
            'issues_open_last_year': activity_issues.issues_opened(elastic, urls, one_year_ago, now),
            'issues_closed_last_month': activity_issues.issues_closed(elastic, urls, one_month_ago, now),
            'issues_closed_last_year': activity_issues.issues_closed(elastic, urls, one_year_ago, now),
            'issues_open_today': activity_issues.issues_open_on(elastic, urls, now),
            'issues_open_month_ago': activity_issues.issues_open_on(elastic, urls, one_month_ago),
            'issues_open_year_ago': activity_issues.issues_open_on(elastic, urls, one_year_ago),
        }

        data['metrics'][project.id]['issues_open_yoy'] = year_over_year(data['metrics'][project.id]['issues_open_last_year'],
                                                                activity_issues.issues_opened(elastic, urls, two_year_ago, one_year_ago))

        data['metrics'][project.id]['issues_closed_yoy'] = year_over_year(data['metrics'][project.id]['issues_closed_last_year'],
                                                                  activity_issues.issues_closed(elastic, urls, two_year_ago, one_year_ago))

    # Visualizations
    data['charts']['issues_created_bokeh_compare'] = activity_issues.issues_created_bokeh_compare(elastics, from_date, to_date)
    data['charts']['issues_closed_bokeh_compare'] = activity_issues.issues_closed_bokeh_compare(elastics, from_date, to_date)

    return data


def compare_activity_reviews_metrics(projects, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    data = dict()
    data['metrics'] = dict()
    data['charts'] = dict()

    elastics = dict()
    for project in projects:
        elastic = get_elastic_project(project)
        elastics[project.id] = elastic
        # Metrics
        data['metrics'][project.id] = {
            'reviews_open_last_month': activity_reviews.reviews_opened(elastic, urls, one_month_ago, now),
            'reviews_open_last_year': activity_reviews.reviews_opened(elastic, urls, one_year_ago, now),
            'reviews_closed_last_month': activity_reviews.reviews_closed(elastic, urls, one_month_ago, now),
            'reviews_closed_last_year': activity_reviews.reviews_closed(elastic, urls, one_year_ago, now),
            'reviews_open_today': activity_reviews.reviews_open_on(elastic, urls, now),
            'reviews_open_month_ago': activity_reviews.reviews_open_on(elastic, urls, one_month_ago),
            'reviews_open_year_ago': activity_reviews.reviews_open_on(elastic, urls, one_year_ago),
        }

        data['metrics'][project.id]['reviews_open_yoy'] = year_over_year(data['metrics'][project.id]['reviews_open_last_year'],
                                                                 activity_reviews.reviews_opened(elastic, urls, two_year_ago, one_year_ago))

        data['metrics'][project.id]['reviews_closed_yoy'] = year_over_year(data['metrics'][project.id]['reviews_closed_last_year'],
                                                                   activity_reviews.reviews_closed(elastic, urls, two_year_ago, one_year_ago))

    # Visualizations
    data['charts']['reviews_created_bokeh_compare'] = activity_reviews.reviews_created_bokeh_compare(elastics, from_date, to_date)
    data['charts']['reviews_closed_bokeh_compare'] = activity_reviews.reviews_closed_bokeh_compare(elastics, from_date, to_date)

    return data


def compare_community_overview_metrics(projects, urls, from_date, to_date):
    data = dict()
    data['metrics'] = dict()
    data['charts'] = dict()

    elastics = dict()
    for project in projects:
        elastic = get_elastic_project(project)
        elastics[project.id] = elastic
        # Metrics
        data['metrics'][project.id] = {
            'active_people_git': community_commits.authors_active(elastic, urls, from_date, to_date),
            'active_people_issues': community_issues.active_submitters(elastic, urls, from_date, to_date),
            'active_people_patches': community_reviews.active_submitters(elastic, urls, from_date, to_date),
            'onboardings_git': community_commits.authors_entering(elastic, urls, from_date, to_date),
            'onboardings_issues': community_issues.authors_entering(elastic, urls, from_date, to_date),
            'onboardings_patches': community_reviews.authors_entering(elastic, urls, from_date, to_date),
        }

    # Visualizations
    data['charts']['git_authors_bokeh_compare'] = community_commits.git_authors_bokeh_compare(elastics, urls, from_date, to_date)
    data['charts']['issue_submitters_bokeh_compare'] = community_issues.issue_submitters_bokeh_compare(elastics, urls, from_date, to_date)
    data['charts']['review_submitters_bokeh_compare'] = community_reviews.review_submitters_bokeh_compare(elastics, urls, from_date, to_date)

    return data


def get_category_metrics(project, category, urls, from_date, to_date):
    # ['overview',
    # 'activity-overview', 'activity-git', 'activity-issues', 'activity-reviews',
    # 'community-overview', 'community-git', 'community-issues', 'community-reviews']
    elastic = get_elastic_project(project)
    if category == 'overview':
        return overview_metrics(elastic, urls, from_date, to_date)
    elif category == 'activity-overview':
        return activity_overview_metrics(elastic, urls, from_date, to_date)
    elif category == 'activity-git':
        return activity_git_metrics(elastic, urls, from_date, to_date)
    elif category == 'activity-issues':
        return activity_issues_metrics(elastic, urls, from_date, to_date)
    elif category == 'activity-reviews':
        return activity_reviews_metrics(elastic, urls, from_date, to_date)
    elif category == 'activity-qa':
        return activity_qa_metrics(elastic, urls, from_date, to_date)
    elif category == 'community-overview':
        return community_overview_metrics(elastic, urls, from_date, to_date)
    elif category == 'community-git':
        return community_git_metrics(elastic, urls, from_date, to_date)
    elif category == 'community-issues':
        return community_issues_metrics(elastic, urls, from_date, to_date)
    elif category == 'community-reviews':
        return community_reviews_metrics(elastic, urls, from_date, to_date)
    elif category == 'community-qa':
        return community_qa_metrics(elastic, urls, from_date, to_date)
    elif category == 'performance-overview':
        return performance_overview_metrics(elastic, urls, from_date, to_date)
    elif category == 'performance-issues':
        return performance_issues_metrics(elastic, urls, from_date, to_date)
    elif category == 'performance-reviews':
        return performance_reviews_metrics(elastic, urls, from_date, to_date)
    elif category == 'chaoss':
        return chaoss_metrics(elastic, urls, from_date, to_date)
    else:
        return overview_metrics(elastic, urls, from_date, to_date)


def overview_metrics(elastic, urls, from_date, to_date):
    epoch = datetime.datetime.fromtimestamp(0)
    now = datetime.datetime.now()
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Activity metrics
    metrics['commits_overview'] = activity_commits.git_commits(elastic, urls, epoch, now)
    metrics['issues_overview'] = activity_issues.issues_opened(elastic, urls, epoch, now)
    metrics['reviews_overview'] = activity_reviews.reviews_opened(elastic, urls, epoch, now)
    metrics['questions_overview'] = activity_stackexchange.questions(elastic, urls, epoch, now)
    metrics['commits_last_year_overview'] = activity_commits.git_commits(elastic, urls, one_year_ago, now)
    metrics['issues_last_year_overview'] = activity_issues.issues_opened(elastic, urls, one_year_ago, now)
    metrics['reviews_last_year_overview'] = activity_reviews.reviews_opened(elastic, urls, one_year_ago, now)
    metrics['questions_last_year_overview'] = activity_stackexchange.questions(elastic, urls, one_year_ago, now)
    metrics['commits_yoy_overview'] = round(year_over_year(metrics['commits_last_year_overview'],
                                                           activity_commits.git_commits(elastic, urls, two_year_ago, one_year_ago)), 2)
    metrics['issues_yoy_overview'] = round(year_over_year(metrics['issues_last_year_overview'],
                                                          activity_issues.issues_opened(elastic, urls, two_year_ago, one_year_ago)), 2)
    metrics['reviews_yoy_overview'] = round(year_over_year(metrics['reviews_last_year_overview'],
                                                           activity_reviews.reviews_opened(elastic, urls, two_year_ago, one_year_ago)), 2)
    metrics['questions_yoy_overview'] = round(year_over_year(metrics['questions_last_year_overview'],
                                                             activity_stackexchange.questions(elastic, urls, two_year_ago, one_year_ago)), 2)
    # Community metrics
    metrics['commit_authors_overview'] = community_commits.authors_active(elastic, urls, epoch, now)
    metrics['issue_submitters_overview'] = community_issues.active_submitters(elastic, urls, epoch, now)
    metrics['review_submitters_overview'] = community_reviews.active_submitters(elastic, urls, epoch, now)
    metrics['question_authors_overview'] = community_stackexchange.people_asking(elastic, urls, epoch, now)
    metrics['commit_authors_last_year_overview'] = community_commits.authors_active(elastic, urls, one_year_ago, now)
    metrics['issue_submitters_last_year_overview'] = community_issues.active_submitters(elastic, urls, one_year_ago, now)
    metrics['review_submitters_last_year_overview'] = community_reviews.active_submitters(elastic, urls, one_year_ago, now)
    metrics['question_authors_last_year_overview'] = community_stackexchange.people_asking(elastic, urls, one_year_ago, now)
    metrics['commit_authors_yoy_overview'] = round(year_over_year(metrics['commit_authors_last_year_overview'],
                                                                  community_commits.authors_active(elastic, urls, two_year_ago, one_year_ago)), 2)
    metrics['issue_submitters_yoy_overview'] = round(year_over_year(metrics['issue_submitters_last_year_overview'],
                                                                    community_issues.active_submitters(elastic, urls, two_year_ago, one_year_ago)), 2)
    metrics['review_submitters_yoy_overview'] = round(year_over_year(metrics['review_submitters_last_year_overview'],
                                                                     community_reviews.active_submitters(elastic, urls, two_year_ago, one_year_ago)), 2)
    metrics['question_authors_yoy_overview'] = round(year_over_year(metrics['question_authors_last_year_overview'],
                                                                    community_stackexchange.people_asking(elastic, urls, two_year_ago, one_year_ago)), 2)
    # Performance metrics
    metrics['issues_median_time_to_close_overview'] = performance_issues.median_time_to_close(elastic, urls, epoch, now)
    metrics['reviews_median_time_to_close_overview'] = performance_reviews.median_time_to_close(elastic, urls, epoch, now)
    metrics['issues_median_time_to_close_last_year_overview'] = performance_issues.median_time_to_close(elastic, urls, one_year_ago, now)
    metrics['reviews_median_time_to_close_last_year_overview'] = performance_reviews.median_time_to_close(elastic, urls, one_year_ago, now)
    metrics['issues_median_time_to_close_yoy_overview'] = round(year_over_year(metrics['issues_median_time_to_close_last_year_overview'],
                                                                               performance_issues.median_time_to_close(elastic, urls, two_year_ago, one_year_ago)), 2)
    metrics['reviews_median_time_to_close_yoy_overview'] = round(year_over_year(metrics['reviews_median_time_to_close_last_year_overview'],
                                                                                performance_reviews.median_time_to_close(elastic, urls, two_year_ago, one_year_ago)), 2)
    # Visualizations
    metrics['commits_bokeh_overview'] = activity_commits.git_commits_bokeh_line(elastic, urls, from_date, to_date)
    metrics['author_evolution_bokeh'] = other.author_evolution_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_open_closed_bokeh_overview'] = activity_issues.issues_open_closed_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_open_closed_bokeh_overview'] = activity_reviews.reviews_open_closed_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_closed_ttc_overview_bokeh'] = performance_issues.ttc_closed_issues_bokeh(elastic, urls, from_date, to_date)
    metrics['questions_answers_stackexchange_bokeh'] = activity_stackexchange.questions_answers_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_still_open_overview_bokeh'] = performance_issues.issues_still_open_by_creation_date_bokeh(elastic, urls)

    return metrics


def activity_overview_metrics(elastic, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics commits
    metrics['commits_activity_overview'] = activity_commits.git_commits(elastic, urls, from_date, to_date)
    lines_commit = activity_commits.git_lines_commit(elastic, urls, from_date, to_date)
    metrics['lines_commit_activity_overview'] = f"{lines_commit:.2f}"
    try:
        lines_commit_file = lines_commit / activity_commits.git_files_touched(elastic, urls, from_date, to_date)
        metrics['lines_commit_file_activity_overview'] = f"{lines_commit_file:.2f}"
    except ZeroDivisionError:
        metrics['lines_commit_file_activity_overview'] = 0
    # Metrics Issues
    metrics['issues_created_activity_overview'] = activity_issues.issues_opened(elastic, urls, from_date, to_date)
    metrics['issues_closed_activity_overview'] = activity_issues.issues_closed(elastic, urls, from_date, to_date)
    metrics['issues_open_activity_overview'] = activity_issues.issues_open_on(elastic, urls, to_date)
    # Metrics reviews
    metrics['reviews_created_activity_overview'] = activity_reviews.reviews_opened(elastic, urls, from_date, to_date)
    metrics['reviews_closed_activity_overview'] = activity_reviews.reviews_closed(elastic, urls, from_date, to_date)
    metrics['reviews_open_activity_overview'] = activity_reviews.reviews_open_on(elastic, urls, to_date)
    # Visualizations
    metrics['commits_activity_overview_bokeh'] = activity_commits.git_commits_bokeh_line(elastic, urls, from_date, to_date)
    metrics['issues_open_closed_activity_overview_bokeh'] = activity_issues.issues_open_closed_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_open_closed_activity_overview_bokeh'] = activity_reviews.reviews_open_closed_bokeh(elastic, urls, from_date, to_date)
    return metrics


def activity_git_metrics(elastic, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['commits_last_month'] = activity_commits.git_commits(elastic, urls, one_month_ago, now)
    metrics['commits_last_year'] = activity_commits.git_commits(elastic, urls, one_year_ago, now)
    commits_yoy = year_over_year(metrics['commits_last_year'],
                                 activity_commits.git_commits(elastic, urls, two_year_ago, one_year_ago))
    metrics['commits_yoy'] = f"{commits_yoy:+.2f}%"

    lines_commit_last_month = activity_commits.git_lines_commit(elastic, urls, one_month_ago, now)
    metrics['lines_commit_last_month'] = f"{lines_commit_last_month:.2f}"

    lines_commit_last_year = activity_commits.git_lines_commit(elastic, urls, one_year_ago, now)
    metrics['lines_commit_last_year'] = f"{lines_commit_last_year:.2f}"

    lines_commit_yoy = year_over_year(lines_commit_last_year,
                                      activity_commits.git_lines_commit(elastic, urls, two_year_ago, one_year_ago))
    metrics['lines_commit_yoy'] = f"{lines_commit_yoy:+.2f}%"
    try:
        lines_commit_file_last_month = lines_commit_last_month / activity_commits.git_files_touched(elastic, urls, one_month_ago, now)
        metrics['lines_commit_file_last_month'] = f"{lines_commit_file_last_month:.2f}"
    except (ZeroDivisionError, TypeError):
        metrics['lines_commit_file_last_month'] = 0
    try:
        lines_commit_file_last_year = lines_commit_last_year / activity_commits.git_files_touched(elastic, urls, one_year_ago, now)
        metrics['lines_commit_file_last_year'] = f"{lines_commit_file_last_year:.2f}"
    except (ZeroDivisionError, TypeError):
        lines_commit_file_last_year = 0
        metrics['lines_commit_file_last_year'] = 0
    try:
        lines_commit_file_two_year_ago = activity_commits.git_lines_commit(elastic, urls, two_year_ago, one_year_ago) / activity_commits.git_files_touched(elastic, urls, two_year_ago, one_year_ago)
    except (ZeroDivisionError, TypeError):
        lines_commit_file_two_year_ago = 0
    lines_commit_file_yoy = year_over_year(lines_commit_file_last_year,
                                           lines_commit_file_two_year_ago)
    metrics['lines_commit_file_yoy'] = f"{lines_commit_file_yoy:+.2f}%"
    # Visualizations
    metrics['commits_bokeh'] = activity_commits.git_commits_bokeh(elastic, urls, from_date, to_date)
    metrics['commits_lines_changed_bokeh'] = activity_commits.git_lines_changed_bokeh(elastic, urls, from_date, to_date)
    metrics['commits_hour_day_bokeh'] = activity_commits.git_commits_hour_day_bokeh(elastic, urls, from_date, to_date)
    metrics['commits_weekday_bokeh'] = activity_commits.git_commits_weekday_bokeh(elastic, urls, from_date, to_date)
    metrics['commits_heatmap_bokeh'] = activity_commits.git_commits_heatmap_bokeh(elastic, urls, from_date, to_date)
    metrics['commits_by_repository_bokeh'] = activity_commits.commits_by_repository(elastic, from_date, to_date)
    return metrics


def activity_issues_metrics(elastic, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['issues_open_last_month'] = activity_issues.issues_opened(elastic, urls, one_month_ago, now)
    metrics['issues_open_last_year'] = activity_issues.issues_opened(elastic, urls, one_year_ago, now)
    issues_open_yoy = year_over_year(metrics['issues_open_last_year'],
                                     activity_issues.issues_opened(elastic, urls, two_year_ago, one_year_ago))
    metrics['issues_open_yoy'] = f"{issues_open_yoy:+.2f}%"
    metrics['issues_closed_last_month'] = activity_issues.issues_closed(elastic, urls, one_month_ago, now)
    metrics['issues_closed_last_year'] = activity_issues.issues_closed(elastic, urls, one_year_ago, now)
    issues_closed_yoy = year_over_year(metrics['issues_closed_last_year'],
                                       activity_issues.issues_closed(elastic, urls, two_year_ago, one_year_ago))
    metrics['issues_closed_yoy'] = f"{issues_closed_yoy:+.2f}%"
    # Visualizations
    metrics['issues_open_closed_bokeh'] = activity_issues.issues_open_closed_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_open_weekday_bokeh'] = activity_issues.issues_open_weekday_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_closed_weekday_bokeh'] = activity_issues.issues_closed_weekday_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_opened_heatmap_bokeh'] = activity_issues.issues_opened_heatmap_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_closed_heatmap_bokeh'] = activity_issues.issues_closed_heatmap_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_created_by_repository_bokeh'] = activity_issues.issues_created_by_repository(elastic, from_date, to_date)
    metrics['issues_closed_by_repository_bokeh'] = activity_issues.issues_closed_by_repository(elastic, from_date, to_date)
    return metrics


def activity_reviews_metrics(elastic, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_year_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['reviews_open_last_month'] = activity_reviews.reviews_opened(elastic, urls, one_month_ago, now)
    metrics['reviews_open_last_year'] = activity_reviews.reviews_opened(elastic, urls, one_year_ago, now)
    reviews_open_yoy = year_over_year(metrics['reviews_open_last_year'],
                                      activity_reviews.reviews_opened(elastic, urls, two_year_ago, one_year_ago))
    metrics['reviews_open_yoy'] = f"{reviews_open_yoy:+.2f}%"
    metrics['reviews_closed_last_month'] = activity_reviews.reviews_closed(elastic, urls, one_month_ago, now)
    metrics['reviews_closed_last_year'] = activity_reviews.reviews_closed(elastic, urls, one_year_ago, now)
    reviews_closed_yoy = year_over_year(metrics['reviews_closed_last_year'],
                                        activity_reviews.reviews_closed(elastic, urls, two_year_ago, one_year_ago))
    metrics['reviews_closed_yoy'] = f"{reviews_closed_yoy:+.2f}%"
    # Visualizations
    metrics['reviews_open_closed_bokeh'] = activity_reviews.reviews_open_closed_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_open_weekday_bokeh'] = activity_reviews.reviews_open_weekday_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_closed_weekday_bokeh'] = activity_reviews.reviews_closed_weekday_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_opened_heatmap_bokeh'] = activity_reviews.reviews_opened_heatmap_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_closed_heatmap_bokeh'] = activity_reviews.reviews_closed_heatmap_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_created_by_repository_bokeh'] = activity_reviews.reviews_created_by_repository(elastic, from_date, to_date)
    metrics['reviews_closed_by_repository_bokeh'] = activity_reviews.reviews_closed_by_repository(elastic, from_date, to_date)
    return metrics


def activity_qa_metrics(elastic, urls, from_date, to_date):
    metrics = dict()

    # Metrics
    metrics['questions'] = activity_stackexchange.questions(elastic, urls, from_date, to_date)
    metrics['answers'] = activity_stackexchange.answers(elastic, urls, from_date, to_date)

    # Visualizations
    metrics['questions_bokeh'] = activity_stackexchange.questions_bokeh(elastic, urls, from_date, to_date)
    metrics['answers_bokeh'] = activity_stackexchange.answers_bokeh(elastic, urls, from_date, to_date)

    return metrics


def community_overview_metrics(elastic, urls, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_git_community_overview'] = community_commits.authors_active(elastic, urls, from_date, to_date)
    metrics['active_people_issues_community_overview'] = community_issues.active_submitters(elastic, urls, from_date, to_date)
    metrics['active_people_patches_community_overview'] = community_reviews.active_submitters(elastic, urls, from_date, to_date)
    metrics['onboardings_git_community_overview'] = community_commits.authors_entering(elastic, urls, from_date, to_date)
    metrics['onboardings_issues_community_overview'] = community_issues.authors_entering(elastic, urls, from_date, to_date)
    metrics['onboardings_patches_community_overview'] = community_reviews.authors_entering(elastic, urls, from_date, to_date)

    metrics['commits_authors_active_community_overview_bokeh'] = community_commits.authors_active_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_authors_active_community_overview_bokeh'] = community_issues.authors_active_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_authors_active_community_overview_bokeh'] = community_reviews.authors_active_bokeh(elastic, urls, from_date, to_date)
    return metrics


def community_git_metrics(elastic, urls, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_git'] = community_commits.authors_active(elastic, urls, from_date, to_date)
    metrics['onboardings_git'] = community_commits.authors_entering(elastic, urls, from_date, to_date)

    metrics['commits_authors_active_bokeh'] = community_commits.authors_active_bokeh(elastic, urls, from_date, to_date)
    metrics['commits_authors_entering_leaving_bokeh'] = community_commits.authors_entering_leaving_bokeh(elastic, urls, from_date, to_date)
    metrics['organizational_diversity_authors_bokeh'] = community_common.organizational_diversity_authors(elastic, urls, from_date, to_date)
    metrics['organizational_diversity_commits_bokeh'] = community_common.organizational_diversity_commits(elastic, urls, from_date, to_date)
    metrics['commits_authors_aging_bokeh'] = community_commits.authors_aging_bokeh(elastic, urls, to_date)
    metrics['commits_authors_retained_ratio_bokeh'] = community_commits.authors_retained_ratio_bokeh(elastic, urls, to_date)
    return metrics


def community_issues_metrics(elastic, urls, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_issues'] = community_issues.active_submitters(elastic, urls, from_date, to_date)
    metrics['onboardings_issues'] = community_issues.authors_entering(elastic, urls, from_date, to_date)

    metrics['issues_authors_active_bokeh'] = community_issues.authors_active_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_authors_entering_leaving_bokeh'] = community_issues.authors_entering_leaving_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_authors_aging_bokeh'] = community_issues.authors_aging_bokeh(elastic, urls, to_date)
    metrics['issues_authors_retained_ratio_bokeh'] = community_issues.authors_retained_ratio_bokeh(elastic, urls, to_date)
    return metrics


def community_reviews_metrics(elastic, urls, from_date, to_date):
    metrics = dict()
    # Metrics
    metrics['active_people_patches'] = community_reviews.active_submitters(elastic, urls, from_date, to_date)
    metrics['onboardings_patches'] = community_reviews.authors_entering(elastic, urls, from_date, to_date)

    metrics['reviews_authors_active_bokeh'] = community_reviews.authors_active_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_authors_entering_leaving_bokeh'] = community_reviews.authors_entering_leaving_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_authors_aging_bokeh'] = community_reviews.authors_aging_bokeh(elastic, urls, to_date)
    metrics['reviews_authors_retained_ratio_bokeh'] = community_reviews.authors_retained_ratio_bokeh(elastic, urls, to_date)
    return metrics


def community_qa_metrics(elastic, urls, from_date, to_date):
    metrics = dict()

    # Metrics
    metrics['people_asking'] = community_stackexchange.people_asking(elastic, urls, from_date, to_date)
    metrics['people_answering'] = community_stackexchange.people_answering(elastic, urls, from_date, to_date)

    # Visualizations
    metrics['people_asking_bokeh'] = community_stackexchange.people_asking_bokeh(elastic, urls, from_date, to_date)
    metrics['people_answering_bokeh'] = community_stackexchange.people_answering_bokeh(elastic, urls, from_date, to_date)

    return metrics


def performance_overview_metrics(elastic, urls, from_date, to_date):
    now = datetime.datetime.now()

    metrics = dict()
    # Metrics
    metrics['issues_time_open_average_performance_overview'] = performance_issues.average_open_time(elastic, urls, now)
    metrics['issues_time_open_median_performance_overview'] = performance_issues.median_open_time(elastic, urls, now)
    metrics['open_issues_performance_overview'] = performance_issues.open_issues(elastic, urls, now)
    metrics['reviews_time_open_average_performance_overview'] = performance_reviews.average_open_time(elastic, urls, now)
    metrics['reviews_time_open_median_performance_overview'] = performance_reviews.median_open_time(elastic, urls, now)
    metrics['open_reviews_performance_overview'] = performance_reviews.open_reviews(elastic, urls, now)
    # Visualizations
    metrics['issues_created_ttc_performance_overview_bokeh'] = performance_issues.ttc_created_issues_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_closed_ttc_performance_overview_bokeh'] = performance_issues.ttc_closed_issues_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_created_ttc_performance_overview_bokeh'] = performance_reviews.ttc_created_reviews_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_closed_ttc_performance_overview_bokeh'] = performance_reviews.ttc_closed_reviews_bokeh(elastic, urls, from_date, to_date)
    return metrics


def performance_issues_metrics(elastic, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_years_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['issues_time_to_close_median_last_month'] = performance_issues.median_time_to_close(elastic, urls, one_month_ago, now)
    metrics['issues_time_to_close_median_last_year'] = performance_issues.median_time_to_close(elastic, urls, one_year_ago, now)
    median_closing_time_yoy = year_over_year(metrics['issues_time_to_close_median_last_month'],
                                             performance_issues.median_time_to_close(elastic, urls, two_years_ago, now))
    metrics['issues_time_to_close_median_yoy'] = f"{median_closing_time_yoy:+.2f}%"
    metrics['issues_time_open_average'] = performance_issues.average_open_time(elastic, urls, now)
    metrics['issues_time_open_median'] = performance_issues.median_open_time(elastic, urls, now)
    metrics['open_issues'] = performance_issues.open_issues(elastic, urls, now)
    # Visualizations
    metrics['issues_created_ttc_bokeh'] = performance_issues.ttc_created_issues_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_still_open_bokeh'] = performance_issues.issues_still_open_by_creation_date_bokeh(elastic, urls)
    metrics['issues_closed_ttc_bokeh'] = performance_issues.ttc_closed_issues_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_closed_created_ratio_bokeh'] = performance_issues.closed_created_issues_ratio_bokeh(elastic, urls, from_date, to_date)
    return metrics


def performance_reviews_metrics(elastic, urls, from_date, to_date):
    now = datetime.datetime.now()
    one_month_ago = now - relativedelta(months=1)
    one_year_ago = now - relativedelta(years=1)
    two_years_ago = now - relativedelta(years=2)

    metrics = dict()
    # Metrics
    metrics['reviews_time_to_close_median_last_month'] = performance_reviews.median_time_to_close(elastic, urls, one_month_ago, now)
    metrics['reviews_time_to_close_median_last_year'] = performance_reviews.median_time_to_close(elastic, urls, one_year_ago, now)
    median_closing_time_yoy = year_over_year(metrics['reviews_time_to_close_median_last_month'],
                                             performance_reviews.median_time_to_close(elastic, urls, two_years_ago, now))
    metrics['reviews_time_to_close_median_yoy'] = f"{median_closing_time_yoy:+.2f}%"
    metrics['reviews_time_open_average'] = performance_reviews.average_open_time(elastic, urls, now)
    metrics['reviews_time_open_median'] = performance_reviews.median_open_time(elastic, urls, now)
    metrics['open_reviews'] = performance_reviews.open_reviews(elastic, urls, now)
    # Visualizations
    metrics['reviews_created_ttc_bokeh'] = performance_reviews.ttc_created_reviews_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_still_open_bokeh'] = performance_reviews.reviews_still_open_by_creation_date_bokeh(elastic, urls)
    metrics['reviews_closed_ttc_bokeh'] = performance_reviews.ttc_closed_reviews_bokeh(elastic, urls, from_date, to_date)
    metrics['reviews_closed_created_ratio_bokeh'] = performance_reviews.closed_created_reviews_ratio_bokeh(elastic, urls, from_date, to_date)
    return metrics


def chaoss_metrics(elastic, urls, from_date, to_date):
    metrics = dict()
    # Visualizations
    metrics['reviews_closed_mean_duration_heatmap_bokeh_chaoss'] = activity_reviews.reviews_closed_mean_duration_heatmap_bokeh(elastic, urls, from_date, to_date)
    metrics['issues_created_closed_bokeh_chaoss'] = activity_issues.issues_open_closed_bokeh(elastic, urls, from_date, to_date)
    metrics['drive_by_and_repeat_contributor_counts_bokeh_chaoss'] = community_commits.drive_by_and_repeat_contributor_counts(elastic, urls, from_date, to_date)
    metrics['commits_heatmap_bokeh_chaoss'] = activity_commits.git_commits_heatmap_bokeh(elastic, urls, from_date, to_date)
    return metrics
