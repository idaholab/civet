(function($) {
  $.fn.formset = function(opts)
  {
    var options = $.extend({}, $.fn.formset.defaults, opts),
      totalForms = $('#id_' + options.prefix + '-TOTAL_FORMS'),
      maxForms = $('#id_' + options.prefix + '-MAX_NUM_FORMS'),
      childElementSelector = 'input,select,textarea,label,div,img',
      $$ = $(this)

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
        d.click(function()
        {
          if (del.length)
          {
            del.attr('checked', true);
            del.hide();
          } else {
          }
          row.hide();
          if (options.deleteCallback)
            options.deleteCallback(row);
        });
      } else {
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
      if (row.find(childElementSelector).length) 
      {
        var formCount = parseInt(totalForms.val());
        for (var i=0; i<formCount; i++)
        {
          var sub_row = $("#" + options.prefix + "-" + i);
          if (sub_row.length)
          {
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

      $(options.addButtonId).click(function()
      {
        var formCount = parseInt(totalForms.val()),
          row = template.clone(true),
          parentDiv = $(options.addLocationId);
        var new_prefix = options.prefix + '-' + formCount;
        if (options.preAddCallback)
          options.preAddCallback(row, options.prefix, formCount);
        row.attr('id', new_prefix);
        row.show();
        parentDiv.append(row);
        row.find(childElementSelector).each(function()
        {
          updateElementIndex($(this), options.prefix, formCount);
        });
        setDeleteFunction(row);
        totalForms.val(formCount + 1);
        if (options.postAddCallback)
          options.postAddCallback(row, options.prefix, formCount);
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
    preAddCallback: null,  // Function called before each time a new form is added
    postAddCallback: null,  // Function called after each time a new form is added
    deleteCallback: null  // Function called each time a form is deleted

  };
})(jQuery);
