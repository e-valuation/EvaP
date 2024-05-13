declare const Sortable: typeof import("sortablejs");

class FormsetOptions {
    prefix: string = "form";
    deleteCssClass: string = "delete-row";
    deleteText: string = "remove";
    addText: string = "add another";
    added: null | ((arg: JQuery<HTMLTableRowElement>) => void) = null;
    formTemplate: string | null = null;
}

interface JQuery {
    formset: (arg: FormsetOptions) => void;
}

function makeFormSortable(
    tableId: string,
    prefix: string,
    rowChanged: (arg: HTMLTableRowElement) => boolean,
    rowAdded: (arg: HTMLTableRowElement) => void,
    removeAsButton: boolean,
    usesTemplate: boolean,
) {
    function applyOrdering() {
        document.querySelectorAll("tr").forEach((tableRow, i) => {
            if (rowChanged(tableRow)) {
                (tableRow.querySelectorAll("input[id$=-order]") as NodeListOf<HTMLInputElement>).forEach(input => {
                    input.value = i.toString();
                });
            } else {
                // if the row is empty (has no text in the input fields) set the order to -1 (default),
                // so that the one extra row doesn't change its initial value
                (tableRow.querySelectorAll("input[id$=-order]") as NodeListOf<HTMLInputElement>).forEach(input => {
                    input.value = "-1";
                });
            }
        });
    }

    // This is the only remaining jQuery usage, since formset requires jQuery
    $(`#${tableId} tbody tr`).formset({
        prefix: prefix,
        deleteCssClass: removeAsButton ? "btn btn-danger btn-sm" : "delete-row",
        deleteText: removeAsButton ? '<span class="fas fa-trash"></span>' : window.gettext("Delete"),
        addText: window.gettext("add another"),
        added: function (rowJQuery) {
            var row = rowJQuery.get()[0];
            (row.querySelectorAll("input[id$=-order]") as NodeListOf<HTMLInputElement>).forEach(input => {
                input.value = row.parentElement?.childElementCount.toString() ?? "";
            });

            // We have to empty the formset, otherwise sometimes old contents from
            // invalid forms are copied (#644).
            // Checkboxes with 'data-keep' need to stay checked.
            row.querySelectorAll("input[type=checkbox]:not([data-keep]),input[type=radio]").forEach(el => {
                el.removeAttribute("checked");
            });

            (row.querySelectorAll("input[type=text],input[type=textarea]") as NodeListOf<HTMLInputElement>).forEach(
                input => {
                    input.value = "";
                },
            );

            row.querySelectorAll("select").forEach(el => {
                el.querySelectorAll("option[selected]").forEach(option => {
                    option.removeAttribute("selected");
                });
                el.querySelector("option")?.setAttribute("selected", "selected");
            });

            //Check the first item in every button group
            row.querySelectorAll(".btn-group").forEach(group => {
                group.querySelector("input")?.setAttribute("checked", "checked");
            });

            //Remove all error messages
            row.querySelectorAll(".error-label").forEach(el => {
                el.remove();
            });

            rowAdded(row);
        },
        formTemplate: usesTemplate ? ".form-template" : null,
    });

    var tableBody = document.querySelector(`#${tableId} tbody`) as HTMLElement | null;
    if (tableBody) {
        new Sortable(tableBody, {
            handle: ".fa-up-down",
            draggable: ".sortable",
            scrollSensitivity: 70,
        });

        document.querySelectorAll("form").forEach(form => {
            form.addEventListener("submit", () => {
                applyOrdering();
                return true;
            });
        });
    }
}
