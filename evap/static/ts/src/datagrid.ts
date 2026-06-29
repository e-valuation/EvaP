import { CSRF_HEADERS } from "./csrf-utils.js";
import { RangeSlider, Range } from "./slider.js";
import { assert, selectOrError } from "./utils.js";

declare const Sortable: typeof import("sortablejs");

type Order = [string, "asc" | "desc"][];

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
    resetSearch?: HTMLButtonElement;
    filterButtons: HTMLButtonElement[];
    resetFilterButton?: HTMLButtonElement;
}

interface DataGridParameters extends BaseParameters {
    sortableHeaders: Map<string, HTMLElement>;
    container: HTMLElement;
    defaultOrder: Order;
}

export class DataGrid {
    public readonly rows: Row[] = [];
    private delayTimer: number | undefined;
    // @ts-expect-error is initialized when calling .init()
    protected state: State;

    protected constructor(
        private readonly storageKey: string,
        protected readonly sortableHeaders: Map<string, HTMLElement>,
        public readonly container: HTMLElement,
        private readonly searchInput: HTMLInputElement,
        protected readonly resetSearch: HTMLButtonElement | undefined,
        protected readonly filterButtons: HTMLButtonElement[],
        protected readonly resetFilterButton: HTMLButtonElement | undefined,
        private readonly getRowElements: () => HTMLElement[] = () => [...this.container.children] as HTMLElement[],
        protected readonly defaultOrder: Order = [],
    ) {}

    public static buildSortableHeadersMap(headerContainer: HTMLElement): Map<string, HTMLElement> {
        const sortableHeaders = new Map<string, HTMLElement>();
        for (const orderElement of headerContainer.querySelectorAll<HTMLElement>(".col-order")) {
            sortableHeaders.set(orderElement.dataset.col!, orderElement);
        }
        return sortableHeaders;
    }

    // Table based data grid which uses its head and body
    public static fromHTMLTable({ table, storageKey, searchInput, resetSearch }: TableGridParameters): DataGrid {
        const thead = selectOrError<HTMLTableSectionElement>("thead", table);
        const tbody = selectOrError<HTMLTableSectionElement>("tbody", table);

        const sortableHeaders = DataGrid.buildSortableHeadersMap(thead);

        const [firstColumn] = sortableHeaders.keys();

        const dataGrid = new DataGrid(
            storageKey,
            sortableHeaders,
            tbody,
            searchInput,
            resetSearch,
            [],
            undefined,
            () => [...tbody.children] as HTMLElement[],
            firstColumn ? [[firstColumn, "asc"]] : [],
        );

        dataGrid.init();

        return dataGrid;
    }

    public static fromCSSGridTable({
        gridContainer,
        storageKey,
        searchInput,
        resetSearch,
        gridHeader,
        filterButtons,
        resetFilterButton,
        defaultOrder,
    }: {
        gridContainer: HTMLElement;
        gridHeader?: HTMLElement;
        defaultOrder?: Order;
    } & BaseParameters): DataGrid {
        const head: HTMLElement = gridHeader ?? selectOrError(".gridHeader", gridContainer);

        const dataGrid = new DataGrid(
            storageKey,
            this.buildSortableHeadersMap(head),
            gridContainer,
            searchInput,
            resetSearch,
            filterButtons,
            resetFilterButton,
            () =>
                [...gridContainer.children].filter(
                    row => !row.classList.contains("gridHeader") && !row.classList.contains("empty-disclaimer"),
                ) as HTMLElement[],
            defaultOrder,
        );

        dataGrid.init();

        return dataGrid;
    }

    private static createBadgePill(count: number): HTMLElement {
        const badgeClass = count === 0 ? "badge-btn-zero" : "badge-btn";
        const pill = document.createElement("span");
        pill.classList.add("badge", "rounded-pill", badgeClass);
        pill.textContent = count.toString();
        return pill;
    }

    public bindFilterButtons(filterButtons: HTMLButtonElement[], filterFieldName: string) {
        for (const filterButton of filterButtons) {
            console.assert(
                !!filterButton.dataset[filterFieldName],
                `data-field '${filterFieldName} must be defined on button`,
                filterButton,
            );

            const count = this.rows.filter(row =>
                row.filterValues.get(filterFieldName)!.includes(filterButton.dataset[filterFieldName]!),
            ).length;
            filterButton.append(DataGrid.createBadgePill(count));

            filterButton.addEventListener("click", () => {
                if (filterButton.classList.contains("active")) {
                    filterButton.classList.remove("active");
                    this.state.equalityFilter.delete(filterFieldName);
                } else {
                    filterButtons.forEach(button => button.classList.remove("active"));
                    filterButton.classList.add("active");
                    this.state.equalityFilter.set(filterFieldName, [filterButton.dataset[filterFieldName]!]);
                }
            });
        }
    }

    // TODO: range filter?
    // TODO: think about switching to builder pattern

    public init() {
        this.state = this.restoreStateFromStorage();
        // @ts-expect-error this is the initialization TODO
        this.rows = this.fetchRows(this.getRowElements());
        this.reflectFilterStateOnInputs();
        this.filterRows();
        this.sortRows();
        this.bindEvents();
        this.renderToDOM();
    }

    private addFilter(filterCategory: string, filterValue: string) {
        const filterList = this.state.equalityFilter.get(filterCategory) ?? [];
        if (!filterList.some(v => v === filterValue)) {
            filterList.push(filterValue);
        }
        this.state.equalityFilter.set(filterCategory, filterList);
        this.filterRows();
        this.renderToDOM();
    }

    private removeFilter(filterCategory: string, filterValue: string) {
        const filterList = this.state.equalityFilter.get(filterCategory) ?? [];
        const newFilterList = filterList.filter(v => v !== filterValue);
        if (newFilterList.length === 0) {
            this.state.equalityFilter.delete(filterCategory);
        } else {
            this.state.equalityFilter.set(filterCategory, newFilterList);
        }
        this.filterRows();
        this.renderToDOM();
    }

    private clearFilter(filterCategory: string) {
        this.state.equalityFilter.delete(filterCategory);
    }

    private filterRow(row: Row): boolean {
        return [...this.state.equalityFilter].every(([filterCategory, filterValues]) =>
            filterValues.some(
                filterValue => row.filterValues.get(filterCategory)?.some(rowValue => rowValue === filterValue) ?? true,
            ),
        );
    }

    protected bindEvents() {
        this.delayTimer = undefined;

        // TODO: move into bindSearch()
        this.searchInput.addEventListener("input", () => {
            clearTimeout(this.delayTimer);
            this.delayTimer = window.setTimeout(() => {
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
        this.resetSearch?.addEventListener("click", () => {
            this.state.search = "";
            this.filterRows();
            this.renderToDOM();
            this.reflectFilterStateOnInputs();
        });

        // TODO: move into bindRadioFilter() (and bindCheckboxFilter)
        for (const filterButton of this.filterButtons) {
            const filterCategory = filterButton.dataset.filterCategory;
            const filterValue = filterButton.dataset.filterValue;

            if (!filterCategory || !filterValue) {
                console.error("Filter buttons need both data-filter-value and data-filter-category!", filterButton);
                continue;
            }

            if (!this.state.equalityFilter.has(filterCategory)) {
                this.state.equalityFilter.set(filterCategory, []);
            }
            const count = this.rows.filter(row =>
                row.filterValues.get(filterCategory)?.some(v => v === filterValue),
            ).length;
            filterButton.append(DataGrid.createBadgePill(count));

            filterButton.addEventListener("click", () => {
                if (filterButton.classList.contains("active")) {
                    filterButton.classList.remove("active");
                    this.removeFilter(filterCategory, filterValue);
                } else {
                    // TODO: multi filter
                    this.filterButtons.forEach(b => b.classList.remove("active"));
                    this.clearFilter(filterCategory);
                    filterButton.classList.add("active");
                    this.addFilter(filterCategory, filterValue);
                }
            });
        }

        this.resetFilterButton?.addEventListener("click", () => {
            this.state.equalityFilter.clear();
            this.state.search = "";
            this.state.rangeFilter.clear();
            this.filterRows();
            this.renderToDOM();
            this.reflectFilterStateOnInputs();
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

    private fetchRows(rowElements: HTMLElement[]): Row[] {
        const rows = rowElements.map(row => {
            const searchWords = this.findSearchableCells(row).flatMap(element =>
                DataGrid.searchWordsOf(element.textContent),
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

    protected findSearchableCells(row: HTMLElement): HTMLElement[] {
        const elements = [...row.children] as HTMLElement[];
        return elements.filter(element => !element.hasAttribute("data-not-searchable"));
    }

    protected fetchRowFilterValues(row: HTMLElement): Map<string, string[]> {
        const filterableCells = [...row.querySelectorAll<HTMLElement>("[data-filter-category]")];
        return filterableCells
            .map<[string, string | undefined]>(cell => [cell.dataset.filterCategory!, cell.dataset.filterValue])
            .reduce((acc, [category, value]) => {
                if (!value) {
                    return acc;
                }
                if (acc.has(category)) {
                    acc.get(category)!.push(value);
                } else {
                    acc.set(category, [value]);
                }
                return acc;
            }, new Map<string, string[]>());
    }

    private fetchRowOrderValues(row: HTMLElement): Map<string, string> {
        const orderValues = new Map<string, string>();
        for (const column of this.sortableHeaders.keys()) {
            const cell = row.querySelector<HTMLElement>(`[data-col=${column}]`)!;
            if (cell.matches("[data-order]")) {
                orderValues.set(column, cell.dataset.order!);
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
            const isDisplayedBySearch = searchWords.every(searchWord =>
                row.searchWords.some(rowWord => rowWord.includes(searchWord)),
            );
            const isDisplayedByEqualityFilters = this.filterRow(row);
            const isDisplayedByRangeFilters = [...this.state.rangeFilter].every(([name, bound]) =>
                row.filterValues
                    .get(name)
                    ?.map(rawValue => parseFloat(rawValue))
                    .some(rowValue => rowValue >= bound.low && rowValue <= bound.high),
            );
            row.isDisplayed = isDisplayedBySearch && isDisplayedByEqualityFilters && isDisplayedByRangeFilters;
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

        const collator = new Intl.Collator(document.documentElement.lang, { caseFirst: "false" });
        this.rows.sort((a, b) => {
            for (const [column, order] of this.state.order) {
                const valueA = a.orderValues.get(column);
                const valueB = b.orderValues.get(column);
                if (typeof valueA === "string") {
                    assert(typeof valueB === "string");
                    return order === "asc" ? collator.compare(valueA, valueB) : collator.compare(valueB, valueA);
                }
                assert(typeof valueB !== "string");
                if (valueA! < valueB!) {
                    return order === "asc" ? -1 : 1;
                } else if (valueA! > valueB!) {
                    return order === "asc" ? 1 : -1;
                }
            }
            return 0;
        });
    }

    // Reflects changes to the rows to the DOM
    protected renderToDOM() {
        this.getRowElements().forEach(element => element.remove());
        const elements = this.rows.filter(row => row.isDisplayed).map(row => row.element);
        this.container.append(...elements);
        this.saveStateToStorage();
    }

    private restoreStateFromStorage(): State {
        const stored = JSON.parse(localStorage.getItem(this.storageKey)!) ?? {};
        return {
            equalityFilter: new Map(stored.equalityFilter),
            rangeFilter: new Map(stored.rangeFilter),
            search: stored.search ?? "",
            order: stored.order ?? this.defaultOrder,
        };
    }

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
        this.filterButtons.forEach(b => b.classList.remove("active"));
        for (const filterCategory of this.state.equalityFilter) {
            this.filterButtons
                .filter(
                    b =>
                        b.dataset.filterCategory == filterCategory[0] &&
                        filterCategory[1].some(value => value == b.dataset.filterValue),
                )
                .forEach(b => b.classList.add("active"));
        }
    }
}

interface TableGridParameters extends BaseParameters {
    table: HTMLTableElement;
}

interface QuestionnaireParameters extends TableGridParameters {
    updateUrl: string;
}

export class QuestionnaireGrid {
    private readonly updateUrl: string;
    private readonly dataGrid: DataGrid;

    constructor({ updateUrl, ...options }: QuestionnaireParameters) {
        this.dataGrid = DataGrid.fromHTMLTable(options);
        this.updateUrl = updateUrl;

        this.dataGrid.init();
        new Sortable(this.dataGrid.container, {
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
                        this.dataGrid.rows.map((row, index) => [row.element.dataset.id!, index.toString()]),
                    ),
                }).catch((error: unknown) => {
                    console.error(error);
                    window.alert(window.gettext("The server is not responding."));
                });
            },
        });
    }

    private reorderRow(oldPosition: number, newPosition: number) {
        const displayedRows = this.dataGrid.rows
            .map((row, index) => ({ row, index }))
            .filter(({ row }) => row.isDisplayed);
        this.dataGrid.rows.splice(displayedRows[oldPosition].index, 1);
        this.dataGrid.rows.splice(displayedRows[newPosition].index, 0, displayedRows[oldPosition].row);
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
        super(
            options.storageKey,
            options.sortableHeaders,
            options.container,
            options.searchInput,
            options.resetSearch,
            [],
            undefined,
        );
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
            this.state.rangeFilter.set(name, slider.value);

            slider.onRangeChange = () => {
                this.state.rangeFilter.set(name, slider.value);
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
                .map(element => element.textContent.trim())
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

    protected override readonly defaultOrder: Order = [
        ["name", "asc"],
        ["semester", "asc"],
    ] as const;

    protected reflectFilterStateOnInputs() {
        super.reflectFilterStateOnInputs();
        for (const [name, { checkboxes }] of this.filterCheckboxes.entries()) {
            checkboxes.forEach(checkbox => {
                let isActive;
                if (this.state.equalityFilter.has(name)) {
                    isActive = this.state.equalityFilter.get(name)!.some(filterValue => filterValue === checkbox.value);
                } else {
                    isActive = false;
                }
                checkbox.checked = isActive;
            });
        }
        for (const [name, { slider }] of this.filterSliders.entries()) {
            const filterRange = this.state.rangeFilter.get(name);
            if (filterRange !== undefined) {
                slider.value = filterRange;
            } else {
                slider.reset();
            }
        }
    }
}
