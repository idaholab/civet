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
 * Auto updates the repo status and event table on the main and repo pages.
 * Requires update.js. Configured by data attributes on the including script tag:
 *   data-update-url, data-last-request, data-event-limit, data-update-interval
 *   and optionally data-repo-id and data-default-view
 */
(function() {
  var config = document.currentScript.dataset;
  var last_request = config.lastRequest;
  var event_limit = Number(config.eventLimit);

  window.onerror=function(msg){
    $("body").attr("JSError",msg);
  }

  function updateEventsPage()
  {
    var data = { 'last_request': last_request, 'limit': event_limit };
    if( config.repoId ){
      data['repo_id'] = config.repoId;
    }
    if( config.defaultView ){
      data['default'] = "1";
    }
    $.ajax({
      url: config.updateUrl,
      datatype: 'json',
      data: data,
      success: function(contents) {
        updateReposStatus(contents, event_limit);
        updateEvents(contents.events, event_limit);
        last_request = contents.last_request;
      },
      error: function(xhr, textStatus, errorThrown) {
        //alert('Problem with server, no more auto updates');
        clearInterval(window.status_interval_id);
      }
    });
  }

  window.status_interval_id = 0;
  $(document).ready(function() {
    if( window.status_interval_id == 0 ){
      window.status_interval_id = setInterval(updateEventsPage, Number(config.updateInterval));
    }
  });
})();
