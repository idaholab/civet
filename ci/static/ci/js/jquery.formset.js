(function($) {
  $.fn.formset = function(opts)
  {
    var options = $.extend({}, $.fn.formset.defaults, opts),
      totalForms = $('#id_' + options.prefix + '-TOTAL_FORMS'),
      maxForms = $('#id_' + options.prefix + '-MAX_NUM_FORMS'),
      childElementSelector = 'input,select,textarea,label,div,img',
      $$ = $(this)
    console.log("Processing " + options.prefix + " : " + totalForms.val());

    updateElementIndex = function(elem, prefix, ndx)
    {
      var idRegex = new RegExp(prefix + '-(\\d*|__prefix__)-'),
        replacement = prefix + '-' + ndx + '-';

      if (elem.attr('id'))
      {
        elem.attr('id', elem.attr('id').replace(idRegex, replacement));
      }
      if (elem.attr('name'))
      {
        elem.attr('name', elem.attr('name').replace(idRegex, replacement));
      }
      if (elem.attr('for'))
      {
        elem.attr('for', elem.attr('for').replace(idRegex, replacement));
      }
    }

    setDeleteFunction = function(row)
    {
      var row_id = row.attr("id");
      var d = $("#"+ row_id + "-delete");
      var del = $("#id_" + row_id + "-DELETE");
      if (d.length)
      {
        console.log('set delete function on ' + d.attr("id"));
        d.click(function()
        {
          if (del.length)
          {
            console.log('hiding and setting to delete : ' + del.attr("id"));
            del.attr('checked', true);
            del.hide();
          } else {
            console.log("Couldn't find -DELETE!");
          }
          row.hide();
          if (options.deleteCallback)
            options.deleteCallback(row);
        });
      } else {
        console.log('failed to set delete function on ' + row_id);
      }
      if (del.length)
      {
        del.hide();
      }
    }

    $$.each(function(i)
    {
      var row = $(this),
        del = row.find('input:checkbox[id $= "-DELETE"]');
      if (del.length)
      {
        del.hide();
        $('label[for="' + del.attr('id') + '"]').hide();
      }
      console.log("processing " + row.attr("id"));
      if (row.find(childElementSelector).length) 
      {
        var formCount = parseInt(totalForms.val());
        console.log("processing " + formCount + " forms");
        for (var i=0; i<formCount; i++)
        {
          var sub_row = $("#" + options.prefix + "-" + i);
          if (sub_row.length)
          {
            console.log("trying to insert delete in : " + sub_row.attr("id"));
            setDeleteFunction(sub_row);
          }
        }
      }
    });

    if ($$.length)
    {
      var template = $(options.formTemplate);
      template.find(childElementSelector).each(function()
      {
        updateElementIndex($(this), options.prefix, '__prefix__');
      });

      console.log('Setting add button click : ' + $(options.addButtonId).attr("id"));
      $(options.addButtonId).click(function()
      {
        var formCount = parseInt(totalForms.val()),
          row = template.clone(true),
          parentDiv = $(options.addLocationId);
        var new_prefix = options.prefix + '-' + formCount;
        console.log('from template : ' + options.formTemplate);
        console.log('new row: ' + row.html());
        row.attr('id', new_prefix);
        row.show();
        parentDiv.append(row);
        console.log('new row with id : ' + row.attr('id') + ' : ' + new_prefix);
        row.find(childElementSelector).each(function()
        {
          updateElementIndex($(this), options.prefix, formCount);
        });
        setDeleteFunction(row);
        totalForms.val(formCount + 1);
        if (options.addedCallback)
          options.addedCallback(row, options.prefix, formCount);
        return false;
      });
    }
    return $$;
  };

  $.fn.formset.defaults = {
    prefix: 'form',       // The form prefix for your django formset
    formTemplate: null,   // The jQuery selection cloned to generate new form instances
    addLocationId: null,  // locaction to append new elements      
    addButtonId: null,    // jQuery buton id to add form
    addedCallback: null,  // Function called each time a new form is added
    deleteCallback: null  // Function called each time a form is deleted

  };
})(jQuery);
