$(document).ready(function(){
    $('form#form-delete-project').on('submit', onSubmitDelete);
    refreshProjects();
});

$('#modal-delete-project').on('show.bs.modal', function (e) {
    var projectId = $(e.relatedTarget).data('project-id');
    var urlDelete = `/dashboard/${projectId}/delete`;
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
  $.post(url =`/dashboard/${project_id}/edit`,
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
    showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', 15000);
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
            $('#project-' + project.id + '-git').html(project.repositories.git);
            $('#project-' + project.id + '-github').html(project.repositories.github);
            $('#project-' + project.id + '-gitlab').html(project.repositories.gitlab);
            $('#project-' + project.id + '-meetup').html(project.repositories.meetup);
            $('#project-' + project.id + '-completed').html(project.status.completed);
            $('#project-' + project.id + '-errors').html(project.status.errors);
            $('#project-' + project.id + '-pending').html(project.status.pending + project.status.running);
            if (project.status.pending + project.status.running > 0) {
                $('#spinner-' + project.id).show();
            } else {
                $('#spinner-' + project.id).hide();
            }
        });
    });
    setTimeout(refreshProjects, 5000);
  }
}
