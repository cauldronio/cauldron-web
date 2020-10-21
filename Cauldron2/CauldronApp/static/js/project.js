var BackendFilter = 'any';
var StatusFilter = 'all';
var Project_ID = window.location.pathname.split('/')[2];

$(document).ready(function(){
    $('form#gh_add').submit(submitBackend);
    $('form#gl_add').submit(submitBackend);
    $('form#meetup_add').submit(submitBackend);
    $('form#git_add').submit(submitBackend);

    $('#rename').click(onClickEditName);

    $('form#change-name').on('submit', onSubmitRename);
    $('.btn-reanalyze-all').click(reanalyzeEveryRepo);

    $('.btn-datasource').click(onSelectDataSource);

    getSummary();
});


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
    $('#reanalyze-all-spinner-dynamic').show();
    $('#reanalyze-all-spinner-static').hide();
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
            $('#reanalyze-all-spinner').html(`<i class="fa fa-sync"></i>`)
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
        if (data.meetup){
            status_output += `. <b>Meetup:</b> ${data.meetup}`
        }
        status_output += `. <b>Running:</b> ${data.running}`
        if (data.running > 0) {
            $('#reanalyze-all-spinner-dynamic').show();
            $('#reanalyze-all-spinner-static').hide();
        } else {
            $('#reanalyze-all-spinner-dynamic').hide();
            $('#reanalyze-all-spinner-static').show();
        }
        $('#num-repos').html(data.total);
        $('#general-status').html(status_output)
    });
    setTimeout(getSummary, 5000, Project_ID);
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
