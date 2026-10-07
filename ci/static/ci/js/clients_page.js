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
 * Auto updates the client status on the clients page.
 * Configured by data attributes on the including script tag:
 *   data-update-url, data-update-interval
 */
(function() {
  var config = document.currentScript.dataset;

  window.clients_interval_id = 0;
  window.onerror=function(msg){
    $("body").attr("JSError",msg);
  }

  function updateClientStatus(contents) {
    var clients = contents.clients;
    for( var i=0; i < clients.length; i++ ){
      var tmp = $('#status_' + clients[i].pk);
      tmp.removeClass().addClass(clients[i].status_class);
      tmp.html(clients[i].status);

      tmp = $('#message_' + clients[i].pk);
      tmp.html(clients[i].message);

      tmp = $('#lastseen_' + clients[i].pk);
      tmp.html(clients[i].lastseen);
    }

    var disabled = contents.disabled_clients || [];
    for( var i=0; i < disabled.length; i++ ){
      var state = $('#state_' + disabled[i].pk);
      if( disabled[i].running_job_url ){
        state.empty().append($('<a>').attr('href', disabled[i].running_job_url).text(disabled[i].state));
      } else {
        state.text(disabled[i].state);
      }
      $('#lastseen_' + disabled[i].pk).html(disabled[i].lastseen);
    }
  }

  function updateClients()
  {
    $.ajax({
      url: config.updateUrl,
      datatype: 'json',
      success: function(contents) {
        updateClientStatus(contents);
      },
      error: function(xhr, textStatus, errorThrown) {
        //alert('Problem with server, no more auto updates');
        clearInterval(window.clients_interval_id);
      }
    });
  }
  $(document).ready(function() {
    // Select all checks every client checkbox in the same table
    $('.select_all').change(function() {
      $(this).closest('table').find('input[name="client_ids"]').prop('checked', this.checked);
    });
    if( window.clients_interval_id == 0 ){
      window.clients_interval_id = setInterval(updateClients, Number(config.updateInterval));
    }
  });
})();
