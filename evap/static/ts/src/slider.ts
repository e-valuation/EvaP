import { assert, selectOrError } from "./utils.js";

export interface Range {
    low: number;
    high: number;
}

const RANGE_DEBOUNCE_MS = 100.0;

export class RangeSlider {
    public readonly lowSlider: HTMLInputElement;
    public readonly highSlider: HTMLInputElement;

    private readonly rangeSlider: HTMLDivElement;
    private readonly maxLabel: HTMLSpanElement;
    private readonly minLabel: HTMLSpanElement;
    private readonly rangeLabel: HTMLSpanElement;
    private allowed: Range = { low: 0, high: 0 };
    private _selection: Range = { low: 0, high: 0 };

    private debounceTimeout?: number;

    public constructor(sliderId: string) {
        this.rangeSlider = selectOrError<HTMLDivElement>("#" + sliderId);
        this.lowSlider = selectOrError<HTMLInputElement>("[name=low]", this.rangeSlider);
        this.highSlider = selectOrError<HTMLInputElement>("[name=high]", this.rangeSlider);
        this.minLabel = selectOrError<HTMLSpanElement>(".text-start", this.rangeSlider);
        this.maxLabel = selectOrError<HTMLSpanElement>(".text-end", this.rangeSlider);
        this.rangeLabel = selectOrError<HTMLSpanElement>(".range-values", this.rangeSlider);

        const setRangeFromSlider = (): void => {
            this.selection = { low: parseFloat(this.lowSlider.value), high: parseFloat(this.highSlider.value) };
        };

        this.lowSlider.addEventListener("input", setRangeFromSlider);
        this.highSlider.addEventListener("input", setRangeFromSlider);
    }

    public get selection(): Range {
        return this._selection;
    }

    public set selection(selection: Range) {
        this._selection = selection;

        this.lowSlider.value = this.selection.low.toString();
        this.highSlider.value = this.selection.high.toString();
        if (this.selection.low > this.selection.high) {
            [this.selection.low, this.selection.high] = [this.selection.high, this.selection.low];
        }
        this.rangeLabel.innerText = `${this.selection.low} – ${this.selection.high}`;

        // debounce on range change callback
        if (this.debounceTimeout !== undefined) {
            clearTimeout(this.debounceTimeout);
        }
        this.debounceTimeout = setTimeout(() => {
            this.onRangeChange();
        }, RANGE_DEBOUNCE_MS);
    }

    public onRangeChange(): void {}

    public includeValues(values: number[]): void {
        assert(Math.min(...values) >= this.allowed.low);
        const max = Math.max(...values);
        if (max > this.allowed.high) {
            this.allowed.high = max;
            this.updateLimits();
            this.reset();
        }
    }

    public reset(): void {
        this.selection = { low: this.allowed.low, high: this.allowed.high };
    }

    private updateLimits(): void {
        this.lowSlider.min = this.allowed.low.toString();
        this.lowSlider.max = this.allowed.high.toString();
        this.highSlider.min = this.allowed.low.toString();
        this.highSlider.max = this.allowed.high.toString();
        this.minLabel.innerText = this.allowed.low.toString();
        this.maxLabel.innerText = this.allowed.high.toString();
    }
}
