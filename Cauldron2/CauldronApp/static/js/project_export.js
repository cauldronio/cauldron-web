var Project_ID = window.location.pathname.split('/')[2];

$(document).ready(function(){
    getExportStatus();
    $('.generate-csv').click(onGenerateExport);

    $('#date-picker-input').daterangepicker({
        startDate: moment().subtract(1, 'year'),
        endDate: moment(),
        maxDate: moment(),
        opens: 'left',
        locale: {
            format: 'YYYY/MM/DD'
        }
    }, onDateChange);

    $('#date-picker').daterangepicker({
        startDate: moment().subtract(1, 'year'),
        endDate: moment(),
        maxDate: moment(),
        opens: 'left',
        ranges: {
           'Last 30 Days': [moment().subtract(29, 'days'), moment()],
           'Last 6 months': [moment().subtract(6, 'months'), moment()],
           'Last Year': [moment().subtract(1, 'year'), moment()],
           'Last 3 Years': [moment().subtract(3, 'years'), moment()],
           'All (20 years)': [moment().subtract(20, 'years'), moment()]
        },
        showCustomRangeLabel: false
    }, onDateChange);
})

function onDateChange(new_start, new_end) {
    $('#date-picker-input').val(new_start.format('YYYY/MM/DD') + ' - ' + new_end.format('YYYY/MM/DD'));
}

function getExportStatus() {
    $.getJSON(`/project/${Project_ID}/export/status`, onExportStatus);
    setTimeout(getExportStatus, 5000);
}

function onExportStatus(data){
    var csv_data = data['csv']

    for (key in csv_data) {
        var lkey = key.toLowerCase();
        if (csv_data[key]['running']) {
            $(`.${lkey}-row .generate-spinner`).show();
            $(`.${lkey}-row .generate-icon`).hide();
        } else {
            $(`.${lkey}-row .generate-spinner`).hide();
            $(`.${lkey}-row .generate-icon`).show();
        }
        if (csv_data[key]['created']) {
            var created = moment(csv_data[key]['created'], 'YYYY-MM-DDTHH:mm:ss.SSSZ', true).fromNow();
            $(`.${lkey}-row .creation`).html(created);
        }
        if (csv_data[key]['size']) {
            $(`.${lkey}-row .size`).html(human_size(csv_data[key]['size']));
        }
        if (csv_data[key]['link']) {
            $(`.${lkey}-row a.csv-link`).attr('href', csv_data[key]['link']);
            $(`.${lkey}-row a.csv-link`).removeClass('disabled');
        }
    }

    var report_data = data['kbn_reports'];
    for (r in report_data) {
        if (report_data[r]['location']){
            var anchor = `<a href="/download/${report_data[r]['location']}" target="_blank">Download</a>`
            $(`#printable-report-${r} td.report-location`).html(anchor);
        } else if (report_data[r]['progress']){
            $(`#printable-report-${r} td.report-location`).html(report_data[r]['progress'] + `<div class="spinner-border spinner-border-sm ml-3" role="status"></div>`);
        } else {
            $(`#printable-report-${r} td.report-location`).html('error');
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
