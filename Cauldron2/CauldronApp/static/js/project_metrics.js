/***********************************
 *    METRICS AND VISUALIZATIONS   *
 ***********************************/
$(function() {
    var categories = ['overview', 'activity-overview', 'activity-git', 'activity-issues', 'activity-reviews', 'community-overview', 'community-git', 'community-issues', 'community-reviews', 'performance-overview', 'performance-issues', 'performance-reviews'];
    var start = getUrlParameter('from_date');
    var end = getUrlParameter('to_date');
    var urls = getURLParameterList('repo_url');
    var tab = getUrlParameter('tab');
    start = (typeof start === 'undefined') ? moment().subtract(1, 'year') : moment(start, "YYYY-MM-DD");
    end = (typeof end === 'undefined') ? moment() : moment(end, "YYYY-MM-DD");
    tab = ((typeof tab === 'undefined') | !categories.includes(tab) ) ? 'overview' : tab;

    $('#date-picker-input').val(start.format('YYYY-MM-DD') + ' - ' + end.format('YYYY-MM-DD'));

    $(`a[data-category="${tab}"]`).tab('show')

    $('select[name=repo_url]').val(urls);
    $('.selectpicker').selectpicker('refresh');

    $('select').on('hidden.bs.select', function() {
        $('select option:selected').prependTo('select');
        $(this).selectpicker('refresh');
    });

    updateSelectForm();

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
        "issues_created_ttc_performance_overview_bokeh": "chart-issues-created-ttc-performance-overview",
        "issues_closed_ttc_performance_overview_bokeh": "chart-issues-closed-ttc-performance-overview",
        "reviews_created_ttc_performance_overview_bokeh": "chart-reviews-created-ttc-performance-overview",
        "reviews_closed_ttc_performance_overview_bokeh": "chart-reviews-closed-ttc-performance-overview",
        "issues_created_ttc_bokeh": "chart-issues-created-ttc",
        "issues_still_open_bokeh": "chart-issues-still-open",
        "issues_closed_ttc_bokeh": "chart-issues-closed-ttc",
        "issues_closed_created_ratio_bokeh": "chart-issues-closed-created-ratio",
        "reviews_created_ttc_bokeh": "chart-reviews-created-ttc",
        "reviews_still_open_bokeh": "chart-reviews-still-open",
        "reviews_closed_ttc_bokeh": "chart-reviews-closed-ttc",
        "reviews_closed_created_ratio_bokeh": "chart-reviews-closed-created-ratio",
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
    }

    var METRICS_ACTIVITY_REVIEWS = {
        "reviews_open_last_month": "number_reviews_open_last_month",
        "reviews_open_last_year": "number_reviews_open_last_year",
        "reviews_open_yoy": "number_reviews_open_yoy",
        "reviews_closed_last_month": "number_reviews_closed_last_month",
        "reviews_closed_last_year": "number_reviews_closed_last_year",
        "reviews_closed_yoy": "number_reviews_closed_yoy",
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

    var METRICS_PERFORMANCE_OVERVIEW = {
        "issues_time_open_average_performance_overview": "issues_time_open_average_performance_overview",
        "issues_time_open_median_performance_overview": "issues_time_open_median_performance_overview",
        "open_issues_performance_overview": "open_issues_performance_overview",
        "reviews_time_open_average_performance_overview": "reviews_time_open_average_performance_overview",
        "reviews_time_open_median_performance_overview": "reviews_time_open_median_performance_overview",
        "open_reviews_performance_overview": "open_reviews_performance_overview",
    }

    var METRICS_PERFORMANCE_ISSUES = {
        "issues_time_to_close_median_last_month": "issues_time_to_close_median_last_month",
        "issues_time_to_close_median_last_year": "issues_time_to_close_median_last_year",
        "issues_time_to_close_median_yoy": "issues_time_to_close_median_yoy",
        "issues_time_open_average": "issues_time_open_average",
        "issues_time_open_median": "issues_time_open_median",
        "open_issues": "open_issues",
    }

    var METRICS_PERFORMANCE_REVIEWS = {
        "reviews_time_to_close_median_last_month": "reviews_time_to_close_median_last_month",
        "reviews_time_to_close_median_last_year": "reviews_time_to_close_median_last_year",
        "reviews_time_to_close_median_yoy": "reviews_time_to_close_median_yoy",
        "reviews_time_open_average": "reviews_time_open_average",
        "reviews_time_open_median": "reviews_time_open_median",
        "open_reviews": "open_reviews",
    }

    var METRICS_KEYS = {
        "commits_range": "number_commits_range",
        "reviews_opened": "number_reviews_opened",
        "review_duration": "number_review_duration",
        "issues_created_range": "number_issues_created_range",
        "issues_closed_range": "number_issues_closed_range",
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
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_PERFORMANCE_OVERVIEW);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_PERFORMANCE_ISSUES);
    METRICS_KEYS = Object.assign({}, METRICS_KEYS, METRICS_PERFORMANCE_REVIEWS);


    function updateSelectForm() {
        $('#repository-select-from-date').val(start.format('YYYY-MM-DD'));
        $('#repository-select-to-date').val(end.format('YYYY-MM-DD'));
        $('#repository-select-tab').val(tab);

        $('select option:selected').prependTo('select');
        $('select').selectpicker('refresh');
    }


    function updateMetricsData() {
        $.getJSON(`${window.location.pathname}/metrics`,
        {"from": start.format('YYYY-MM-DD'), "to": end.format('YYYY-MM-DD'), "tab": tab, "repo_url": urls, "repo_url": urls},
        function(data){
            for (k in data){
                if (k in METRICS_KEYS){
                    if (!document.getElementById(METRICS_KEYS[k])){
                        continue;
                    }
                    var id_html = `#${METRICS_KEYS[k]}`;
                    $(id_html).html(data[k]);
                }
                if (k in VIZ_KEYS){
                    if (!document.getElementById(VIZ_KEYS[k])){
                        continue;
                    }
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
        var payload = `?from_date=${start_str}&to_date=${end_str}&tab=${tab}`
        for (var i = 0; i < urls.length; i++) {
          payload += `&repo_url=${urls[i]}`
        }
        $('#date-picker-input').val(start.format('YYYY-MM-DD') + ' - ' + end.format('YYYY-MM-DD'));
        window.history.replaceState({'start': start_str, 'end': end_str}, 'date', payload);
        updateSelectForm();
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
        var payload = `?from_date=${start_str}&to_date=${end_str}&tab=${tab}`
        for (var i = 0; i < urls.length; i++) {
          payload += `&repo_url=${urls[i]}`
        }
        window.history.replaceState({'start': start_str, 'end': end_str}, 'date', payload);
        updateSelectForm();
        updateMetricsData();
    });
});
