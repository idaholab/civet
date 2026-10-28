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
 * Loads the output of a step on the job page the first time that it is
 * expanded, so the page doesn't include the output of every step.
 * Configured by data attributes on the including script tag:
 *   data-output-url
 */
(function() {
  var config = document.currentScript.dataset;

  $(document).on('show.bs.collapse', '.panel-collapse', function() {
    var output_id = $(this).find('.job_result_output');
    if( output_id.length == 0 || output_id.attr('data-output-state') ){
      return;
    }
    output_id.attr('data-output-state', 'loading');
    output_id.text('Loading...');
    $.ajax({
      url: config.outputUrl,
      datatype: 'json',
      data: { 'result_id': output_id[0].id.replace('result_output_', '') },
      success: function(contents) {
        output_id.html(contents.contents);
        output_id.attr('data-output-length', contents.output_length);
        /* job_page.js keeps the loaded output up to date */
        output_id.attr('data-output-state', 'loaded');
      },
      error: function() {
        output_id.text('Failed to load the output');
        output_id.removeAttr('data-output-state');
      }
    });
  });
})();
