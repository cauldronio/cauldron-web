$('#dropdown-datasource a').on('click', function (e) {
    e.preventDefault()
    $(this).tab('show')
    $('#dropdown-datasource a').removeClass('active')
    $(this).addClass('active')
})

$('#projectName').blur(function(e){
    var name = $('#projectName').val();
    $.post(url = "",
           data = {'name': name})
        .fail(function (data) {
            if(!data.hasOwnProperty('responseJSON')){
                showToast('Unknown error from server', `Internal error.`, 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
                console.log(data.responseText);
                return;
            }
            showToast('Failed', `There was a problem: ${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
        })
})