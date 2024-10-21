import { CSRF_HEADERS } from "./csrf-utils.js";
import { RangeSlider, Range } from "./slider.js";

declare const Sortable: typeof import("sortablejs");

interface Row {
    element: HTMLElement;
    searchWords: string[];
    filterValues: Map<string, string[]>;
    orderValues: Map<string, string | number>;
    isDisplayed: boolean;
}

interface State {
    equalityFilter: Map<string, string[]>;
    rangeFilter: Map<string, Range>;
    search: string;
    order: [string, "asc" | "desc"][];
}

interface BaseParameters {
    storageKey: string;
    searchInput: HTMLInputElement;
}

interface DataGridParameters extends BaseParameters {
    head: HTMLElement;
    container: HTMLElement;
}

abstract class DataGrid {
    private readonly storageKey: string;
    protected sortableHeaders: Map<string, HTMLElement>;
    protected container: HTMLElement;
    private searchInput: HTMLInputElement;
    protected rows: Row[] = [];
    private delayTimer: any | null;
    protected state: State;

    protected constructor({ storageKey, head, container, searchInput }: DataGridParameters) {
        this.storageKey = storageKey;
        this.sortableHeaders = new Map();
        head.querySelectorAll<HTMLElement>(".col-order").forEach(header => {
            const column = header.dataset.col!;
            this.sortableHeaders.set(column, header);
        });
        this.container = container;
        this.searchInput = searchInput;
        this.state = this.restoreStateFromStorage();
    }

    public init() {
        this.rows = this.fetchRows();
        this.reflectFilterStateOnInputs();
        this.filterRows();
        this.sortRows();
        this.renderToDOM();
        this.bindEvents();
    }

    protected bindEvents() {
        this.delayTimer = null;
        this.searchInput.addEventListener("input", () => {
            clearTimeout(this.delayTimer);
            this.delayTimer = setTimeout(() => {
                this.state.search = this.searchInput.value;
                this.filterRows();
                this.renderToDOM();
            }, 200);
        });
        this.searchInput.addEventListener("keypress", event => {
            // after enter, unfocus the search input to collapse the screen keyboard
            if (event.key === "enter") {
                this.searchInput.blur();
            }
        });

        for (const [column, header] of this.sortableHeaders) {
            header.addEventListener("click", () => {
                // The first click order the column ascending. All following clicks toggle the order.
                const ordering = header.classList.contains("col-order-asc") ? "desc" : "asc";
                this.sort([[column, ordering]]);
            });
        }
    }

    private static NUMBER_REGEX = /^[+-]?\d+(?:[.,]\d*)?$/;

    private fetchRows(): Row[] {
        const rows = [...this.container.children]
            .map(row => row as HTMLElement)
            .map(row => {
                const searchWords = this.findSearchableCells(row).flatMap(element =>
                    DataGrid.searchWordsOf(element.textContent!),
                );
                return {
                    element: row,
                    searchWords,
                    filterValues: this.fetchRowFilterValues(row),
                    orderValues: this.fetchRowOrderValues(row),
                } as Row;
            });
        for (const column of this.sortableHeaders.keys()) {
            const orderValues = rows.map(row => row.orderValues.get(column) as string);
            const isNumericalColumn = orderValues.every(orderValue => DataGrid.NUMBER_REGEX.test(orderValue));
            if (isNumericalColumn) {
                rows.forEach(row => {
                    const numberString = (row.orderValues.get(column) as string).replace(",", ".");
                    row.orderValues.set(column, parseFloat(numberString));
                });
            }
        }
        return rows;
    }

    protected abstract findSearchableCells(row: HTMLElement): HTMLElement[];

    protected abstract fetchRowFilterValues(row: HTMLElement): Map<string, string[]>;

    private fetchRowOrderValues(row: HTMLElement): Map<string, string> {
        const orderValues = new Map();
        for (const column of this.sortableHeaders.keys()) {
            const cell = row.querySelector<HTMLElement>(`[data-col=${column}]`)!;
            if (cell.matches("[data-order]")) {
                orderValues.set(column, cell.dataset.order);
            } else {
                orderValues.set(column, cell.innerHTML.trim());
            }
        }
        return orderValues;
    }

    private static searchWordsOf(string: string): string[] {
        return string.toLowerCase().trim().split(/\s+/);
    }

    // Filters rows respecting the current search string and filters by their searchWords and filterValues
    protected filterRows() {
        const searchWords = DataGrid.searchWordsOf(this.state.search);
        for (const row of this.rows) {
            const isDisplayedBySearch = searchWords.every(searchWord => {
                return row.searchWords.some(rowWord => rowWord.includes(searchWord));
            });
            const isDisplayedByFilters = [...this.state.equalityFilter].every(([name, filterValues]) => {
                return filterValues.some(filterValue => {
                    return row.filterValues.get(name)?.some(rowValue => rowValue === filterValue);
                });
            });
            const isDisplayedByRangeFilters = [...this.state.rangeFilter].every(([name, bound]) => {
                return row.filterValues
                    .get(name)
                    ?.map(rawValue => parseFloat(rawValue))
                    .some(rowValue => rowValue >= bound.low && rowValue <= bound.high);
            });
            row.isDisplayed = isDisplayedBySearch && isDisplayedByFilters && isDisplayedByRangeFilters;
        }
    }

    protected sort(order: [string, "asc" | "desc"][]) {
        this.state.order = order;
        this.sortRows();
        this.renderToDOM();
    }

    // Sorts rows respecting the current order by their orderValues
    private sortRows() {
        for (const header of this.sortableHeaders.values()) {
            header.classList.remove("col-order-asc", "col-order-desc");
        }
        for (const [column, ordering] of this.state.order) {
            const header = this.sortableHeaders.get(column);
            if (header === undefined) {
                // Silently ignore non-existing columns: They were probably renamed.
                // A correct state will be built the next time the user sorts the datagrid.
                continue;
            }
            header.classList.add(`col-order-${ordering}`);
        }

        this.rows.sort((a, b) => {
            for (const [column, order] of this.state.order) {
                if (a.orderValues.get(column)! < b.orderValues.get(column)!) {
                    return order === "asc" ? -1 : 1;
                } else if (a.orderValues.get(column)! > b.orderValues.get(column)!) {
                    return order === "asc" ? 1 : -1;
                }
            }
            return 0;
        });
    }

    // Reflects changes to the rows to the DOM
    protected renderToDOM() {
        [...this.container.children].map(element => element as HTMLElement).forEach(element => element.remove());
        const elements = this.rows.filter(row => row.isDisplayed).map(row => row.element);
        this.container.append(...elements);
        this.saveStateToStorage();
    }

    private restoreStateFromStorage(): State {
        const stored = JSON.parse(localStorage.getItem(this.storageKey)!) || {};
        return {
            equalityFilter: new Map(stored.equalityFilter),
            rangeFilter: new Map(stored.rangeFilter),
            search: stored.search || "",
            order: stored.order || this.defaultOrder,
        };
    }

    protected abstract get defaultOrder(): [string, "asc" | "desc"][];

    private saveStateToStorage() {
        const stored = {
            equalityFilter: [...this.state.equalityFilter],
            rangeFilter: [...this.state.rangeFilter],
            search: this.state.search,
            order: this.state.order,
        };
        localStorage.setItem(this.storageKey, JSON.stringify(stored));
    }

    protected reflectFilterStateOnInputs() {
        this.searchInput.value = this.state.search;
    }
}

interface TableGridParameters extends BaseParameters {
    table: HTMLTableElement;
    resetSearch: HTMLButtonElement;
}

// Table based data grid which uses its head and body
export class TableGrid extends DataGrid {
    private resetSearch: HTMLButtonElement;

    constructor({ table, resetSearch, ...options }: TableGridParameters) {
        super({
            head: table.querySelector("thead")!,
            container: table.querySelector("tbody")!,
            ...options,
        });
        this.resetSearch = resetSearch;
    }

    public bindEvents() {
        super.bindEvents();
        this.resetSearch.addEventListener("click", () => {
            this.state.search = "";
            this.filterRows();
            this.renderToDOM();
            this.reflectFilterStateOnInputs();
        });
    }

    protected findSearchableCells(row: HTMLElement): HTMLElement[] {
        return [...row.children] as HTMLElement[];
    }

    protected fetchRowFilterValues(row: HTMLElement): Map<string, string[]> {
        return new Map();
    }

    protected get defaultOrder(): [string, "asc" | "desc"][] {
        if (this.sortableHeaders.size > 0) {
            const [firstColumn] = this.sortableHeaders.keys();
            return [[firstColumn, "asc"]];
        }
        return [];
    }
}

interface EvaluationGridParameters extends TableGridParameters {
    filterButtons: HTMLButtonElement[];
}

export class EvaluationGrid extends TableGrid {
    private filterButtons: HTMLButtonElement[];

    constructor({ filterButtons, ...options }: EvaluationGridParameters) {
        super(options);
        this.filterButtons = filterButtons;
    }

    public bindEvents() {
        super.bindEvents();
        this.filterButtons.forEach(button => {
            const count = this.rows.filter(row => {
                return row.filterValues.get("evaluationState")!.includes(button.dataset.filter!);
            }).length;
            button.append(EvaluationGrid.createBadgePill(count));

            button.addEventListener("click", () => {
                if (button.classList.contains("active")) {
                    button.classList.remove("active");
                    this.state.equalityFilter.delete("evaluationState");
                } else {
                    this.filterButtons.forEach(button => button.classList.remove("active"));
                    button.classList.add("active");
                    this.state.equalityFilter.set("evaluationState", [button.dataset.filter!]);
                }
                this.filterRows();
                this.renderToDOM();
            });
        });
    }

    private static createBadgePill(count: number): HTMLElement {
        const badgeClass = count === 0 ? "badge-btn-zero" : "badge-btn";
        const pill = document.createElement("span");
        pill.classList.add("badge", "rounded-pill", badgeClass);
        pill.textContent = count.toString();
        return pill;
    }

    protected fetchRowFilterValues(row: HTMLElement): Map<string, string[]> {
        const evaluationState = [...row.querySelectorAll<HTMLElement>("[data-filter]")].map(
            element => element.dataset.filter!,
        );
        return new Map([["evaluationState", evaluationState]]);
    }

    protected get defaultOrder(): [string, "asc" | "desc"][] {
        return [["name", "asc"]];
    }

    protected reflectFilterStateOnInputs() {
        super.reflectFilterStateOnInputs();
        if (this.state.equalityFilter.has("evaluationState")) {
            const activeEvaluationState = this.state.equalityFilter.get("evaluationState")![0];
            const activeButton = this.filterButtons.find(button => button.dataset.filter === activeEvaluationState)!;
            activeButton.classList.add("active");
        }
    }
}

interface QuestionnaireParameters extends TableGridParameters {
    updateUrl: string;
}

export class QuestionnaireGrid extends TableGrid {
    private readonly updateUrl: string;

    constructor({ updateUrl, ...options }: QuestionnaireParameters) {
        super(options);
        this.updateUrl = updateUrl;
    }

    public bindEvents() {
        super.bindEvents();
        new Sortable(this.container, {
            handle: ".fa-up-down",
            draggable: ".sortable",
            scrollSensitivity: 70,
            onUpdate: event => {
                if (event.oldIndex !== undefined && event.newIndex !== undefined) {
                    this.reorderRow(event.oldIndex, event.newIndex);
                }
                fetch(this.updateUrl, {
                    method: "POST",
                    headers: CSRF_HEADERS,
                    body: new URLSearchParams(
                        this.rows.map((row, index) => [row.element.dataset.id!, index.toString()]),
                    ),
                }).catch((error: unknown) => {
                    console.error(error);
                    window.alert(window.gettext("The server is not responding."));
                });
            },
        });
    }

    private reorderRow(oldPosition: number, newPosition: number) {
        const displayedRows = this.rows.map((row, index) => ({ row, index })).filter(({ row }) => row.isDisplayed);
        this.rows.splice(displayedRows[oldPosition].index, 1);
        this.rows.splice(displayedRows[newPosition].index, 0, displayedRows[oldPosition].row);
    }
}

interface ResultGridParameters extends DataGridParameters {
    filterCheckboxes: Map<string, { selector: string; checkboxes: HTMLInputElement[] }>;
    filterSliders: Map<string, { selector: string; slider: RangeSlider }>;
    sortColumnSelect: HTMLSelectElement;
    sortOrderCheckboxes: HTMLInputElement[];
    resetFilter: HTMLButtonElement;
    resetOrder: HTMLButtonElement;
}

// Grid based data grid which has its container separated from its header
export class ResultGrid extends DataGrid {
    private readonly filterCheckboxes: Map<string, { selector: string; checkboxes: HTMLInputElement[] }>;
    private readonly filterSliders: Map<string, { selector: string; slider: RangeSlider }>;
    private readonly sortColumnSelect: HTMLSelectElement;
    private readonly sortOrderCheckboxes: HTMLInputElement[];
    private readonly resetFilter: HTMLButtonElement;
    private readonly resetOrder: HTMLButtonElement;

    constructor({
        filterCheckboxes,
        filterSliders,
        sortColumnSelect,
        sortOrderCheckboxes,
        resetFilter,
        resetOrder,
        ...options
    }: ResultGridParameters) {
        super(options);
        this.filterCheckboxes = filterCheckboxes;
        this.filterSliders = filterSliders;
        this.sortColumnSelect = sortColumnSelect;
        this.sortOrderCheckboxes = sortOrderCheckboxes;
        this.resetFilter = resetFilter;
        this.resetOrder = resetOrder;
    }

    public bindEvents() {
        super.bindEvents();
        for (const [name, { checkboxes }] of this.filterCheckboxes.entries()) {
            checkboxes.forEach(checkbox => {
                checkbox.addEventListener("change", () => {
                    const values = checkboxes.filter(checkbox => checkbox.checked).map(elem => elem.value);
                    if (values.length > 0) {
                        this.state.equalityFilter.set(name, values);
                    } else {
                        this.state.equalityFilter.delete(name);
                    }
                    this.filterRows();
                    this.renderToDOM();
                });
            });
        }

        for (const [name, { slider }] of this.filterSliders.entries()) {
            this.state.rangeFilter.set(name, slider.range);

            slider.onRangeChange = () => {
                this.state.rangeFilter.set(name, slider.range);
                this.filterRows();
                this.renderToDOM();
            };
        }

        this.sortColumnSelect.addEventListener("change", () => this.sortByInputs());
        this.sortOrderCheckboxes.forEach(checkbox => checkbox.addEventListener("change", () => this.sortByInputs()));

        this.resetFilter.addEventListener("click", () => {
            this.state.search = "";
            this.state.equalityFilter.clear();
            this.state.rangeFilter.clear();
            this.filterRows();
            this.renderToDOM();
            this.reflectFilterStateOnInputs();
        });

        this.resetOrder.addEventListener("click", () => {
            this.sort(this.defaultOrder);
        });
    }

    sortByInputs() {
        const column = this.sortColumnSelect.value;
        const order = this.sortOrderCheckboxes.find(checkbox => checkbox.checked)!.value;
        if (order === "asc" || order === "desc") {
            if (column === "name-semester") {
                this.sort([
                    ["name", order],
                    ["semester", order],
                ]);
            } else {
                this.sort([[column, order]]);
            }
        }
    }

    protected findSearchableCells(row: HTMLElement): HTMLElement[] {
        return [...row.querySelectorAll<HTMLElement>(".evaluation-name, [data-col=responsible]")];
    }

    protected fetchRowFilterValues(row: HTMLElement): Map<string, string[]> {
        const filterValues = new Map<string, string[]>();
        for (const [name, { selector, checkboxes }] of this.filterCheckboxes.entries()) {
            // To store filter values independent of the language, use the corresponding id from the checkbox
            const values = [...row.querySelectorAll(selector)]
                .map(element => element.textContent?.trim())
                .map(filterName => checkboxes.find(checkbox => checkbox.dataset.filter === filterName)?.value)
                .filter(v => v !== undefined);
            filterValues.set(name, values);
        }
        for (const [name, { selector, slider }] of this.filterSliders.entries()) {
            const values = [...row.querySelectorAll<HTMLElement>(selector)]
                .map(element => element.dataset.filterValue)
                .filter(v => v !== undefined);
            filterValues.set(name, values);
            slider.includeValues(values.map(parseFloat));
        }
        return filterValues;
    }

    protected get defaultOrder(): [string, "asc" | "desc"][] {
        return [
            ["name", "asc"],
            ["semester", "asc"],
        ];
    }

    protected reflectFilterStateOnInputs() {
        super.reflectFilterStateOnInputs();
        for (const [name, { checkboxes }] of this.filterCheckboxes.entries()) {
            checkboxes.forEach(checkbox => {
                let isActive;
                if (this.state.equalityFilter.has(name)) {
                    isActive = this.state.equalityFilter.get(name)!.some(filterValue => {
                        return filterValue === checkbox.value;
                    });
                } else {
                    isActive = false;
                }
                checkbox.checked = isActive;
            });
        }
        for (const [name, { slider }] of this.filterSliders.entries()) {
            const filterRange = this.state.rangeFilter.get(name);
            if (filterRange !== undefined) {
                slider.range = filterRange;
            } else {
                slider.reset();
            }
        }
    }
}
