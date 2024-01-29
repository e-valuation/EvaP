function makeFormSortable(tableId, prefix, rowChanged, rowAdded, tolerance, removeAsButton, usesTemplate) {

    function applyOrdering() {
        $(document).find('tr').each(function(i) {
            if (rowChanged($(this))) {
                $(this).find('input[id$=-order]').val(i);
            }
            else {
                // if the row is empty (has no text in the input fields) set the order to -1 (default),
                // so that the one extra row doesn't change its initial value
                $(this).find('input[id$=-order]').val(-1);
            }
        });
    }

    $('#' + tableId + ' tbody tr').formset({
        prefix: prefix,
        deleteCssClass: removeAsButton ? 'btn btn-danger btn-sm' : 'delete-row',
        deleteText: removeAsButton ? '<span class="fas fa-trash"></span>' : gettext('Delete'),
        addText: gettext('add another'),
        added: function(row) {
            row.find('input[id$=-order]').val(row.parent().children().length);

            // We have to empty the formset, otherwise sometimes old contents from
            // invalid forms are copied (#644).
            // Checkboxes with 'data-keep' need to stay checked.
            row.find("input:checkbox:not([data-keep]),:radio").removeAttr("checked");

            row.find("input:text,textarea").val("");

            row.find("select").each(function(){
                $(this).find('option:selected').removeAttr("selected");
                $(this).find('option').first().attr("selected", "selected");
            });

            //Check the first item in every button group
            row.find(".btn-group").each(function() {
                var inputs = $(this).find("input");
                $(inputs[0]).prop("checked", true);
            });

            //Remove all error messages
            row.find(".error-label").remove();

            rowAdded(row);
        },
        formTemplate: (usesTemplate ? ".form-template" : null)
    });

    new Sortable($('#' + tableId + " tbody").get(0), {
        handle: ".fa-up-down",
        draggable: ".sortable",
        scrollSensitivity: 70
    });

    $('form').submit(function() {
        applyOrdering();
        return true;
    });
}
