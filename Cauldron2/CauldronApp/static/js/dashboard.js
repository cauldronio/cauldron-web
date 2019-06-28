var LogsInterval;
var BackendFilter = 'any';
var StatusFilter = 'all';
var TimeoutInfo = null; // To avoid multiple getInfo calls with timeouts
var Dash_ID = window.location.pathname.split('/')[2];

$(document).ready(function(){
    getInfo();
    $('#logModal').on('show.bs.modal', onShowLogsModal);
    $('#logModal').on('hidden.bs.modal', OnHideLogsModal);
    loadLastStatus();
    $('form#gh_add').submit(submitBackend);
    $('form#gl_add').submit(submitBackend);
    $('form#git_add').submit(submitBackend);

    $('.btn-delete').click(deleteRepo);
    $('.btn-reanalyze').click(reanalyzeRepo);

    $('.backend-filters a').click(onFilterClick);
    $('.status-filters a').click(onFilterClick);

    $('#edit-name').click(onClickEditName);
});

function loadLastStatus(){
    if(!LocalStorageAvailable){
        return
    }
    var gh_data = window.localStorage.getItem('gh_data');
    var gl_data = window.localStorage.getItem('gl_data');
    window.localStorage.removeItem('gh_data');
    window.localStorage.removeItem('gl_data');
    $('#gh_data').val(gh_data);
    $('#gl_data').val(gl_data);
    $('#git_data').val('');
}

function onFilterClick(ev) {
    ev.preventDefault();
    $('.backend-item').removeClass('active');
    $(this).addClass('active');
    var filterType = $(this).attr('data-filter-type');
    
    if(filterType == 'status'){
        StatusFilter = $(this).attr('data-filter');
    } else if (filterType == 'backend'){
        BackendFilter = $(this).attr('data-filter');
    }
    filterTable();
}

function filterTable() {
    var num_filtered = 0;
    $('table.repos-table tbody tr').each(function(i, elem){
        var statusOK = (StatusFilter == 'all' || $(elem).attr('data-status') == StatusFilter);
        var backendOK = (BackendFilter == 'any' || $(elem).attr('data-backend') == BackendFilter);
        if ( statusOK && backendOK ){
            $(elem).show();
            num_filtered += 1;
        } else {
            $(elem).hide();
        }
    })
    $('#num-repos-filter').html(num_filtered);
    $('#btn-filter-status').html(`status: ${StatusFilter}`);
    $('#btn-filter-backend').html(`backend: ${BackendFilter}`);
}

function onClickEditName(ev) {
    ev.preventDefault();
    var this_a = $(this)
    var old_name = $('#dash_name').text()
    this_a.hide();

    var name_input = `<form class="input-group mb-3" id="change-name">
                          <input type="text" class="form-control" id="new-name" name="name" placeholder="${old_name}" data-container="body" data-toggle="popover" data-trigger="hover" data-placement="bottom" data-html="true" data-content="Between 4-32 characters allowed. Try to use only: <ul><li>Alphanumeric characters</li><li>Spaces</li><li>Hyphens</li><li>Underscores</li></ul>">
                          <div class="input-group-append">
                            <button class="btn btn-outline-primary" type="submit">Change</button>
                          </div>
                        </form>`
    
    $('#dash_name').html(name_input);
    $('input#new-name').focus();
    $('[data-toggle="popover"]').popover();

    $('form#change-name').submit(function (ev) {
        ev.preventDefault();
        $('input#new-name').popover('dispose')

        var name = $('#new-name').val();
        if (!name){
            showToast('Empty input', 'We are keeping the same name', 'fas fa-check-circle text-success', 5000);
            this_a.show();
            $('#dash_name').text(old_name);
            return
        }
        
        $.post(url = window.location.pathname + "/edit-name",
           data = {'name': name})
        .done(function (data) {
            showToast('Name updated', `${data.message}`, 'fas fa-check-circle text-success', 5000);
            this_a.show();
            $('#dash_name').text(name);
        })
        .fail(function (data) {
            showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', 5000);
            this_a.show();
            $('#dash_name').text(old_name);
        })
    });
}


function deleteRepo(event) {
    var id_repo = event.target.dataset['repo'];
    var backend = $(`tr#repo-${id_repo}`).attr('data-backend');
    var url_repo = $(`tr#repo-${id_repo} td.repo-url`).html();

    var deleteBtn = $(this);
    deleteBtn.html(`<div class="spinner-border text-dark spinner-border-sm" role="status">
                    <span class="sr-only">Loading...</span>
                </div>`);

    $.post(url = window.location.pathname + "/edit", 
           data = {'action': 'delete', 'backend': backend, 'data': url_repo})
        .done(function (data) {
            showToast('Deleted', `The repository <b>${url_repo}</b> was deleted from this dashboard`, 'fas fa-check-circle text-success', 1500);
            $(`tr#repo-${id_repo}`).remove();
            filterTable();
        })
        .fail(function (data) {
            showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', 5000);
        })
        .always(function(){deleteBtn.html('Delete')})
    
}

function reanalyzeRepo(event){
    var id_repo = event.target.dataset['repo'];
    var backend = $(`tr#repo-${id_repo}`).attr('data-backend');
    var url_repo = $(`tr#repo-${id_repo} td.repo-url`).html();

    var reanalyzeRepo = $(this);
    reanalyzeRepo.html(`<div class="spinner-border text-primary spinner-border-sm" role="status">
                            <span class="sr-only">Loading...</span>
                        </div>`);
    $.post(url = window.location.pathname + "/edit",
           data = {'action': 'reanalyze', 'backend': backend, 'data': url_repo})
        .done(function (data) {
            showToast('Reanalyzing', `The repository <b>${url_repo}</b> has restarted`, 'fas fa-check-circle text-success', 1500);
            getInfo();
        })
        .fail(function (data) {
            showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', 5000);
        })
        .always(function(){reanalyzeRepo.html('Restart')})
}

function getInfo() {
    TimeoutInfo = null; // To avoid multiple getInfo calls
    $.getJSON('/dashboard/' + Dash_ID + "/info", function(data) {
        var status_dict = {}
        if (!data || !data.exists){
            return
        }
        data.repos.forEach(function(repo){
            if (!(repo.status.toLowerCase() in status_dict)){
                status_dict[repo.status.toLowerCase()] = 1;
            } else {
                status_dict[repo.status.toLowerCase()]++;
            }
            setIconStatus('#repo-' + repo.id + ' .repo-status', repo.status);
            $('#repo-' + repo.id).attr('data-status', repo.status.toLowerCase());
            if (repo.completed){
                $('#repo-' + repo.id + " .repo-last-update").html(moment(repo.completed).fromNow());
            } else {
                $('#repo-' + repo.id + " .repo-last-update").html("Not completed");
            }
            var duration = get_duration(repo);
            $('#repo-' + repo.id + " .repo-duration").html(duration);

        });
        $('#general-status').html(data.general);
        if ((data.general == 'PENDING' || data.general == 'RUNNING') && !TimeoutInfo) {
            TimeoutInfo = setTimeout(getInfo, 5000, Dash_ID);
        }
        var status_output = ""
        for (var key in status_dict){
            if (status_dict.hasOwnProperty(key)) {
                status_output += `<strong>${key}</strong>: ${status_dict[key]} `;
            }
        }
        $('#general-status').html(status_output)
    }); 
    filterTable();
}

function setIconStatus(jq_selector, status) {
    /**
     * Status could be UNKNOWN, RUNNING, PENDING, COMPLETED OR ERROR
     */
    var icon;
    switch (status) {
        case 'COMPLETED':
            icon = '<i class="fas fa-check text-success"></i>';
            break;
        case 'PENDING':
            icon = '<div class="spinner-grow spinner-grow-sm text-primary" role="status"><span class="sr-only">...</span></div> Pending...';
            break;
        case 'RUNNING':
            icon = '<div class="spinner-border spinner-border-sm text-secondary" role="status"><span class="sr-only">...</span></div> Running...';
            break;
        case 'ERROR':
            icon = '<i class="fas fa-exclamation text-warning"></i> Error.';
            break;
        case 'UNKNOWN':
            icon = '<i class="fas fa-question text-warning"></i>';
            break;
        default:
            break;
    }
    $(jq_selector).html(icon);
}

function get_duration(repo) {
    var output = "";
    if (repo.started){
        var a = moment(repo.started);
        var b = "";
        if (repo.status == 'RUNNING'){
            b = moment();
        } else {
            b = moment(repo.completed);
        }
        output = moment.utc(b.diff(a)).format("HH:mm:ss")
    } else {
        output = "Not started";
    }
    return output
}

function updateBadgesRepos(repo_arr) {
    var repos_gh = 0;
    var repos_gl = 0;
    var repos_git = 0;
    repo_arr.forEach(function(repo){
        if (repo.backend == 'github'){
            repos_gh += 1;
        } else if (repo.backend == 'gitlab'){
            repos_gl += 1;
        } else if (repo.backend == 'git'){
            repos_git += 1;
        }        
    });
    $('.badge-repos-all').html(repos_git + repos_gh + repos_gl)
    $('.badge-repos-gh').html(repos_gh)
    $('.badge-repos-gl').html(repos_gl)
    $('.badge-repos-git').html(repos_git)
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
 *     GITHUB GITLAB GIT SUBMIT    *
 ****************************/
function submitBackend(event) {
    var addBtn = $(`#${event.target.id} button`);
    addBtn.html(`<div class="spinner-border text-dark spinner-border-sm" role="status">
                    <span class="sr-only">Loading...</span>
                </div>`);
    
    $.post(url = window.location.pathname + "/edit", 
           data = $(this).serializeArray())
        .done(function (data) {onDataAdded(data, event.target)})
        .fail(function (data) {onDataFail(data, event.target)})
        .always(function(){addBtn.html('Add')})
    event.preventDefault()
}

function onDataAdded(data, target) {
    //showToast('Success', `Data added correctly. Reloading the list of repositories...`, 'fas fa-spinner text-success', 5000);
    console.log(data);
    //setTimeout(function(){window.location.reload()}, 2000);
    window.location.reload()
}

function onDataFail(data, target) {
    if(!data.hasOwnProperty('responseJSON')){
        showToast('Unknown error from server', `${data.responseText}`, 'fas fa-question-circle text-danger', 5000);
        return;
    }
    if (data.responseJSON.hasOwnProperty('redirect')){
        if(LocalStorageAvailable){
            var input_target = $(`#${target.id} input[name=data]`);
            window.localStorage.setItem('location', window.location.href);
            window.localStorage.setItem(input_target.attr('id'), input_target.val());
        }
        var redirect = `<a href="${data.responseJSON['redirect']}" class="btn btn-primary"> Go</a>`;
        showModalAlert('We can not add it right now...', `<p><b>${data.responseJSON['message']}</b></p>`,  redirect);
    } else {
        showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', 5000);
    }
}
