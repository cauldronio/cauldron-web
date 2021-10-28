$(document).ready(function(){
    $('form#form-delete-project').on('submit', onSubmitDelete);
    $('a[name=generate-commits-reports]').on('click', generateCommitsReports);
    refreshProjects();
    getReportsExportStatus();
});

$('#modal-delete-project').on('show.bs.modal', function (e) {
    var projectId = $(e.relatedTarget).data('project-id');
    var urlDelete = `/project/${projectId}/delete`;
    $('#form-delete-project').attr('action', urlDelete);
})

function onSubmitDelete(ev) {
    ev.preventDefault();

    var url = $(this).attr("action")
    $.post(url=url)
    .done(function (result) {
        location.reload();
    })
    .fail(function (data) {
        showToast('Failed', `Deletion operation failed`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
    })
}

function refreshProjectDatasources(button, project_id) {
  var old_html = $(button).html();
  $(button).html(`<div class="spinner-border spinner-border-sm" role="status">
                <span class="sr-only">Loading...</span>
                </div>`);
  $.post(url =`/project/${project_id}/refresh`,
    data = {'action': 'reanalyze-all', 'backend': 'all', 'data': 'all'}
  )
  .done(function (data) {
    if (data['status'] == 'reanalyze'){
      showToast('Reanalyzing', `${data.message}`, 'fas fa-check-circle text-success', 3000);
    } else {
      showToast(data['status'], "The repositories couldn't be refreshed", 'fas fa-times-circle text-danger', 10000);
    }
  })
  .fail(function (data) {
    if (data.responseJSON.hasOwnProperty('redirect')){
        var redirect = `<a href="${data.responseJSON['redirect']}" class="btn btn-primary">Go</a>`;
        showModalAlert('We need a token for refreshing', `<p class="text-justify">${data.responseJSON['message']}</p>`,  redirect);
    } else {
        showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
    }
  })
  .always(function(){
    $(button).html(old_html)
  })
}

function refreshProjects() {
  var projects_ids = []
  $('#projects-cards > div').each(function(){
    projects_ids.push($(this).attr('data-project-id'));
  })

  if(projects_ids.length > 0) {
    var query_string = '?projects_ids='.concat(projects_ids.join('&projects_ids='));

    $.getJSON('/projects/info' + query_string, function(data) {
        data.forEach(function(project){
            $('#project-' + project.id + '-git').html(project.git);
            $('#project-' + project.id + '-github').html(project.github);
            $('#project-' + project.id + '-gitlab').html(project.gitlab);
            $('#project-' + project.id + '-gnome').html(project.gnome);
            $('#project-' + project.id + '-kde').html(project.kde);
            $('#project-' + project.id + '-meetup').html(project.meetup);
            $('#project-' + project.id + '-stack').html(project.stackexchange);
            if (project.running > 0) {
                $('#spinner-' + project.id).show();
                $('#spinner-' + project.id).attr('data-original-title', `Analyzing ${project.running} repositories.`);
            } else {
                $('#spinner-' + project.id).hide();
                $('#spinner-' + project.id).attr('data-original-title', `Analyzing 0 repositories.`);
            }
        });
    });
    setTimeout(refreshProjects, 5000);
  }
}


function generateCommitsReports(event) {
    event.preventDefault();
    $.post(url =`/projects/commits-by-month`)
    .done(function (data) {
        $(`#dropdown-generate .generate-spinner`).show();
        $(`#dropdown-generate .generate-icon`).hide();
        setTimeout(getReportsExportStatus, 3000);
    })
    .fail(function (data) {
        if(!data.hasOwnProperty('responseJSON')){
            showToast('Unknown error from server', `Internal error.`, 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
            return;
        }
        showToast('Failed', `There was a problem: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
    })
}

function getReportsExportStatus() {
    $.getJSON(`/projects/commits-by-month`)
    .done(function(data) {
        if (data['status'] == 'running') {
            $("#dropdown-generate .generate-spinner").show();
            $("#dropdown-generate .generate-icon").hide();
            $("#dropdown-generate .commits-progress").html(`(${data['progress']})`)
            setTimeout(getReportsExportStatus, 3000);
        } else if (data['status'] == 'completed') {
            $("#dropdown-generate .commits-progress").html('');
            $('a[name=download-commits-reports]').removeClass('disabled');
            $('a[name=download-commits-reports]').attr('href', data['location']);
            var created = moment(data['last-updated'], 'YYYY-MM-DDTHH:mm:ss.SSSZ', true).from(moment.utc());
            $('a[name=download-commits-reports] span.last-updated').html(`(${created})`);
            $("#dropdown-generate .generate-spinner").hide();
            $("#dropdown-generate .generate-icon").show();
        }
    })
}
