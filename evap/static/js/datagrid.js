// Grid based data grid which has its container separated from its header
export class ResultGrid {
    init({storageKey, head, container, searchInput, filterCheckboxes, sortColumnSelect, sortOrderCheckboxes, resetFilter, resetOrder}) {
        this.storageKey = storageKey;
        this.sortableHeaders = new Map();
        head.find(".col-order").each((index, header) => {
            const column = $(header).data("col");
            this.sortableHeaders.set(column, $(header));
        });
        this.container = container;
        this.searchInput = searchInput;
        this.filterCheckboxes = filterCheckboxes;
        this.sortColumnSelect = sortColumnSelect;
        this.sortOrderCheckboxes = sortOrderCheckboxes;
        this.resetFilter = resetFilter;
        this.resetOrder = resetOrder;
        this.rows = this.fetchRowData();
        this.restoreStateFromStorage();
        this.bindEvents();
    }

    bindEvents() {
        this.delayTimer = null;
        this.searchInput.on("change paste input", () => {
            clearTimeout(this.delayTimer);
            this.delayTimer = setTimeout(() => {
                this.state.search = this.searchInput.val();
                this.filterRows();
                this.renderToDOM();
            }, 200);
        }).keypress(event => {
            // after enter, unfocus the search input to collapse the screen keyboard
            if (event.keyCode === 13) {
                event.target.blur();
            }
        });

        for (const [name, {checkboxes}] of Object.entries(this.filterCheckboxes)) {
            checkboxes.on("change", () => {
                const values = checkboxes.filter(":checked").get().map(elem => elem.value);
                if (values.length > 0) {
                    this.state.filter.set(name, values);
                } else {
                    this.state.filter.delete(name);
                }
                this.filterRows();
                this.renderToDOM();
            });
        }

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

        this.resetFilter.click(() => {
            this.state.search = "";
            this.state.filter.clear();
            this.filterRows();
            this.renderToDOM();
            this.reflectFilterStateOnInputs();
        });

        this.resetOrder.click(() => {
            this.sort(this.defaultOrder);
        });
    }

    fetchRowData() {
        return this.container.children().get()
            .map(row => {
                const searchWords = $(row).find(".evaluation-name, [data-col=responsible]").get()
                    .flatMap(element => this.searchWordsOf($(element).text()));
                let filterValues = new Map();
                for (const [name, {selector, checkboxes}] of Object.entries(this.filterCheckboxes)) {
                    // To store filter values independent of the language, use the corresponding id from the checkbox
                    const values = $(row).find(selector).get()
                        .map(element => $(element).text().trim())
                        .map(filterName => checkboxes.filter(`[data-filter="${filterName}"]`).val());
                    filterValues.set(name, values);
                }
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
                    searchWords,
                    filterValues,
                    orderValues,
                };
            });
    }

    searchWordsOf(string) {
        return string.toLowerCase().trim().split(/\s+/);
    }

    // Filters rows respecting the current search string and filters by their searchWords and filterValues
    filterRows() {
        const searchWords = this.searchWordsOf(this.state.search);
        for (const row of this.rows) {
            const isDisplayedBySearch = searchWords.every(searchWord => {
                return row.searchWords.some(rowWord => rowWord.includes(searchWord));
            });
            const isDisplayedByFilters = [...this.state.filter].every(([name, filterValues]) => {
                return filterValues.some(filterValue => {
                    return row.filterValues.get(name).some(rowValue => rowValue === filterValue);
                });
            });
            row.isDisplayed = isDisplayedBySearch && isDisplayedByFilters;
        }
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
        const elements = this.rows
            .filter(row => row.isDisplayed)
            .map(row => row.element);
        this.container.append($(elements));
        this.saveStateToStorage();
    }

    get defaultOrder() {
        return [["name", "asc"], ["semester", "asc"]];
    }

    restoreStateFromStorage() {
        const stored = JSON.parse(localStorage.getItem(this.storageKey)) || {};
        this.state = {
            search: stored.search || "",
            filter: new Map(stored.filter),
            order: stored.order || this.defaultOrder,
        };
        this.reflectFilterStateOnInputs();
        this.filterRows();
        this.sortRows();
        this.renderToDOM();
    }

    saveStateToStorage() {
        const stored = {
            search: this.state.search,
            filter: [...this.state.filter],
            order: this.state.order,
        };
        localStorage.setItem(this.storageKey, JSON.stringify(stored));
    }

    reflectFilterStateOnInputs() {
        this.searchInput.val(this.state.search);
        for (const [name, {checkboxes}] of Object.entries(this.filterCheckboxes)) {
            checkboxes.each((index, checkbox) => {
                let isActive;
                if (this.state.filter.has(name)) {
                    isActive = this.state.filter.get(name).some(filterValue => {
                        return filterValue === $(checkbox).val();
                    });
                } else {
                    isActive = false;
                }
                $(checkbox).prop("checked", isActive);
            });
        }
    }
}
