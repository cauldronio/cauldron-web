LocalStorageAvailable = false;

$(document).ready(function () {
    // Configure ajax for using the CSRF token
    var csrftoken = getCookie('csrftoken');
    $.ajaxSetup({
        beforeSend: function (xhr, settings) {
            if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRFToken", csrftoken);
            }
        }
    });
    LocalStorageAvailable = checkLocalStorage()

    $('#delete-gh-token').click(function(ev){
        showModalAlert('Do you want to delete your GitHub token?',
                       'We will delete your personal Token from our server. If you delete it, all the pending tasks for that token will be stopped.',
                       `<button type="button" class="btn btn-secondary" data-dismiss="modal" aria-label="Close">No</button>
                        <button type="button" class="btn btn-danger" onclick="deleteToken('github')" data-dismiss="modal">Yes</button>`
        )
        ev.preventDefault();
    });
    $('#delete-gl-token').click(function(ev){
        showModalAlert('Do you want to delete your Gitlab token?',
                       'We will delete your personal Token from our server. If you delete it, all the pending tasks for that token will be stopped.',
                       `<button type="button" class="btn btn-secondary" data-dismiss="modal" aria-label="Close">No</button>
                        <button type="button" class="btn btn-danger" onclick="deleteToken('gitlab')" data-dismiss="modal">Yes</button>`
        )
        ev.preventDefault();
    });
    $('#delete-meetup-token').click(function(ev){
        showModalAlert('Do you want to delete your Meetup token?',
                       'We will delete your personal Token from our server. If you delete it, all the pending tasks for that token will be stopped.',
                       `<button type="button" class="btn btn-secondary" data-dismiss="modal" aria-label="Close">No</button>
                        <button type="button" class="btn btn-danger" onclick="deleteToken('meetup')" data-dismiss="modal">Yes</button>`
        )
        ev.preventDefault();
    });

    $('form.create-dashboard').on('submit', on_create_dashboard);

    $('[data-toggle="tooltip"]').tooltip();

    $('.copy-share-link-kibana').click(copy_kibana_public_link);
});


/**
 * Check if LocalStorage works in this browser
 */
function checkLocalStorage() {
    try {
        localStorage.setItem('test', 'test');
        localStorage.removeItem('test');
        return true;
    } catch (e) {
        return false;
    }
}

/**
 *   Django function to adquire a cookie
 */
function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}


/**
 * Check if the method is safe. These methods don't require CSRF protection
 */
function csrfSafeMethod(method) {
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}


/**
 * Show an alert in the top of the page
 * Possible options for style: primary, secondary, success, danger, warning, info, light and dark
 * Styles: https://getbootstrap.com/docs/4.0/components/alerts/
 */
function showAlert(title, message, style) {
    $('#alert-container').hide();
    var alertMessage = `<div class="alert alert-${style}" role="alert">
                            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                                <span aria-hidden="true">&times;</span>
                            </button>
                            <h4 class="alert-heading">${title}</h4>
                            <p>${message}</p>
                        </div>`
    $('#alert-container').html(alertMessage);
    $('#alert-container').show();
}


/**
 * Show a toast with a message
 */
function showToast(title, message, icon_class, time) {
    var toastID = "toast-" + Date.now();
    var toastDiv = `<div class="toast" role="alert" aria-live="assertive" aria-atomic="true" id="${toastID}" data-delay="${time}">
                        <div class="toast-header">
                            <h5 class="mr-auto"><i class="${icon_class}"></i> ${title}</h5>
                            <button type="button" class="ml-2 mb-1 close" data-dismiss="toast" aria-label="Close">
                                <span aria-hidden="true">&times;</span>
                            </button>
                        </div>
                        <div class="toast-body">
                            ${message}
                        </div>
                    </div>`
    $('#toast-container').append(toastDiv);
    $('#' + toastID).toast('show');
    $('#' + toastID).on('hidden.bs.toast', function () {
        $('#' + toastID).remove();
    })
}

/**
 * Show a modal with the title and the message passed
 */
function showModalAlert(title, message, footer) {
    $('#modal-alert').modal('hide');
    $('#modal-alert h5').html(title);
    $('#modal-alert p').html(message);
    $('#modal-alert').modal('show');
    if (footer != undefined){
        $('#modal-alert .modal-footer').html(footer);
    }
}


/**
 * Delete the token of the user for the defined backend
 */
function deleteToken(identity) {
    $.post(url = "/delete-token",
           data = {'identity': identity})
        .done(function (data) {
            showToast('Deleted', `Your <b>${identity} token</b> has been removed and all the associated tasks`, 'fas fa-check-circle text-success', 5000);
        })
        .fail(function (data) {
            if(!data.hasOwnProperty('responseJSON')){
                showToast('Unknown error from server', `Internal error.`, 'fas fa-question-circle text-danger', 5000);
                console.log(data.responseText);
                return;
            }
            showToast('Failed', `There was a problem: ${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', 5000);
        })
        .always(function(){
            setTimeout(window.location.reload.bind(window.location), 2000)
        })
 }

 function on_create_dashboard(event) {
    showToast('Creating...', `Your project analytics environment is being set up. Wait a second.`, 'fas fa-spinner text-success', 10000);
}

function copy_kibana_public_link() {
  var project_id = this.getAttribute("data-project-id");
  var copyText = document.getElementById('url-public-link-kibana_' + project_id);
  copyText.select();
  document.execCommand("copy");

  share_button = $(this);
  share_button.tooltip('show');
  setTimeout(function () {share_button.tooltip('hide')}, 1000)
}
