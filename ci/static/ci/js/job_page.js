/*
 * Copyright 2016-2025 Battelle Energy Alliance, LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * Auto updates the results on the job page.
 * Configured by data attributes on the including script tag:
 *   data-update-url, data-job-id, data-update-interval
 */
(function() {
  var config = document.currentScript.dataset;

  window.job_interval_id = 0;
  window.onerror=function(msg){
    $("body").attr("JSError",msg);
  }

  function updateResults(contents) {
    var job_info = contents.job_info;
    var results = contents.results;
    if( job_info.length == 0 ){
      return
    }
    $('#job_status_row').removeClass().addClass('row').addClass('job_status_' + job_info.status);
    if( job_info.complete ){
      $('#job_complete').removeClass().addClass('glyphicon').addClass('glyphicon-ok');
    } else {
      $('#job_complete').removeClass().addClass('glyphicon').addClass('glyphicon-remove');
    }
    if( job_info.active ){
      $('#job_active').removeClass().addClass('glyphicon').addClass('glyphicon-ok');
    }
    if( job_info.invalidated ){
      $('#job_invalidated').removeClass().addClass('glyphicon').addClass('glyphicon-ok');
    } else {
      $('#job_invalidated').removeClass().addClass('glyphicon').addClass('glyphicon-remove');
    }
    if( job_info.ready ){
      $('#job_ready').removeClass().addClass('glyphicon').addClass('glyphicon-ok');
    } else {
      $('#job_ready').removeClass().addClass('glyphicon').addClass('glyphicon-remove');
    }
    $('#job_time').text(job_info.runtime);
    $('#job_last_modified').text(job_info.last_modified);
    $('#job_created').text(job_info.created);
    $('#job_recipe_repo_sha').text(job_info.recipe_repo_sha);
    if( job_info.client_name.length > 0 ){
      var link = $('<a>').attr('href', job_info.client_url).text(job_info.client_name);
      $('#job_client').empty().append(link);
    }

    for( var i=0; i < results.length; i++ ){
      var tb = $('#step_result_' + results[i].id);
      if( tb.length == 0 ){
        /* if the user loaded the page before the job was started, there won't
           be any table for the results, so create one. Just a basic one since
           all the fields will be updated after.
        */
        if( i == 0 ){
          $('#all_results').html('');
        }
        $('#waiting_for_results').show();
        var tb_text = '<div class="panel panel-default" id="step_result_' + results[i].id + '">';
        tb_text += '<table class="result_table table table-hover table-bordered table-condensed table-sm">';
        tb_text += '<tbody>';
        tb_text += '<tr data-toggle="collapse" data-parent="#all_results" data-target="#collapse' + results[i].id + '" class="clickable">';
        tb_text += '<td id="result_status_' + results[i].id + '" class="result_' + results[i].status + '">';
        tb_text += '<span class="caret"> </span> ' + results[i].name + '</td>';
        tb_text += '<td id="result_time_' + results[i].id + '"></td>';
        tb_text += '<td id="result_size_' + results[i].id + '"></td>';
        tb_text += '<td id="result_exit_' + results[i].id + '"></td>';
        tb_text += '</tr>';
        tb_text += '</tbody>';
        tb_text += '</table>';
        tb_text += '<div class="panel-collapse collapse" id="collapse' + results[i].id + '">';
        tb_text += '<pre id="result_output_' + results[i].id + '" class="panel-body job_result_output pre-scrollable"></pre>';
        tb_text += '</div>';
        tb_text += '</div>';
        $('#all_results').append(tb_text);
      }
      $('#result_status_' + results[i].id).removeClass().addClass('result_' + results[i].status);
      $('#result_size_' + results[i].id).text(results[i].output_size);
      $('#result_time_' + results[i].id).text('Time: ' + results[i].runtime);
      if( results[i].complete ){
        $('#result_exit_' + results[i].id).text('Exit: ' + results[i].exit_status);
      }else{
        $('#result_exit_' + results[i].id).text("Not finished");
      }
      var output_id = $('#result_output_' + results[i].id);
      output_id.html(results[i].output);
      output_id.scrollTop(output_id[0].scrollHeight);
    }

    if( job_info.complete ){
      //clearInterval(window.job_interval_id);
      $('#waiting_for_results').hide();
    }
  }

  var last_request = 0;
  function updateJob()
  {
    $.ajax({
      url: config.updateUrl,
      datatype: 'json',
      data: { 'last_request': last_request, 'job_id': config.jobId },
      success: function(contents) {
        updateResults(contents);
        last_request = contents.last_request;
      },
      error: function(xhr, textStatus, errorThrown) {
        //alert('Problem with server, no more auto updates');
        //clearInterval(window.job_interval_id);
        $('#waiting_for_results').hide();
      }
    });
  }
  $(document).ready(function() {
   if( window.job_interval_id == 0 ){
      window.job_interval_id = setInterval(updateJob, Number(config.updateInterval));
      $('#waiting_for_results').show();
    }
  });
})();
