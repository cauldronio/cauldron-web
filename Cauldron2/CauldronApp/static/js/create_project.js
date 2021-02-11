$(document).ready(function(){
    if (OpenTab){
        $(`#link-tab-${OpenTab}`).tab('show');
    }
    $('#projectName').blur(validate_name);
    if ($('#projectName').val()){
        validate_name();
    }
    validate_form();
})

$('#dropdown-datasource a').on('click', function (e) {
    e.preventDefault()
    $(this).tab('show')
    $('#dropdown-datasource a').removeClass('active')
    $(this).addClass('active')
})

function validate_name(){
    var name = $('#projectName').val();
    $.post(url = "",
           data = {'name': name})
        .done(function(data) {
            if (data['status'] == 'error') {
                $('#projectNameHelper').html(data['message']);
                $('#projectName').removeClass('is-valid');
                $('#projectName').addClass('is-invalid');
                $('.createProjectBtn').prop('disabled', true)
            } else {
                $('#projectName').removeClass('is-invalid');
                $('#projectName').addClass('is-valid');
                validate_form();
            }
        })
        .fail(function (data) {
            if(!data.hasOwnProperty('responseJSON')){
                showToast('Unknown error from server', `Internal error.`, 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
                console.log(data.responseText);
                return;
            }
        })
}

function validate_form(){
    if ($('#projectName').hasClass('is-valid') && $('#actionsList li').length){
        $('.createProjectBtn').prop('disabled', false)
    } else {
        $('.createProjectBtn').prop('disabled', true)
    }
}
