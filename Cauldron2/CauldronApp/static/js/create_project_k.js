$(document).ready(function(){
    if (OpenTab){
        $(`#link-tab-${OpenTab}`).tab('show');
    }
    $('#projectName').blur(validate_name);
    if ($('#projectName').val()){
        validate_name();
    }
    validate_form();
    if (typeof OpenSPDX !== 'undefined') {
        fetch_spdx_results(OpenSPDX);
    }
    $('#spdx_select_all').change(function(){
        var checks = $('#spdx-table').find(':checkbox:enabled:not(#spdx_select_all)');
        checks.trigger('change');
        checks.prop('checked', $(this).is(':checked'));
    });
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
    if ($('#projectName').hasClass('is-valid') && ($('#actionsList li').length || $('#spdx-table').find(':checkbox:checked').length)){
        $('.createProjectBtn').prop('disabled', false)
    } else {
        $('.createProjectBtn').prop('disabled', true)
    }
}

function fetch_spdx_results(spdx_id){
    $.get(url=`/spdx/results/${spdx_id}`)
        .done(function(data) {
            if (data['status'] === 'parsing'){
                $('#spdx-load-spinner').show();
                setTimeout(fetch_spdx_results, 1000, spdx_id);
            } else if (data['results']) {
                $('#spdx-load-spinner').hide();
                $('#spdx-table').show();
                for(var i=0; i<data['results'].length; i++){
                    var item = data['results'][i]
                    var repository = item['repository'] ? item['repository'] : '?'
                    var datasource = item['datasource'] ? item['datasource'] : '?'
                    var disabled = item['repository'] ? '' : 'disabled'
                    $('#spdx-table tbody:last-child').append(`<tr>
                                                                <td><input type="checkbox" name="repository" value="${repository}" ${disabled}></td>
                                                                <td>${item['PackageName']}</td>
                                                                <td>${repository}</td>
                                                                <td class="row-datasource">${datasource}</td>
                                                              </tr>`);
                }
                $(':checkbox:enabled').change(function(event){
                    var jq_target = $(event.target);
                    if (!jq_target.is(':checked')) {
                        var datasource_row = jq_target.closest('tr').children('.row-datasource').html()
                        if (datasource_row == 'github' && document.getElementById('modal-github-need')) {
                            $('#modal-github-need').modal('show');
                            jq_target.prop('checked', false);
                        } else if (datasource_row == 'gitlab' && document.getElementById('modal-gitlab-need')) {
                            $('#modal-gitlab-need').modal('show');
                            jq_target.prop('checked', false);
                        }
                    }
                    validate_form();
                })
            } else if (data['error']) {
                $('#spdx-load-spinner').hide();
                showToast('Error parsing data', data['error'], 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
            }
        })
        .fail(function(data){
            if(!data.hasOwnProperty('responseJSON')){
                showToast('Unknown error from server', `Internal error.`, 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
                console.log(data.responseText);
            } else {
                showToast('Error from server', data['error'], 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
                console.log(data.responseText);
            }
        })
}


