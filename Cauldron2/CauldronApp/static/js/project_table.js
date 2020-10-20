var LogsInterval;

$(document).ready(function(){
    $('.btn-delete').click(deleteRepo);

    $('.btn-reanalyze').click(reanalyzeRepo);
    $('.btn-reanalyze-all').click(reanalyzeEveryRepo);

    $('.btn-details').click(toggleRepoDetails);
    $('.repo-status-row').on('show.bs.collapse', onShowRepoDetails);

    $('#logModal').on('show.bs.modal', onShowLogsModal);
    $('#logModal').on('hidden.bs.modal', OnHideLogsModal);

    refreshTable();
});


function deleteRepo(event) {
    var button = $(event.currentTarget);
    var id_repo = button.attr('data-repo');
    var backend = $(`tr#repo-${id_repo}`).attr('data-backend');
    var url_repo = $(`tr#repo-${id_repo} td.repo-url`).html();

    var deleteBtn = $(this);
    deleteBtn.html(`<div class="spinner-border spinner-border-sm" role="status">
                    <span class="sr-only">Loading...</span>
                </div>`);

    $.post(url=`/project/${Project_ID}/repositories/remove`,
           data = {'repository': id_repo})
        .done(function (data) {
            showToast('Deleted', `The repository <b>${url_repo}</b> was deleted from this project`, 'fas fa-check-circle text-success', 1500);
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
    var url_repo = $(`tr#repo-${id_repo} td.repo-url`).html();

    var reanalyzeRepo = $(this);
    reanalyzeRepo.html(`<div class="spinner-border spinner-border-sm" role="status">
                            <span class="sr-only">Loading...</span>
                        </div>`);
    $.post(url=`/repository/${id_repo}/refresh`)
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


function refreshTable() {
  var repos_ids = []
  $('#repos-table tbody tr.repo-row').each(function(){
    repos_ids.push($(this).attr('data-repo-id'));
  })

  if(repos_ids.length > 0) {
    var query_string = '?repos_ids='.concat(repos_ids.join('&repos_ids='));

    $.getJSON('/repositories/info' + query_string, function(data) {
        data.forEach(function(repo){
            var jq_id_status = `#repo-${repo.id} .repo-status`;
            var jq_id_last_update = `#repo-${repo.id} .repo-last-update`;
            var last_refresh = moment(repo.last_refresh, 'YYYY-MM-DDTHH:mm:ss:SSSz').fromNow();
            $(jq_id_status).html(repo.status);
            if (last_refresh == 'Invalid date'){
                $(jq_id_last_update).html(repo.last_refresh);
            } else {
                $(jq_id_last_update).html(last_refresh);
            }
        });
    });
    setTimeout(refreshTable, 5000);
  }
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


function toggleRepoDetails(event) {
    var button = $(event.currentTarget);
    var id_repo = button.attr('data-repo');
    $(`#repo-${id_repo}-details`).collapse('toggle');
}

function onShowRepoDetails(event) {
    var id_repo = $(event.currentTarget).attr('data-repo');
    $(`#repo-${id_repo}-intentions`).load(`/repository/${id_repo}/actions`)
}


/****************************
 *     LOGS FUNCTIONS       *
 ****************************/
function onShowLogsModal(event) {
    var button = $(event.relatedTarget);
    var logs_id = button.attr('data-logs-id');
    if (LogsInterval) {
        clearInterval(LogsInterval);
        LogsInterval = null;
    }
    if (logs_id == ''){
        $('#logModal .log-content').html('Logs not found for this action. Could not have started yet.');
    } else {
        LogsInterval = setInterval(updateLogs, 1000, logs_id);
    }
}

function OnHideLogsModal(event) {
    if(LogsInterval){
        clearInterval(LogsInterval);
        LogsInterval = null;
    }
    $('#logModal .log-content ').html('Loading...');
}

function updateLogs(logs_id){
    $.getJSON(`/logs/${logs_id}`, function (data) {
        if (!data){
            $('#logModal .log-content').html('Log not found in this server.');
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
    }).fail(function(){
        if (LogsInterval){
            clearInterval(LogsInterval);
            LogsInterval = null;
        }
    });
}
