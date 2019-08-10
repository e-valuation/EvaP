// Grid based data grid which has its container separated from its header
export class ResultGrid {
    init({head, container, sortColumnSelect, sortOrderCheckboxes, resetOrder}) {
        this.sortableHeaders = new Map();
        head.find(".col-order").each((index, header) => {
            const column = $(header).data("col");
            this.sortableHeaders.set(column, $(header));
        });
        this.container = container;
        this.sortColumnSelect = sortColumnSelect;
        this.sortOrderCheckboxes = sortOrderCheckboxes;
        this.resetOrder = resetOrder;
        this.rows = this.fetchRowData();
        this.state = {
            order: this.defaultOrder,
        };
        this.sortRows();
        this.renderToDOM();
        this.bindEvents();
    }

    bindEvents() {
        for (const [column, header] of this.sortableHeaders) {
            header.click(() => {
                // The first click order the column ascending. All following clicks toggle the order.
                const ordering = header.hasClass("col-order-asc") ? "desc" : "asc";
                this.sort([[column, ordering]]);
            });
        }

        this.sortColumnSelect.add(this.sortOrderCheckboxes).change(() => {
            const column = this.sortColumnSelect.prop("value");
            const order = this.sortOrderCheckboxes.filter(":checked").prop("value");
            if (column === "name-semester") {
                this.sort([["name", order], ["semester", order]]);
            } else {
                this.sort([[column, order]]);
            }
        });

        this.resetOrder.click(() => {
            this.sort(this.defaultOrder);
        });
    }

    fetchRowData() {
        return this.container.children().get()
            .map(row => {
                let orderValues = new Map();
                for (const column of this.sortableHeaders.keys()) {
                    const cell = $(row).find(`[data-col=${column}]`);
                    if (cell.is("[data-order]")) {
                        orderValues.set(column, cell.data("order"));
                    } else {
                        orderValues.set(column, cell.html().trim());
                    }
                }
                return {
                    element: row,
                    orderValues,
                };
            });
    }

    sort(order) {
        this.state.order = order;
        this.sortRows();
        this.renderToDOM();
    }

    // Sorts rows respecting the current order by their orderValues
    sortRows() {
        for (const header of this.sortableHeaders.values()) {
            header.removeClass("col-order-asc col-order-desc");
        }
        for (const [column, ordering] of this.state.order) {
            this.sortableHeaders.get(column).addClass(`col-order-${ordering}`);
        }

        this.rows.sort((a, b) => {
            for (const [column, order] of this.state.order) {
                if (a.orderValues.get(column) < b.orderValues.get(column)) {
                    return order === "asc" ? -1 : 1;
                } else if (a.orderValues.get(column) > b.orderValues.get(column)) {
                    return order === "asc" ? 1 : -1;
                }
            }
            return 0;
        });
    }

    // Reflects changes to the rows to the DOM
    renderToDOM() {
        this.container.children().detach();
        const elements = this.rows.map(row => row.element);
        this.container.append($(elements));
    }

    get defaultOrder() {
        return [["name", "asc"], ["semester", "asc"]];
    }
}
