$('#modal-delete-project').on('show.bs.modal', function (e) {
    var projectId = $(e.relatedTarget).data('project-id');
    var urlDelete = `/dashboard/${projectId}/delete`;
    $('#form-delete-project').attr('action', urlDelete);
})

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
      showToast(data['status'], "The data sources couldn't be refreshed", 'fas fa-times-circle text-danger', 3000);
    }
  })
  .fail(function (data) {
    showToast('Failed', `${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', 5000);
  })
  .always(function(){
    $(button).html(old_html)
  })
}