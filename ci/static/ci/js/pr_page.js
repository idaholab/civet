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
 * Auto updates the pull request page.
 * Requires update.js. Configured by data attributes on the including script tag:
 *   data-update-url, data-update-interval
 */
(function() {
  var config = document.currentScript.dataset;

  function updatePR()
  {
    $.ajax({
      url: config.updateUrl,
      datatype: 'json',
      success: function(contents) {
        updatePRPage(contents);
      },
      error: function(xhr, textStatus, errorThrown) {
        // alert('Problem with server, no more auto updates');
        //clearInterval(window.status_interval_id);
      }
    });
  }


  window.status_interval_id = 0;
  $(document).ready(function() {
    if( window.status_interval_id == 0 ){
      window.status_interval_id = setInterval(updatePR, Number(config.updateInterval));
    }
  });
})();
