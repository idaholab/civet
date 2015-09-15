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
      var job_groups = evs[i].job_groups;
      for( var j=0; j < job_groups.length; j++ ){
        var jobs=job_groups[j]
        for( var k=0; k < jobs.length; k++ ){
          new_ev += '<td id="job_' + jobs[k].id + '"></td>';
        }
        if( j < (job_groups.length - 1)){
          new_ev += '<td>-&gt;</td>';
        }
      }
      new_ev += '</tr>';
      $('#event_table').append(new_ev);
    }
    $('#event_status_' + evs[i].id).removeClass().addClass('job_status_' + evs[i].status).addClass('event_name');
    $('#event_' + evs[i].id).attr("data-date", evs[i].sort_time);
    var job_groups = evs[i].job_groups;
    for( var k=0; k < job_groups.length; k++){
      var jobs = job_groups[k];
      for( var j=0; j < jobs.length; j++){
        $('#job_' + jobs[j].id).removeClass().addClass('job_status_' + jobs[j].status);
        $('#job_' + jobs[j].id).html(jobs[j].info);
      }
    }
  }
  /* now sort by last modified */
  $('#event_table tr').sort(function(a, b) {
    return $(a).attr('data-date') < $(b).attr('data-date');
  }).appendTo('#event_table');
  /* now limit to the max number */
  $("#event_table").find("li:gt(" + event_limit + ")").remove();
}

function updateMainPage( status_data, limit )
{
  updateEvents(status_data.events, limit);

  var repos = status_data.repo_status;
  var closed = status_data.closed;
  if( repos.length == 0 && closed.length == 0){
    return;
  }
  for( var i=0, len=repos.length; i < len; i++){
    var repo = $('#repo_' + repos[i].id);
    if( repo.length == 0 ){
      var repo_html = '<li id="repo_' + repos[i].id + '"><a href="' + repos[i].url + '">' + repos[i].name + '</a></li>';
      repo_html += '<ul id="repo_status_' + repos[i].id + '">';
      if( repos[i].branches.length ){
        repo_html += '<li id="branches_' + repos[i].id + '"></li>';
      }
      repo_html += '</ul>';
      $('#repo_list').append(repo_html);
    }

    var branches = repos[i].branches;
    for( var j=0, blen=branches.length; j < blen; j++){
      var branch = $('#branch_' + branches[j].id);
      if( branch.length ){
        branch.removeClass().addClass('job_status_' + branches[j].status);
      }else{
        b_text = '<span id="branch_' + branches[j].id + '" class="job_status_' + branches[j].status + '"><a href="' + branches[j].url + '">' + branches[j].name +'</a></span>';
        $('#branches_' + repos[i].id).append(b_text);
      }
    }
    var prs = repos[i].prs;
    for( var j=0, plen=prs.length; j < plen; j++){
      var pr_status = $('#pr_status_' + prs[j].id);
      if( pr_status.length ){
        pr_status.removeClass().addClass('job_status_' + prs[j].status);
      }else{
        var row_class = 'list_row1';
        if( $('#repo_status_' + repos[i].id).last().hasClass('list_row1') ){
          row_class = 'list_row2';
        }
        pr_text = '<li id="pr_' + prs[j].id + '" class="' + row_class + '">';
        pr_text += '<span id="pr_status_' + prs[j].id + '" class="job_status_' + prs[j].status + '">';
        pr_text += '<a href="' + prs[j].url + '">#' + prs[j].number + '</a>';
        pr_text += '</span><span> ' + prs[j].title + ' by ' + prs[j].user + '</span></li>';

        $('#repo_status_' + repos[i].id).append(pr_text);
      }
    }
  }
  /* now get rid of any closed PRs */
  for( var i=0, len=closed.length; i < len; i++){
    var to_remove=$('#pr_' + closed[i].id);
    var parent = to_remove.parent();
    to_remove.remove();
    parent.find('li:odd').removeClass().addClass('list_row2');
    parent.find('li:even').removeClass().addClass('list_row1');
  }
}

function updatePRPage( status_data )
{
  $('#pr_status').removeClass().addClass('job_status_' + status_data.status);
  $('#pr_status').text(status_data.closed);
  $('#pr_created').text(status_data.created);
  $('#pr_last_modified').text(status_data.last_modified);
  updateEvents( status_data.events, 1000 )
}

function updateEventPage( status_data )
{
  $('#event_status').removeClass().addClass('job_status_' + status_data.status);
  $('#event_status').text(status_data.complete);
  $('#event_created').text(status_data.created);
  $('#event_last_modified').text(status_data.last_modified);
  updateEvents( status_data.events, 1000 )
}
