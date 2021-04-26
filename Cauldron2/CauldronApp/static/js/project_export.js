var Project_ID = window.location.pathname.split('/')[2];

$(document).ready(function(){
    getExportStatus();
    $('.generate-csv').click(onGenerateExport)
})

function getExportStatus() {
    $.getJSON(`/project/${Project_ID}/export/status`, onExportStatus);
    setTimeout(getExportStatus, 5000);
}

function onExportStatus(data){
    for (key in data) {
        var lkey = key.toLowerCase();
        if (data[key]['running']) {
            $(`.${lkey}-row .generate-spinner`).show();
            $(`.${lkey}-row .generate-icon`).hide();
        } else {
            $(`.${lkey}-row .generate-spinner`).hide();
            $(`.${lkey}-row .generate-icon`).show();
        }
        if (data[key]['created']) {
            var created = moment(data[key]['created'], 'YYYY-MM-DDTHH:mm:ss.SSSZ', true).fromNow();
            $(`.${lkey}-row .creation`).html(created);
        }
        if (data[key]['size']) {
            $(`.${lkey}-row .size`).html(human_size(data[key]['size']));
        }
        if (data[key]['link']) {
            $(`.${lkey}-row a.csv-link`).attr('href', data[key]['link']);
            $(`.${lkey}-row a.csv-link`).removeClass('disabled');
        }
    }
}

function onGenerateExport(event){
    var backend = $(event.currentTarget).data('backend');
    $.post(url =`/project/${Project_ID}/export/create`,
        data = {'backend': backend}
    )
    .done(function (data) {
        $(`.${backend.toLowerCase()}-row .generate-spinner`).show();
        $(`.${backend.toLowerCase()}-row .generate-icon`).hide();
    })
    .fail(function (data) {
        if(!data.hasOwnProperty('responseJSON')){
                showToast('Unknown error from server', `Internal error.`, 'fas fa-question-circle text-danger', ERROR_TIMEOUT_MS);
                return;
            }
            showToast('Failed', `There was a problem: ${data.responseJSON['message']}`, 'fas fa-times-circle text-danger', ERROR_TIMEOUT_MS);
    })
}


function human_size(bytes) {
      var units = ['B', 'KB', 'MB', 'GB'];
      var pos = 0

      while((bytes > 999) && (units.length - 1 > pos)){
            bytes /= 1000;
            ++pos;
      }
      return bytes.toFixed(2) + ' ' + units[pos];
}
