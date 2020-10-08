var LogsInterval;
var BackendFilter = 'any';
var StatusFilter = 'all';
var Dash_ID = window.location.pathname.split('/')[2];

$(document).ready(function(){
    $('#logModal').on('show.bs.modal', onShowLogsModal);
    $('#logModal').on('hidden.bs.modal', OnHideLogsModal);

    $('form#gh_add').submit(submitBackend);
    $('form#gl_add').submit(submitBackend);
    $('form#meetup_add').submit(submitBackend);
    $('form#git_add').submit(submitBackend);

    $('.btn-delete').click(deleteRepo);
    $('.btn-reanalyze').click(reanalyzeRepo);
    $('.btn-reanalyze-all').click(reanalyzeEveryRepo);

    $('#rename').click(onClickEditName);

    $('form#change-name').on('submit', onSubmitRename);

    $('.btn-datasource').click(onSelectDataSource);

    refreshTable();
    getSummary();
});


function onClickEditName(ev) {
    ev.preventDefault();
    var old_name = $('#dash-name').text();

    $('#dash-name-container').hide();
    $('#change-name').show();

    $('input#new-name').popover();
    $('input#new-name').focus();
    $('input#new-name').val(old_name);
}


function deleteRepo(event) {
    var button = $(event.currentTarget);
    var id_repo = button.attr('data-repo');
    var backend = $(`tr#repo-${id_repo}`).attr('data-backend');
    var url_repo = $(`tr#repo-${id_repo} td.repo-url`).html();

    var deleteBtn = $(this);
    deleteBtn.html(`<div class="spinner-border spinner-border-sm" role="status">
                    <span class="sr-only">Loading...</span>
                </div>`);

    $.post(url = window.location.pathname + "/edit",
           data = {'action': 'delete', 'backend': backend, 'data': id_repo})
        .done(function (data) {
            showToast('Deleted', `The repository <b>${url_repo}</b> was deleted from this dashboard`, 'fas fa-check-circle text-success', 1500);
            $(`tr#repo-${id_repo}`).remove();
        })
        .fail(function (data) {
            showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
        })
        .always(function(){deleteBtn.html('Delete')})

}

function reanalyzeRepo(event){
    var button = $(event.currentTarget);
    var id_repo = button.attr('data-repo');
    var backend = $(`tr#repo-${id_repo}`).attr('data-backend');
    var url_repo = $(`tr#repo-${id_repo} td.repo-url`).html();

    var reanalyzeRepo = $(this);
    reanalyzeRepo.html(`<div class="spinner-border spinner-border-sm" role="status">
                            <span class="sr-only">Loading...</span>
                        </div>`);
    $.post(url = window.location.pathname + "/edit",
           data = {'action': 'reanalyze', 'backend': backend, 'data': id_repo})
        .done(function (data) {
            if (data['status'] == 'reanalyze'){
                showToast('Reanalyzing', `The repository <b>${url_repo}</b> has refreshed`, 'fas fa-check-circle text-success', 1500);
            } else {
                showToast(data['status'],  `The repository <b>${url_repo}</b> can not be refreshed`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
            }
        })
        .fail(function (data) {
            showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
        })
        .always(function(){reanalyzeRepo.html('<i class="fa fa-sync"></i> <small>Refresh</small>')})
}

function reanalyzeEveryRepo(event){
    var id_repo = 'all';
    var backend = 'all';

    $('#reanalyze-all-spinner').html(`<div class="spinner-border spinner-border-sm" role="status">
                                    <span class="sr-only">Loading...</span>
                                </div>`);
    $.post(url = window.location.pathname + "/edit",
           data = {'action': 'reanalyze-all', 'backend': backend, 'data': id_repo})
        .done(function (data) {
            if (data['status'] == 'reanalyze'){
                showToast('Reanalyzing', `${data.message}`, 'fas fa-check-circle text-success', 3000);
            } else {
                showToast(data['status'], "The repositories couldn't be refreshed", 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
            }
        })
        .fail(function (data) {
            showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
            $('#reanalyze-all-spinner').html(`<i class="fa fa-sync"></i>`)
        })
}

function refreshTable() {
  var repos_ids = []
  $('#repos-table tbody tr').each(function(){
    repos_ids.push($(this).attr('data-repo-id'));
  })

  if(repos_ids.length > 0) {
    var query_string = '?repos_ids='.concat(repos_ids.join('&repos_ids='));

    $.getJSON('/repositories/info' + query_string, function(data) {
        data.forEach(function(repo){
            setIconStatus('#repo-' + repo.id + ' .repo-status', repo.status);
            $('#repo-' + repo.id).attr('data-status', repo.status.toLowerCase());
            if (repo.status == 'completed'){
                $('#repo-' + repo.id + " .repo-last-update").html(moment(repo.last_refresh).fromNow());
            } else {
                $('#repo-' + repo.id + " .repo-last-update").html("Not completed");
            }
            var duration = get_duration(repo);
            $('#repo-' + repo.id + " .repo-duration").html(duration);

        });
    });
    setTimeout(refreshTable, 5000);
  }
}

function getSummary() {
    $.getJSON('/dashboard/' + Dash_ID + "/summary", function(data) {
        var status_output = "";
        var i = 0;
        for (var key in data.status){
            status_output += `${key}: ${data.status[key]}`;
            if(i < Object.keys(data.status).length - 1) {
              status_output += ` | `;
            }
            i++;
        }
        if ((data.status['pending'] > 0) | (data.status['running'] > 0)) {
            $('#reanalyze-all-spinner').html(`<div class="spinner-border spinner-border-sm" role="status">
                                    <span class="sr-only">Loading...</span>
                                </div>`);
        } else {
            $('#reanalyze-all-spinner').html(`<i class="fa fa-sync"></i>`)
        }

        $('#num-repos-filter').html(data.total);
        $('#general-status').html(status_output)
    });
    setTimeout(getSummary, 5000, Dash_ID);
}

function onSubmitRename(ev) {
    ev.preventDefault();

    $('input#new-name').popover('dispose');

    var url = $(this).attr("action");
    var data = $(this).serialize();
    var name = $('#new-name').val();

    $.post(url=url, data=data)
    .done(function (result) {
        $('#dash-name').text(name);

        $('#dash-name-container').show();
        $('#change-name').hide();

        showToast('Name updated', `${result.message}`, 'fas fa-check-circle text-success', 5000);
    })
    .fail(function (data) {
        showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
        $('#dash-name-container').show();
        $('#change-name').hide();
    })
}

function setIconStatus(jq_selector, status) {
    /**
     * Status could be completed, running, pending, error or unknown
     */
    var icon;
    switch (status) {
        case 'completed':
            icon = '<i class="fas fa-check text-success"></i>';
            break;
        case 'pending':
            icon = '<div class="spinner-grow spinner-grow-sm text-primary" role="status"><span class="sr-only">...</span></div> Pending...';
            break;
        case 'running':
            icon = '<div class="spinner-border spinner-border-sm text-secondary" role="status"><span class="sr-only">...</span></div> Running...';
            break;
        case 'error':
            icon = '<i class="fas fa-exclamation text-warning"></i> Error.';
            break;
        case 'unknown':
            icon = '<i class="fas fa-question text-warning"></i>';
            break;
        default:
            break;
    }
    $(jq_selector).html(icon);
}

function get_duration(repo) {
    var output = "";
    if (repo.duration > 0){
        if (repo.status == 'pending'){
          return "Waiting token"
        }
        var h = Math.floor(repo.duration / 3600);
        var m = Math.floor(repo.duration / 60) % 60;
        var s = Math.floor(repo.duration) % 60;
        output = `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)}`
    } else {
        output = "Not started";
    }
    return output
}

function pad(num, size) {
    var s = num + "";
    while (s.length < size) s = "0" + s;
    return s;
}

/****************************
 *     LOGS FUNCTIONS       *
 ****************************/
function onShowLogsModal(event) {
    var button = $(event.relatedTarget);
    var id_repo = button.attr('data-repo');
    if (LogsInterval) {
        clearInterval(LogsInterval);
        LogsInterval = null;
    }
    LogsInterval = setInterval(updateLogs, 1000, id_repo);
}

function OnHideLogsModal(event) {
    if(LogsInterval){
        clearInterval(LogsInterval);
        LogsInterval = null;
    }
    $('#logModal .log-content ').html('Loading...');
}

function updateLogs(id_repo){
    $.getJSON('/repo-logs/' + id_repo, function (data) {
        if (!data){
            $('#logModal .log-content').html('Task not found or an error occurred, try to reload the page.');
            if (LogsInterval){
                clearInterval(LogsInterval);
                LogsInterval = null;
            }
            return // NOTHING MORE TO DO
        }
        if (data.content) {
            $('#logModal .log-content ').html('');
            $('#logModal .log-content ').html(data.content);
        }
        if (!data.more) {
            if (LogsInterval){
                clearInterval(LogsInterval);
                LogsInterval = null;
            }
        }
    });
}


/****************************
 *    ADD DATA SOURCES      *
 ****************************/

function onSelectDataSource(event) {
    $('#add-datasource-modal').modal('hide');
}

function submitBackend(event) {
    event.preventDefault()
    var addBtn = $(`#${event.target.id} button`);
    addBtn.html(`<div class="spinner-border spinner-border-sm" role="status">
                    <span class="sr-only">Loading...</span>
                </div>`);

    $.post(url = window.location.pathname + "/edit",
           data = $(this).serializeArray())
        .done(function (data) {onDataAdded(data, event.target)})
        .fail(function (data) {onDataFail(data, event.target)})
        .always(function(){addBtn.html('Add')})
}

function onDataAdded(data, target) {
    $(`#${target.id} input[type=text]`).val('');
    window.location.reload()
}

function onDataFail(data, target) {
    if(!data.hasOwnProperty('responseJSON')){
        showToast('Unknown error from server', `${data.responseText}`, 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
        return;
    }
    if (data.responseJSON.hasOwnProperty('redirect')){
        var redirect = `<a href="${data.responseJSON['redirect']}" class="btn btn-primary">Go</a>`;
        showModalAlert('Do you let us?', `<p class="text-justify">${data.responseJSON['message']}</p>`,  redirect);
    } else {
        showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
    }
}


/***********************************
 *    METRICS AND VISUALIZATIONS   *
 ***********************************/
$(function() {
    var categories = ['overview', 'activity-overview', 'activity-git', 'activity-issues', 'activity-reviews', 'community-overview', 'community-git', 'community-issues', 'community-reviews'];
    var start = getUrlParameter('from_date');
    var end = getUrlParameter('to_date');
    var tab = getUrlParameter('tab');
    start = (typeof start === 'undefined') ? moment().subtract(1, 'year') : moment(start, "YYYY-MM-DD");
    end = (typeof end === 'undefined') ? moment() : moment(end, "YYYY-MM-DD");
    tab = ((typeof tab === 'undefined') | !categories.includes(tab) ) ? 'overview' : tab

    $('#date-picker-input').val(start.format('YYYY-MM-DD') + ' - ' + end.format('YYYY-MM-DD'));

    $(`a[data-category="${tab}"]`).tab('show')

    //"html_id": "key from Django"
    var VIZ_KEYS = {
        'commits_bokeh': "chart-commits",
        'commits_bokeh_overview': "chart-commits-overview",
        'commits_activity_overview_bokeh': "chart-commits-activity-overview",
        'commits_lines_changed_bokeh': "chart-lines-touched",
        'commits_hour_day_bokeh': "chart-commits-hour",
        'commits_weekday_bokeh': "chart-commits-weekday",
        'commits_heatmap_bokeh': "chart-commits-heatmap",
        'issues_open_closed_bokeh': "chart-issues-open-closed",
        'issues_open_weekday_bokeh': "chart-issues-open-weekday",
        'issues_closed_weekday_bokeh': "chart-issues-closed-weekday",
        'issues_opened_heatmap_bokeh': "chart-issues-opened-heatmap",
        'issues_closed_heatmap_bokeh': "chart-issues-closed-heatmap",
        'reviews_open_closed_bokeh': "chart-reviews-open-closed",
        'reviews_open_weekday_bokeh': "chart-reviews-open-weekday",
        'reviews_closed_weekday_bokeh': "chart-reviews-closed-weekday",
        'reviews_opened_heatmap_bokeh': "chart-reviews-opened-heatmap",
        'reviews_closed_heatmap_bokeh': "chart-reviews-closed-heatmap",
        "author_evolution_bokeh": "chart-people-overview",
        "issues_open_closed_bokeh_overview": "chart-issues-overview",
        'issues_open_closed_activity_overview_bokeh': "chart-issues-open-closed-activity-overview",
        "reviews_open_closed_bokeh_overview": "chart-pull-requests-overview",
        'reviews_open_closed_activity_overview_bokeh': "chart-reviews-open-closed-activity-overview",
        "commits_authors_active_bokeh": "chart-authors-git-active",
        "commits_authors_active_community_overview_bokeh": "chart-authors-git-active-community-overview",
        "issues_authors_active_bokeh": "chart-authors-issues-active",
        "issues_authors_active_community_overview_bokeh": "chart-authors-issues-active-community-overview",
        "reviews_authors_active_bokeh": "chart-authors-reviews-active",
        "reviews_authors_active_community_overview_bokeh": "chart-authors-reviews-active-community-overview",
        "commits_authors_entering_leaving_bokeh": "chart-onboarding-leaving-git",
        "issues_authors_entering_leaving_bokeh": "chart-onboarding-leaving-issues",
        "reviews_authors_entering_leaving_bokeh": "chart-onboarding-leaving-reviews",
        "organizational_diversity_authors_bokeh": "chart-organizational-diversity-authors",
        "organizational_diversity_commits_bokeh": "chart-organizational-diversity-commits",
        "commits_authors_aging_bokeh": "chart-authors-aging-git",
        "issues_authors_aging_bokeh": "chart-authors-aging-issues",
        "reviews_authors_aging_bokeh": "chart-authors-aging-reviews",
        "commits_authors_retained_ratio_bokeh": "chart-authors-retained-ratio-git",
        "issues_authors_retained_ratio_bokeh": "chart-authors-retained-ratio-issues",
        "reviews_authors_retained_ratio_bokeh": "chart-authors-retained-ratio-reviews",
        "issues_open_age_bokeh": "chart-issues-open-age",
        "reviews_open_age_bokeh": "chart-reviews-open-age",
    }

    var METRICS_ACTIVITY_OVERVIEW = {
        "commits_activity_overview": "number_commits_activity_overview",
        "lines_commit_activity_overview": "number_lines_commit_activity_overview",
        "lines_commit_file_activity_overview": "number_lines_commit_file_activity_overview",
        "issues_created_activity_overview": "number_issues_created_activity_overview",
        "issues_closed_activity_overview": "number_issues_closed_activity_overview",
        "issues_open_activity_overview": "number_issues_open_activity_overview",
        "reviews_created_activity_overview": "number_reviews_created_activity_overview",
        "reviews_closed_activity_overview": "number_reviews_closed_activity_overview",
        "reviews_open_activity_overview": "number_reviews_open_activity_overview",
    }

    var METRICS_ACTIVITY_GIT = {
        "commits_last_month": "number_commits_last_month",
        "commits_last_year": "number_commits_last_year",
        "commits_yoy": "number_commits_yoy",
        "lines_commit_last_month": "number_lines_commit_last_month",
        "lines_commit_last_year": "number_lines_commit_last_year",
        "lines_commit_yoy": "number_lines_commit_yoy",
        "lines_commit_file_last_month": "number_lines_commit_file_last_month",
        "lines_commit_file_last_year": "number_lines_commit_file_last_year",
        "lines_commit_file_yoy": "number_lines_commit_file_yoy",
    }

    var METRICS_ACTIVITY_ISSUES = {
        "issues_open_last_month": "number_issues_open_last_month",
        "issues_open_last_year": "number_issues_open_last_year",
        "issues_open_yoy": "number_issues_open_yoy",
        "issues_closed_last_month": "number_issues_closed_last_month",
        "issues_closed_last_year": "number_issues_closed_last_year",
        "issues_closed_yoy": "number_issues_closed_yoy",
        "issues_open_today": "number_issues_open_today",
        "issues_open_month_ago": "number_issues_open_month_ago",
        "issues_open_year_ago": "number_issues_open_year_ago",
    }

    var METRICS_ACTIVITY_REVIEWS = {
        "reviews_open_last_month": "number_reviews_open_last_month",
        "reviews_open_last_year": "number_reviews_open_last_year",
        "reviews_open_yoy": "number_reviews_open_yoy",
        "reviews_closed_last_month": "number_reviews_closed_last_month",
        "reviews_closed_last_year": "number_reviews_closed_last_year",
        "reviews_closed_yoy": "number_reviews_closed_yoy",
        "reviews_open_today": "number_reviews_open_today",
        "reviews_open_month_ago": "number_reviews_open_month_ago",
        "reviews_open_year_ago": "number_reviews_open_year_ago",
    }

    var METRICS_COMMUNITY_OVERVIEW = {
      "active_people_git_community_overview": "active_people_git_community_overview",
      "active_people_issues_community_overview": "active_people_issues_community_overview",
      "active_people_patches_community_overview": "active_people_patches_community_overview",
      "onboardings_git_community_overview": "onboardings_git_community_overview",
      "onboardings_issues_community_overview": "onboardings_issues_community_overview",
      "onboardings_patches_community_overview": "onboardings_patches_community_overview",
    }

    var METRICS_COMMUNITY_GIT = {
        "active_people_git": "active_people_git",
        "onboardings_git": "onboardings_git",
    }

    var METRICS_COMMUNITY_ISSUES = {
        "active_people_issues": "active_people_issues",
        "onboardings_issues": "onboardings_issues",
    }

    var METRICS_COMMUNITY_REVIEWS = {
        "active_people_patches": "active_people_patches",
        "onboardings_patches": "onboardings_patches",
    }

    var METRICS_KEYS = {
        "commits_range": "number_commits_range",
        "reviews_opened": "number_reviews_opened",
        "review_duration": "number_review_duration",
        "issues_created_range": "number_issues_created_range",
        "issues_closed_range": "number_issues_closed_range",
        "issues_time_to_close": "number_issues_time_to_close",
        "issues_time_to_close": "number_issues_time_to_close",
    }

    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_ACTIVITY_OVERVIEW);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_ACTIVITY_GIT);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_ACTIVITY_ISSUES);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_ACTIVITY_REVIEWS);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_COMMUNITY_OVERVIEW);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_COMMUNITY_GIT);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_COMMUNITY_ISSUES);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_COMMUNITY_REVIEWS);


    function updateMetricsData() {
        $.getJSON(`${window.location.pathname}/metrics`,
        {"from": start.format('YYYY-MM-DD'), "to": end.format('YYYY-MM-DD'), "tab": tab},
        function(data){
            for (k in data){
                if (k in METRICS_KEYS){
                    var id_html = `#${METRICS_KEYS[k]}`;
                    $(id_html).html(data[k]);
                }
                if (k in VIZ_KEYS){
                    var id_html = `#${VIZ_KEYS[k]}`;
                    var item = JSON.parse(data[k]);
                    $(id_html).empty();
                    Bokeh.embed.embed_item(item, VIZ_KEYS[k]);
                }
            }
        });
    }

    function cb(new_start, new_end) {
        start = new_start;
        end = new_end;
        var start_str = start.format('YYYY-MM-DD');
        var end_str = end.format('YYYY-MM-DD');
        $('#date-picker-input').val(start.format('YYYY-MM-DD') + ' - ' + end.format('YYYY-MM-DD'));
        window.history.replaceState({'start': start_str, 'end': end_str}, 'date', `?from_date=${start_str}&to_date=${end_str}&tab=${tab}`)
        updateMetricsData();
    }

    $('#date-picker').daterangepicker({
        startDate: start,
        endDate: end,
        maxDate: moment(),
        opens: 'left',
        ranges: {
           'Last 30 Days': [moment().subtract(29, 'days'), moment()],
           'Last 6 months': [moment().subtract(6, 'months'), moment()],
           'Last Year': [moment().subtract(1, 'year'), moment()],
           'Last 3 Years': [moment().subtract(3, 'years'), moment()],
           'All (20 years)': [moment().subtract(20, 'years'), moment()]
        },
        showCustomRangeLabel: false
    }, cb);

    $('#date-picker-input').daterangepicker({
        startDate: start,
        endDate: end,
        maxDate: moment(),
        opens: 'left',
        locale: {
            format: 'YYYY-MM-DD'
        }
    }, cb);

    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        tab = e.target.dataset.category;
        var start_str = start.format('YYYY-MM-DD');
        var end_str = end.format('YYYY-MM-DD');
        window.history.replaceState({'start': start_str, 'end': end_str}, 'date', `?from_date=${start_str}&to_date=${end_str}&tab=${tab}`)
        updateMetricsData();
    });
});
