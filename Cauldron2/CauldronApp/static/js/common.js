ERROR_TIMEOUT_MS = 60000;

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

    $('form.create-project').on('submit', on_create_project);

    /**
    * Send data to Share modal
    */
    $('.shareproject').click(function () {
        var projname = $(this).data('projname');
        var projid = $(this).data('projid');
        var projurl = $(this).data('projurl');
        $('#shareModal .modal-title').text('Share ' + projname + ' public dashboard');
        $('#shareModal .modal-body input').attr('id', 'url-public-link-kibana_'+projid);
        $('#shareModal .modal-body input').attr('value', projurl);
        $('#shareModal .modal-body button.copy-share-link-kibana').attr('data-project-id', projid);
        $('#shareModal .modal-body .btn-group .shareontwitter').attr('href', 'https://twitter.com/intent/tweet?text=Watch+the+public+metrics+about+'+projname+'+development+provided+by+@cauldronio:&url='+projurl+'&hashtags=LevelUp,OpenSource,DevAnalytics');
        $('#shareModal .modal-body .btn-group .shareonlinkedin').attr('href', 'https://www.linkedin.com/shareArticle?mini=true&text=Watch+this+amazing+visualizations+of+'+projname+'+made+with+@cauldronio&url='+projurl);
        $('#shareModal .modal-body .btn-group .shareonemail').attr('href', 'mailto:?subject='+projname+' visualizations by Cauldronio&body='+projurl);
    })

    $('[data-toggle="tooltip"]').tooltip();

    $('.copy-share-link-kibana').click(copy_kibana_public_link);
});


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
                showToast('Unknown error from server', `Internal error.`, 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
                console.log(data.responseText);
                return;
            }
            showToast('Failed', `There was a problem: ${data.responseJSON['status']} ${data.status}: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
        })
        .always(function(){
            setTimeout(window.location.reload.bind(window.location), 2000)
        })
 }

 function on_create_project(event) {
    showToast('Creating...', `Your project analytics environment is being set up. Wait a second.`, 'fas fa-spinner text-success', 10000);
}

function copy_kibana_public_link() {
  var project_id = $(this).attr('data-project-id');
  var copyText = $('#url-public-link-kibana_' + project_id)[0];
  copyText.focus();
  copyText.select();
  try {
    var successful = document.execCommand('copy');
    var msg = successful ? 'successful' : 'unsuccessful';
    console.log('Copying text command was ' + msg);
  } catch (err) {
    console.log('Oops, unable to copy');
  }

  share_button = $(this);
  share_button.tooltip('show');
  setTimeout(function () {share_button.tooltip('hide')}, 1000)
}

// From https://stackoverflow.com/a/21903119/5930859
var getUrlParameter = function getUrlParameter(sParam) {
    var sPageURL = window.location.search.substring(1),
        sURLVariables = sPageURL.split('&'),
        sParameterName,
        i;

    for (i = 0; i < sURLVariables.length; i++) {
        sParameterName = sURLVariables[i].split('=');

        if (sParameterName[0] === sParam) {
            return sParameterName[1] === undefined ? true : decodeURIComponent(sParameterName[1]);
        }
    }
};


var getURLParameterList = function getURLParameterList(sParam) {
    var sPageURL = window.location.search.substring(1),
        sURLVariables = sPageURL.split('&'),
        params = [],
        sParameterName,
        i;

    for (i = 0; i < sURLVariables.length; i++) {
        sParameterName = sURLVariables[i].split('=');

        if (sParameterName[0] === sParam) {
            params.push(sParameterName[1] === undefined ? true : decodeURIComponent(sParameterName[1]));
        }
    }

    return params;
};
