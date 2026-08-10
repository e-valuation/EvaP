import { Range, RangeSlider } from "./slider.js";
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
}

class DataGrid {
    // TODO: split into LegacyDataGrid & DataGrid for faster integration
    private _rows?: Row[];
    private delayTimer: number | undefined;
    protected state: State = {
        equalityFilter: new Map<string, string[]>(),
        rangeFilter: new Map<string, Range>(),
        search: "",
        order: this.defaultOrder,
    };
    private _setSearchValue: (newSearchValue: any) => void = _ => {};

    protected constructor(
        private readonly storageKey: string,
        protected readonly sortableHeaders: Map<string, HTMLElement>,
        public readonly container: HTMLElement,
        private readonly getRowElements: () => HTMLElement[] = () => [...this.container.children] as HTMLElement[],
        protected readonly defaultOrder: Order = [],
    ) {}

    public get rows() {
        this._rows ??= this.fetchRows(this.getRowElements());
        return this._rows;
    }

    public static buildSortableHeadersMap(headerContainer: HTMLElement): Map<string, HTMLElement> {
        const sortableHeaders = new Map<string, HTMLElement>();
        for (const orderElement of headerContainer.querySelectorAll<HTMLElement>(".col-order")) {
            sortableHeaders.set(orderElement.dataset.col!, orderElement);
        }
        return sortableHeaders;
    }

    // Table based data grid which uses its head and body
    public static fromHTMLTable({ table, storageKey }: BaseParameters & { table: HTMLTableElement }): DataGrid {
        const thead = selectOrError<HTMLTableSectionElement>("thead", table);
        const tbody = selectOrError<HTMLTableSectionElement>("tbody", table);

        const sortableHeaders = DataGrid.buildSortableHeadersMap(thead);

        const [firstColumn] = sortableHeaders.keys();

        return new DataGrid(
            storageKey,
            sortableHeaders,
            tbody,
            () => [...tbody.children] as HTMLElement[],
            firstColumn ? [[firstColumn, "asc"]] : [],
        );
    }

    public static fromCSSGridTable({
        gridContainer,
        storageKey,
        gridHeader,
        defaultOrder,
    }: {
        gridContainer: HTMLElement;
        gridHeader?: HTMLElement;
        defaultOrder?: Order;
    } & BaseParameters): DataGrid {
        const head: HTMLElement = gridHeader ?? selectOrError(".gridHeader", gridContainer);

        return new DataGrid(
            storageKey,
            this.buildSortableHeadersMap(head),
            gridContainer,
            () =>
                [...gridContainer.children].filter(
                    row => !row.classList.contains("gridHeader") && !row.classList.contains("empty-disclaimer"),
                ) as HTMLElement[],
            defaultOrder,
        );
    }

    private static createBadgePill(count: number): HTMLElement {
        const badgeClass = count === 0 ? "badge-btn-zero" : "badge-btn";
        const pill = document.createElement("span");
        pill.classList.add("badge", "rounded-pill", badgeClass);
        pill.textContent = count.toString();
        return pill;
    }

    public bindCheckboxFilterButtons(filterCategory: string, filterButtons: HTMLInputElement[]): this {
        const _filterButtons = new Map<string, Map<string, HTMLInputElement>>();
        for (const filterButton of filterButtons) {
            const buttonFilterCategory = filterButton.dataset.filterCategory;
            const filterValue = filterButton.dataset.filterValue;

            if (!buttonFilterCategory || !filterValue) {
                console.error("Filter buttons need both data-filter-value and data-filter-category!", filterButton);
                continue;
            }

            if (buttonFilterCategory !== filterCategory) {
                console.error(
                    `Equality filters need to be of the same category! Expected ${filterCategory}, got ${buttonFilterCategory}. Skipping button...`,
                    filterButton,
                );
                continue;
            }

            filterButton.addEventListener("input", () => {
                if (filterButton.checked) {
                    this.addEqualityFilter(filterCategory, filterValue);
                } else {
                    this.removeEqualityFeature(filterCategory, filterValue);
                }
            });

            // TODO: how to rebind inputs?
            _filterButtons
                .getOrInsert(filterCategory, new Map<string, HTMLInputElement>())
                .set(filterValue, filterButton);
        }

        return this;
    }

    // TODO: refactor buttons to inputs with type radio
    public bindRadioFilterButtons(filterButtons: HTMLButtonElement[]) {
        for (const filterButton of filterButtons) {
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
                    this.removeEqualityFeature(filterCategory, filterValue);
                } else {
                    // TODO: multi filter
                    filterButtons.forEach(b => b.classList.remove("active"));
                    this.clearEqualityFilter(filterCategory);
                    filterButton.classList.add("active");
                    this.addEqualityFilter(filterCategory, filterValue);
                }
            });
        }
        return this;
    }

    public bindSearchField(searchInput: HTMLInputElement, resetSearchButton?: HTMLButtonElement): this {
        this._setSearchValue = function (newSearchValue: string) {
            searchInput.value = newSearchValue;
        };

        searchInput.addEventListener("input", () => {
            clearTimeout(this.delayTimer);
            this.delayTimer = window.setTimeout(() => {
                this.state.search = searchInput.value;
                this.filterRows();
                this.renderToDOM();
            }, 200);
        });
        searchInput.addEventListener("keypress", event => {
            // after enter, unfocus the search input to collapse the screen keyboard
            if (event.key === "enter") {
                searchInput.blur();
            }
        });
        resetSearchButton?.addEventListener("click", () => {
            this.state.search = "";
            this.filterRows();
            this.renderToDOM();
            this.reflectFilterStateOnInputs();
        });

        return this;
    }

    public bindRangeFilterSlider(filterCategory: string, rangeSliderElement: HTMLElement): this {
        const minInput = rangeSliderElement.querySelector("input[name=low]");
        const maxInput = rangeSliderElement.querySelector("input[name=high]");
        if (!(minInput && maxInput)) {
            console.error('Range slider is missing "low" or "high" input.', rangeSliderElement);
            return this;
        }

        const slider = new RangeSlider(rangeSliderElement);

        this.state.rangeFilter.set(filterCategory, slider.value);
        slider.onRangeChange = () => {
            this.state.rangeFilter.set(filterCategory, slider.value);
            // TODO: actually apply range filter
            // TODO: use filter-category and filter value
            // TODO: change html to use filter-category=participants
            this.filterRows();
            this.renderToDOM();
        };

        return this;
    }

    // TODO: think about using separate builder class

    public init() {
        this.restoreStateFromStorage();
        this.reflectFilterStateOnInputs();
        this.filterRows();
        this.sortRows();
        this.bindEvents();
        this.renderToDOM();
        return this;
    }

    private addEqualityFilter(filterCategory: string, filterValue: string) {
        const filterList = this.state.equalityFilter.get(filterCategory) ?? [];
        if (!filterList.some(v => v === filterValue)) {
            filterList.push(filterValue);
        }
        this.state.equalityFilter.set(filterCategory, filterList);
        this.filterRows();
        this.renderToDOM();
    }

    private removeEqualityFeature(filterCategory: string, filterValue: string) {
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

    private clearEqualityFilter(filterCategory: string) {
        this.state.equalityFilter.delete(filterCategory);
    }

    private filterRow(row: Row): boolean {
        return [...this.state.equalityFilter].every(
            ([filterCategory, filterValues]) =>
                filterValues.length == 0 ||
                filterValues.some(
                    filterValue =>
                        row.filterValues.get(filterCategory)?.some(rowValue => rowValue === filterValue) ?? true,
                ),
        );
    }

    public bindResetFilterButton(resetFilterButton: HTMLButtonElement): this {
        resetFilterButton.addEventListener("click", () => {
            this.state.equalityFilter.clear();
            this.state.search = "";
            this.state.rangeFilter.clear();
            this.filterRows();
            this.renderToDOM();
            this.reflectFilterStateOnInputs();
        });
        return this;
    }

    protected bindEvents() {
        this.delayTimer = undefined;

        for (const [column, header] of this.sortableHeaders) {
            header.addEventListener("click", () => {
                // The first click order the column ascending. All following clicks toggle the order.
                const ordering = header.classList.contains("col-order-asc") ? "desc" : "asc";
                this.sort([[column, ordering]]);
            });
        }
    }


    private fetchRows(_rowElements: HTMLElement[]): Row[] {
        // eslint-disable-next-line @typescript-eslint/no-unsafe-return
        return null as any;
        // const rows = rowElements.map(row => {
        //     const searchWords = this.findSearchableCells(row).flatMap(element =>
        //         DataGrid.searchWordsOf(element.textContent),
        //     );
        //     return {
        //         element: row,
        //         searchWords,
        //         filterValues: this.fetchRowFilterValues(row),
        //         orderValues: this.fetchRowOrderValues(row),
        //     } as Row;
        // });
        // for (const column of this.sortableHeaders.keys()) {
        //     const orderValues = rows.map(row => row.orderValues.get(column) as string);
        //     const isNumericalColumn = orderValues.every(orderValue => DataGrid.NUMBER_REGEX.test(orderValue));
        //     if (isNumericalColumn) {
        //         rows.forEach(row => {
        //             const numberString = (row.orderValues.get(column) as string).replace(",", ".");
        //             row.orderValues.set(column, parseFloat(numberString));
        //         });
        //     }
        // }
        // return rows;
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


    static searchWordsOf(string: string): string[] {
        const searchWords = string.toLowerCase().trim().split(/\s+/);
        return searchWords;
    }

    // Filters rows respecting the current search string and filters by their searchWords and filterValues
    protected filterRows() {
        const searchWords = DataGrid.searchWordsOf(this.state.search);
        for (const row of this.rows) {
            const isDisplayedBySearch = () =>
                searchWords.every(searchWord => row.searchWords.some(rowWord => rowWord.includes(searchWord)));
            const isDisplayedByEqualityFilters = () => this.filterRow(row);
            const isDisplayedByRangeFilters = () =>
                [...this.state.rangeFilter].every(([name, bound]) =>
                    row.filterValues
                        .get(name)
                        ?.map(rawValue => parseFloat(rawValue))
                        .some(rowValue => rowValue >= bound.low && rowValue <= bound.high),
                );
            row.isDisplayed = isDisplayedBySearch() && isDisplayedByEqualityFilters() && isDisplayedByRangeFilters();
        }
    }

    protected sort(order: [string, "asc" | "desc"][]) {
        this.state.order = order;
        this.sortRows()
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

    private restoreStateFromStorage(): void {
        // TODO: I believe this can break if there is the old data in localStorage?
        const stored = JSON.parse(localStorage.getItem(this.storageKey)!) ?? {};

        // set previous equality filters, if they exist
        try {
            const previousEqualityFilter = new Map<string, string[]>(stored.equalityFilter);
            for (const previousFilterCategory in previousEqualityFilter) {
                if (this.state.equalityFilter.get(previousFilterCategory)) {
                    this.state.equalityFilter.set(
                        previousFilterCategory,
                        previousEqualityFilter.get(previousFilterCategory)!,
                    );
                }
            }
        } catch (e) {
            console.warn("Could not restore previous equality filter from:", stored, e);
        }

        this.state = {
            ...this.state,
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
        this._setSearchValue(this.state.search);
        // TODO: how to reflect onto filter buttons?
        /*
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
         */
    }
}

export default DataGrid

interface DataProvider<R> {
    fetchRows: () => R[];
}

interface Renderer<R> {
    render: (rows: R[]) => void;
}

interface Filter<R> extends EventTarget {
    isDisplayed: (r: R) => boolean;
    addCountBadges?: (rows: R[]) => void;
}

interface GridSorter<R> extends EventTarget {
    sortFn: (a: R, b: R) => number;
}

class _DataGrid<R> {
    constructor(
        private readonly dataProvider: DataProvider<R>,
        private readonly filters: Filter<R>[],
        private readonly sorter: GridSorter<R>,
        private readonly renderer: Renderer<R>,
    ) {
        this.sorter.addEventListener('sort', () => this.update())
        for (const filter of this.filters) {
            filter.addEventListener('filter', () => this.update())
        }

        this.update();
    }

    private update() {
        let rows: R[] = this.dataProvider.fetchRows();
        rows.sort((a,b) => this.sorter.sortFn(a,b));
        for (const filter of this.filters) {
            rows = rows.filter((row) => filter.isDisplayed(row));
        }
        this.renderer.render(rows);
    }
}

// TODO: serialization strategy

export class DataGridBuilder<R> {
    private readonly dataProvider: DataProvider<R> | undefined;
    private filters: Filter<R>[] = [];
    private sorter: GridSorter<R> | undefined;
    private renderer: Renderer<R> | undefined;

    constructor(dataProvider: DataProvider<R>) {
        this.dataProvider = dataProvider;
    }

    addSorter(gridSorter: GridSorter<R>): this {
        this.sorter = gridSorter;

        return this;
    }

    addFilter(filter: Filter<R>): this {
        this.filters.push(filter)

        if(filter.addCountBadges) {
            const rows = this.dataProvider?.fetchRows();
            if(!rows) {
                throw new Error("This filter has to be added after a data provider")
            }
            filter.addCountBadges(rows);
        }

        return this;
    }

    addRendererAndBuild(renderer: Renderer<R>): _DataGrid<R> {
        this.renderer = renderer;
        if (!this.dataProvider || !this.sorter) {
            throw new Error("DataGrid needs at least a DataProvider, GridSorter and Renderer.");
        }

        return new _DataGrid(this.dataProvider, this.filters, this.sorter, this.renderer);
    }
}

interface MyRow {
    element: HTMLElement;
    orderValues: Map<string, string>;
    filterValues: Map<string, string[]>;
}

function fetchOrderValues(element: HTMLElement): Map<string, string> {
    const orderCells = element.querySelectorAll<HTMLElement>("[data-order]");
    return new Map(
        orderCells.values().map(cell => {
            const column = cell.dataset.col;
            if (!column) {
                throw new Error("Cells using data-order need to specify data-col");
            }
            const orderValue = cell.dataset.order ?? cell.innerHTML.trim();
            return [column, orderValue];
        }),
    );
}

function fetchFilterValues(element: HTMLElement): Map<string,string[]> {
    const filterableCells = [...element.querySelectorAll<HTMLElement>("[data-filter-category]")];
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

export class CSSGridTable implements DataProvider<MyRow>, Renderer<MyRow> {
    private readonly rowElements: HTMLElement[];
    constructor(public readonly gridContainer: HTMLElement) {

        this.rowElements = this.fetchRowElements();
    }

    private fetchRowElements(): HTMLElement[] {
        return [...this.gridContainer.children].filter(
            row => !row.classList.contains("gridHeader") && !row.classList.contains("empty-disclaimer"),
        ) as HTMLElement[];
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-private-class-members
    private findSearchableCells(row: HTMLElement): HTMLElement[] {
        const elements = [...row.children] as HTMLElement[];
        return elements.filter(element => !element.hasAttribute("data-not-searchable"));
    }

    fetchRows(): MyRow[] {
        return this.rowElements.map(row => {
            const orderValues = fetchOrderValues(row);
            const filterValues = fetchFilterValues(row);
            return { element: row, orderValues, filterValues };
        });
    }

    render(rows: MyRow[]): void {
        const headerRow = this.gridContainer.querySelector<HTMLElement>(".gridHeader")!;
        this.gridContainer.replaceChildren(headerRow, ...rows.map(r => r.element));
    }
}

export class CSSGridSorter extends EventTarget implements GridSorter<MyRow> {
    private readonly sortableHeaders: Map<string, HTMLElement>;
    public order: Order;

    constructor(sortButtons: NodeListOf<HTMLElement>, defaultOrder?: Order) {
        super()
        this.sortableHeaders = new Map(
            [...sortButtons].map(btn => {
                const sortKey = btn.dataset.col;
                if (!sortKey) {
                    throw new Error("SortButtons need a 'data-col' attribute!");
                }
                return [sortKey, btn];
            }),
        );

        const firstSortKey = this.sortableHeaders.keys().next().value;
        this.order = defaultOrder ?? (firstSortKey ? [[firstSortKey, "asc"]] : []);

        for (const [column, header] of this.sortableHeaders) {
            header.classList.remove("col-order-asc", "col-order-desc")
            if (column === this.order[0][0]) {
                header.classList.add(`col-order-${this.order[0][1]}`)
            }
            header.addEventListener("click", () => this.handleSortClick(column));
        }
    }

    private handleSortClick(category: string) {
        const sortButton = this.sortableHeaders.get(category);
        if(!sortButton) {
            // Silently ignore non-existing columns: They were probably renamed.
            // A correct state will be built the next time the user sorts the datagrid.
            console.error(`Unknown sort category: ${category}. Not one of`, this.sortableHeaders.keys())
            return;
        }

        // The first click order the column ascending. All following clicks toggle the order.
        const ordering = sortButton.classList.contains("col-order-asc") ? "desc" : "asc";
        this.order = [[category, ordering]]

        for (const header of this.sortableHeaders.values()) {
            header.classList.remove("col-order-asc", "col-order-desc");
        }

        sortButton.classList.add(`col-order-${ordering}`)

        // this.sort([[column, ordering]]);
        this.dispatchEvent(new CustomEvent('sort'))
    }

    sortFn(a: MyRow, b: MyRow): number {
        const collator = new Intl.Collator(document.documentElement.lang, { caseFirst: "false" });
        for (const [column, order] of this.order) {
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
    }
}

export class RadioButtonFilter extends EventTarget implements Filter<MyRow> {
    private allowedValue: string | undefined;
    private readonly filterButtons: HTMLElement[];

    constructor(private filterCategory: string, filterButtons: NodeListOf<HTMLElement>) {
        super();

        this.allowedValue = undefined;
        this.filterButtons = [...filterButtons];

        for (const filterButton of this.filterButtons) {
            const filterValue = filterButton.dataset.filterValue;

            if (!filterValue) {
                console.error("Filter buttons need data-filter-value!", filterButton);
                return;
            }

            filterButton.addEventListener("click", () => {
                if (filterButton.classList.contains("active")) {
                    filterButton.classList.remove("active");
                    this.allowedValue = undefined;
                } else {
                    filterButtons.forEach(b => b.classList.remove("active"));
                    filterButton.classList.add("active");
                    this.allowedValue = filterValue;
                }
                this.dispatchEvent(new CustomEvent("filter"))
            });
        }
    }

    private static createBadgePill(count: number): HTMLElement {
        const badgeClass = count === 0 ? "badge-btn-zero" : "badge-btn";
        const pill = document.createElement("span");
        pill.classList.add("badge", "rounded-pill", badgeClass);
        pill.textContent = count.toString();
        return pill;
    }

    addCountBadges(rows: MyRow[]) {
        for (const filterButton of this.filterButtons) {
            const filterValue = filterButton.dataset.filterValue!;

            const count = rows.filter(RadioButtonFilter.filter.bind(undefined, this.filterCategory, filterValue)).length
            filterButton.append(RadioButtonFilter.createBadgePill(count))
        }
    }

    private static filter(filterCategory: string, filterValue: string,row : MyRow) : boolean {
        return row.filterValues.get(filterCategory)?.includes(filterValue) ?? false;
    }

    isDisplayed(row: MyRow): boolean {
        if (!this.allowedValue) {return true;}

        return RadioButtonFilter.filter(this.filterCategory, this.allowedValue, row)
    }
}

export class SearchFilter extends EventTarget implements Filter<MyRow> {
    // TODO: search filter
    constructor(private readonly searchField: HTMLInputElement, private readonly resetSearchButton?: HTMLElement ) {
        super();

    }
}