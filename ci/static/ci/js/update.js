/*
 * Copyright 2016 Battelle Energy Alliance, LLC
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

function updateEvents( evs, event_limit )
{
  for( var i=0, len=evs.length; i < len; i++){
    var li = $('#event_' + evs[i].id);
    if( li.length == 0 ){
      /* if the event doesn't exist, just create a basic one. The rest
       * will be filled in later.
       */
      var new_ev = '<tr id="event_' + evs[i].id + '">';
      new_ev += '<td id="event_status_' + evs[i].id + '">' + evs[i].description + '</td>';
      var jobs = evs[i].jobs;
      for( var j=0; j < jobs.length; j++ ){
        if( jobs[j].id == 0 ){
          new_ev += '<td class="depends"><span class="glyphicon glyphicon-arrow-right"></span></td>';
        }else{
          new_ev += '<td id="job_' + jobs[j].id + '"></td>';
        }
      }
      new_ev += '</tr>';
      $('#event_table').append(new_ev);
    }

    $('#event_status_' + evs[i].id).removeClass().addClass('job_status_' + evs[i].status);
    $('#event_' + evs[i].id).attr("data-date", evs[i].sort_time + '_9999');
    var jobs = evs[i].jobs;
    for( var j=0; j < jobs.length; j++){
      if( jobs[j].id == 0 ){
        continue;
      }
      var job_id = '#job_' + jobs[j].id;
      /* if the job doesn't exist yet, just create an empty <td> and append it to the row */
      if( $(job_id).length == 0 ){
        new_job_td = '<td id="job_' + jobs[j].id + '"></td>';
        $('#event_' + evs[i].id).append(new_job_td);
      }
      $(job_id).removeClass().addClass('job_status_' + jobs[j].status);
      $(job_id).html(jobs[j].description);
    }
  }
  $('#event_table tr').sort(function(a, b) {
    var date_a = a.getAttribute('data-date'),
      date_b = b.getAttribute('data-date');
    if( date_a != date_b ){
      return date_a > date_b ? -1 : 1;
    }
    /* We can have the same time so then
     * just sort by id.
     */
    var id_a = a.getAttribute('id'),
      id_b = b.getAttribute('id');
    if( id_a != id_b ){
      return id_a < id_b ? -1 : 1;
    }
    return 0;
  }).appendTo('#event_table');
  /* now limit to the max number */
  var count = 0;
  $("#event_table").find("tr").filter(function(i, e){
    if( e.id.split('_').length == 2 ){
      count++;
    }
    return count > event_limit;
  }).remove()
}

function newBranchHTML(branch)
{
  var branch_html = '<span id="branch_' + branch.id + '" class="boxed_job_status_' + branch.status + '">';
  branch_html += branch.description;
  branch_html += '</span>';
  return branch_html;
}

function updateReposStatus( status_data, limit )
{
  var repos = status_data.repo_status;
  var closed = status_data.closed;
  if( repos.length == 0 && closed.length == 0){
    return;
  }
  for( var i=0; i < repos.length; i++){
    var repo = $('#repo_' + repos[i].id);

    if( repo.length == 0 ){
      /* New repo, just set up a dummy */
      var repo_html = '<li class="list-group-item" id="repo_' + repos[i].id +'">';
      repo_html += '<span id="repo_desc_' + repos[i].id + '">' + repos[i].description + '</span>';
      repo_html += '<span id="repo_branches_' + repos[i].id + '">';
      for( var j=0, len=repos[i].branches.length; j < len; j++){
        repo_html += newBranchHTML(repos[i].branches[j]);
      }
      repo_html += '</span>';
      repo_html += '<ul id="pr_list_' + repos[i].id + '" class="pr_list"></ul>';
      repo_html += '</li>';
      $('#repo_status').append(repo_html);
    }else{
      for( var j=0, len=repos[i].branches.length; j < len; j++){
        branch = $('#branch_' + repos[i].branches[j].id);
        if( branch.length == 0 ){
          var branch_span = $('#repo_branches_' + repos[i].id);
          var branch_html = newBranchHTML(repos[i].branches[j]);
          var orig_html = branch_span.html();
          branch_span.html(orig_html + branch_html);
        }else{
          branch.removeClass().addClass('boxed_job_status_' + repos[i].branches[j].status);
        }
      }
      for( var j=0, len=repos[i].badges.length; j < len; j++){
        badge = $('#badge_' + repos[i].badges[j].id);
        if( badge.length > 0 ){
          badge.removeClass().addClass('badge_job_status_' + repos[i].badges[j].status);
        }
      }
    }

    var prs = repos[i].prs;
    for( var j=0; j < prs.length; j++){
      var pr_row = $('#pr_' + prs[j].id);
      if( pr_row.length ){
        pr_row.html(prs[j].description);
      }else{
        var pr_text = '<li id="pr_' + prs[j].id + '" data-sort="' + prs[j].number + '">' + prs[j].description + '</li>';
        $('#pr_list_' + repos[i].id).append(pr_text);
      }
    }
    $('#pr_list_' + repos[i].id + ' li').sort(function(a, b) {
      var date_a = parseInt(a.getAttribute('data-sort')),
        date_b = parseInt(b.getAttribute('data-sort'));
      if( date_a != date_b ){
        return date_a < date_b ? -1 : 1;
      }
      return 0;
    }).appendTo('#pr_list_' + repos[i].id);
  }
  /* now get rid of any closed PRs */
  for( var i=0, len=closed.length; i < len; i++){
    var to_remove=$('#pr_' + closed[i].id);
    to_remove.remove();
  }
}

function updatePRPage( status_data )
{
  $('#pr_status').removeClass().addClass('row result_' + status_data.status);
  $('#pr_closed').text(status_data.closed);
  $('#pr_created').text(status_data.created);
  $('#pr_last_modified').text(status_data.last_modified);
  updateEvents( status_data.events, 1000 )
}

function updateEventPage( status_data )
{
  $('#event_status').removeClass().addClass('row').addClass('result_' + status_data.status);
  if( status_data.complete ){
    $('#event_complete').removeClass().addClass('glyphicon').addClass('glyphicon-ok')
  }else{
    $('#event_complete').removeClass().addClass('glyphicon').addClass('glyphicon-remove')
  }
  $('#event_created').text(status_data.created);
  $('#event_last_modified').text(status_data.last_modified);
  updateEvents( status_data.events, 1000 )
}
