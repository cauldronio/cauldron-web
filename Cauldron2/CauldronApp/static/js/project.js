var BackendFilter = 'any';
var StatusFilter = 'all';
var Project_ID = window.location.pathname.split('/')[2];
var OnGoingActions = {};

$(document).ready(function(){
    $('form#gh_add').submit(submitBackend);
    $('form#gl_add').submit(submitBackend);
    $('form#meetup_add').submit(submitBackend);
    $('form#git_add').submit(submitBackend);

    $('#rename').click(onClickEditName);

    $('form#change-name').on('submit', onSubmitRename);
    $('.btn-reanalyze-all').click(reanalyzeEveryRepo);
    $('#generate-git-csv-link').click(exportGitCSV);

    $('.btn-datasource').click(onSelectDataSource);

    $('.toggle-sidebar').click(toggleSidebar);

    $('.action-delete').click(removeAction);

    $('.btn-delete-repo').click(deleteRepo);

    $('.sidebar-item').hover(showFlyOutMenu);
    $('.sidebar-item').mouseleave(hideFlyOutMenu);

    getSummary();

    getOnGoingActions();
});


function showFlyOutMenu(event) {
    console.log('enter')
    console.log($(event.currentTarget).find('.fly-out-menu').show())
}

function hideFlyOutMenu(event) {
    console.log('leave')
    console.log($(event.currentTarget).find('.fly-out-menu').hide())
}

function removeAction(event) {
    var action_id = $(event.currentTarget).data('action');
    $.post(url=`/project/${Project_ID}/actions/remove`, data={'action_id': action_id})
        .done(function(data) {
            window.location.reload();
        })
        .fail(function(data) {
           showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
        })
}


function onClickEditName(ev) {
    ev.preventDefault();
    var old_name = $('#project-name').text();

    $('#project-name-container').hide();
    $('#change-name').show();

    $('input#new-name').popover();
    $('input#new-name').focus();
    $('input#new-name').val(old_name);
}


function reanalyzeEveryRepo(event){
    $('.reanalyze-all-spinner-dynamic').show();
    $('.reanalyze-all-spinner-static').hide();
    $.post(url =`/project/${Project_ID}/refresh`)
        .done(function (data) {
            if (data['status'] == 'reanalyze'){
                showToast('Reanalyzing', `${data.message}`, 'fas fa-check-circle text-success', 3000);
            } else {
                showToast(data['status'], "The repositories couldn't be refreshed", 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
            }
        })
        .fail(function (data) {
            showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
            $('.reanalyze-all-spinner-dynamic').hide();
            $('.reanalyze-all-spinner-static').show();
        })
}


function getSummary() {
    $.getJSON('/project/' + Project_ID + "/summary", function(data) {
        var status_output = "";
        var i = 0;
        if (data.git){
            status_output += `. <b>Git:</b> ${data.git}`
        }
        if (data.github){
            status_output += `. <b>GitHub:</b> ${data.github}`
        }
        if (data.gitlab){
            status_output += `. <b>GitLab:</b> ${data.gitlab}`
        }
        if (data.gnome){
            status_output += `. <b>Gnome:</b> ${data.gnome}`
        }
        if (data.kde){
            status_output += `. <b>KDE:</b> ${data.kde}`
        }
        if (data.meetup){
            status_output += `. <b>Meetup:</b> ${data.meetup}`
        }
        status_output += `. <b>Running:</b> ${data.running}`
        if (data.running > 0) {
            $('.reanalyze-all-spinner-dynamic').show();
            $('.reanalyze-all-spinner-static').hide();
        } else {
            $('.reanalyze-all-spinner-dynamic').hide();
            $('.reanalyze-all-spinner-static').show();
        }
        $('#num-repos').html(data.total);
        $('#general-status').html(status_output);

        if (data.project_csv) {
            manageCSVStatus(data.project_csv);
        }
        manageRefreshActionsStatus(data.refresh_actions);
    });
    setTimeout(getSummary, 5000, Project_ID);
}


function manageRefreshActionsStatus(running){
    var exists_div = $('.refresh-actions-status').length > 0
    if (running && !exists_div) {
        var div = $('<div/>').addClass("alert alert-info row align-items-center refresh-actions-status");
        div.append('<div class="col-auto"><div class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></div></div>');
        div.append(`<div class="col">Rerunning actions for this project</div>`);
        $('#ongoing-actions').append(div);
    } else if (!running) {
        $('.refresh-actions-status').remove();
    }
}


function manageCSVStatus(csv_data){
    if (csv_data.generating) {
        $('#spinner-git-csv-create').show();
        $('#generate-git-csv-link').addClass('disabled');
        $('#icon-export-csv-btn').hide();
        $('#spinner-export-csv-btn').show();
    } else {
        $('#spinner-git-csv-create').hide();
        $('#generate-git-csv-link').removeClass('disabled');
        $('#icon-export-csv-btn').show();
        $('#spinner-export-csv-btn').hide();
    }
    if (csv_data.download) {
        $('#download-git-csv-link').removeClass('disabled');
        var date_from_now = moment(csv_data.download.date, 'YYYY-MM-DDTHH:mm:ss.SSSZ', true).fromNow();
        $('#download-git-csv-link').html(`Download (created ${date_from_now})`);
        $('#download-git-csv-link').attr('href', csv_data.download.link);
    } else {
        $('#download-git-csv-link').addClass('disabled');
    }
}


function exportGitCSV(){
    $.post(url = `/project/${Project_ID}/create-git-csv`)
        .done(function (data) {
            $('#spinner-git-csv-create').show();
            $('#generate-git-csv-link').addClass('disabled');
            $('#icon-export-csv-btn').hide();
            $('#spinner-export-csv-btn').show();
        })
        .fail(function (data) {onDataFail(data, event.target)})
}


function onSubmitRename(ev) {
    ev.preventDefault();

    $('input#new-name').popover('dispose');

    var url = $(this).attr("action");
    var data = $(this).serialize();
    var name = $('#new-name').val();

    $.post(url=url, data=data)
    .done(function (result) {
        $('#project-name').text(name);

        $('#project-name-container').show();
        $('#change-name').hide();

        showToast('Name updated', `${result.message}`, 'fas fa-check-circle text-success', 5000);
    })
    .fail(function (data) {
        showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
        $('#project-name-container').show();
        $('#change-name').hide();
    })
}


function show_descriptions() {
  var charts_without_description = $('.charts-without-description');
  var charts_with_description = $('.charts-with-description');

  $('#toggle-btn').html($('<i/>',{class:'fa fa-eye-slash'}));
  $('#toggle-btn').removeClass('show-descriptions-btn');
  $('#toggle-btn').addClass('hide-descriptions-btn');
  $('#toggle-btn').attr('data-original-title', 'Hide descriptions');

  charts_without_description.fadeOut();
  charts_with_description.fadeIn();
}


function hide_descriptions() {
  var charts_without_description = $('.charts-without-description');
  var charts_with_description = $('.charts-with-description');

  $('#toggle-btn').html($('<i/>',{class:'fa fa-eye'}));
  $('#toggle-btn').removeClass('hide-descriptions-btn');
  $('#toggle-btn').addClass('show-descriptions-btn');
  $('#toggle-btn').attr('data-original-title', 'Show descriptions');

  charts_with_description.fadeOut();
  charts_without_description.fadeIn();
}


function toggle_descriptions() {
  if ($('#toggle-btn').hasClass('show-descriptions-btn')) {
    show_descriptions();
    eraseCookie('project_metrics_description');
  } else {
    hide_descriptions();
    setCookie('project_metrics_description', 'dismiss', 0);
  }
}


function deleteRepo(event) {
    var button = $(event.currentTarget);
    var id_repo = button.attr('data-repo');
    var backend = $(`tr#repo-${id_repo}`).attr('data-backend');
    var url_repo = $(`tr#repo-${id_repo} td.repo-url`).html();

    var deleteBtn = $(this);
    if (id_repo != 'all'){
        deleteBtn.html(`<div class="spinner-border spinner-border-sm" role="status">
                        <span class="sr-only">Loading...</span>
                    </div>`);
    } else {
        deleteBtn.html(`<span class="icon"><div class="spinner-border spinner-border-sm" role="status"></div></span>
                        <span class="text">Removing...</span>`);
    }

    $.post(url=`/project/${Project_ID}/repositories/remove`,
           data = {'repository': id_repo})
        .done(function (data) {
            if(id_repo == 'all') {
                window.location.reload();
            } else {
                showToast('Removed', `The repository <b>${url_repo}</b> was deleted from this project`, 'fas fa-check-circle text-success', 1500);
                $(`tr#repo-${id_repo}`).remove();
            }
        })
        .fail(function (data) {
            if (data.responseJSON){
                showToast('Failed', `${data.responseJSON['status']}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
            } else {
                showToast('Failed', `500 internal error`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
            }
        })
        .always(function(){
            if (id_repo == 'all'){
                deleteBtn.html(`<span class="icon"><i class="fa fa-trash-alt"></i></span>
                                <span class="text">Remove all</span>`)
            } else {
                deleteBtn.html('Remove')
            }
        })
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

    $.post(url = `/project/${Project_ID}/repositories/add`,
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
 *        GET OWNER ACTIONS        *
 ************************************/
function getOnGoingActions(){
    $.get(url=`/project/${Project_ID}/ongoing-owners`, function(data){
        var currentOngoingLength = Object.keys(OnGoingActions).length;
        if (currentOngoingLength && (!data['owners'] || currentOngoingLength > data['owners'].length) ){
            window.location.reload();
        } else if (!data['owners'] || data['owners'].length == 0){
            return
        } else {
            data['owners'].forEach(function(item, index){
                var key = `${item['backend']}-${item['owner']}`;
                if (!OnGoingActions[key]){
                    OnGoingActions[key] = true;
                    var div = $('<div/>').addClass("alert alert-info row align-items-center");
                    div.append('<div class="col-auto"><div class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></div></div>');
                    div.append(`<div class="col">Adding owner <strong>${item['owner']}</strong> from <strong>${item['backend']}</strong></div>`);
                    $('#ongoing-actions').append(div);
                }
            });
            setTimeout(getOnGoingActions, 3000);
        }
    });
}


/****************************
 *   Collapse sidebar       *
 ****************************/
function toggleSidebar(){
    $('.sidebar-item').unbind('mouseenter mouseleave');
    if ($('#sidebar').hasClass('sidebar-with-text')) {
        $('#sidebar').addClass('sidebar-with-icons').removeClass('sidebar-with-text');
        $('#toggle-sidebar-icon').removeClass('fa-angle-double-left').addClass('fa-angle-double-right');
        $('.sidebar-item').hover(showFlyOutMenu);
        $('.sidebar-item').mouseleave(hideFlyOutMenu);
    } else {
        $('#sidebar').addClass('sidebar-with-text').removeClass('sidebar-with-icons');
        $('#toggle-sidebar-icon').removeClass('fa-angle-double-right').addClass('fa-angle-double-left');
        $('.download-toggle').hover(function(){$('.download-menu').show()});
        $('.download-toggle').mouseleave(function(){$('.download-menu').hide()});
    }
}
