function updateEvents( event_data, event_limit )
{
  if( ! event_data ){
    return;
  }
  if( ! event_data.events ){
    return;
  }
  var evs = event_data.events;
  if( evs.length == 0 ){
    return;
  }
  /* just update the fields first */
  for( var i=0, len=evs.length; i < len; i++){
    var li = $('#event_' + evs[i].id);
    if( li.length ){
      $('#event_status_' + evs[i].id).removeClass().addClass('job_status_' + evs[i].status).addClass('event_name');
      $('#event_last_' + evs[i].id).text(evs[i].last_modified);
      $('#event_' + evs[i].id).attr("data-date", evs[i].last_modified_date);
      var job_groups = evs[i].job_groups;
      for( var k=0; k < job_groups.length; k++){
        var jobs = job_groups[k];
        for( var j=0; j < jobs.length; j++){
          $('#job_' + jobs[j].id).removeClass().addClass('job_status_' + jobs[j].status);
          $('#job_' + jobs[j].id).html(jobs[j].info);
        }
      }
    }else{
      var new_li = $('#empty_event').clone();
      new_li.attr('id', 'event_' + evs[i].id);
      new_li.attr("data-date", evs[i].last_modified_date);
      new_li.find('#empty_event_table').attr('id', 'event_table' + evs[i].id);
      new_li.find('#empty_event_row').attr('id', 'event_row' + evs[i].id);
      new_li.find('#empty_event_status').addClass('job_status_' + evs[i].status);
      new_li.find('#empty_event_status').html(evs[i].description);
      new_li.find('#empty_event_status').attr('id', 'event_status_' + evs[i].id);
      new_li.find('#empty_event_last').text(evs[i].last_modified);
      new_li.find('#empty_event_last').attr('id', 'event_last_' + evs[i].id);
      var job_groups = evs[i].job_groups;
      for( var k=0; k < job_groups.length; k++ ){
        var jobs=job_groups[j]
        for( var j=0; j < jobs.length; j++ ){
          $('#event_row_' + evs[i].id).append('<td id="job_' + jobs[j].id + '" class="job_status_' + jobs[j].status + '">' + jobs[j].info + '</td>');
          if( j < (jobs.length - 1)){
            $('#event_row_' + evs[i].id).append('<td>-&gt;</td>');
          }
        }
      }
    }
  }
  /* now sort by last modified */
  $('#event_list li').sort(function(a, b) {
    return $(a).attr('data-date') < $(b).attr('data-date');
  }).appendTo('#event_list');
  /* now limit to the max number */
  $("#event_list").find("li:gt(" + event_limit + ")").remove();
}

function updateStatus( status_data )
{
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

function updateMain(event_url, status_url, event_limit)
{
  $.ajax({
    url: event_url,
    datatype: 'json',
    data: { 'last_request': 5, 'limit': event_limit },
    success: function(contents) {
      updateEvents(contents, event_limit);
    },
    error: function(xhr, textStatus, errorThrown) {
      // alert('Problem with server, no more auto updates');
      //clearInterval(window.status_interval_id);
    }
  });
  $.ajax({
    url: status_url,
    datatype: 'json',
    data: { 'last_request': 5},
    success: function(contents) {
      updateStatus(contents);
    },
    error: function(xhr, textStatus, errorThrown) {
    }
  });
}

