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
    private _value: Range = { low: 0, high: 0 };

    private debounceTimeout?: number;

    public constructor(sliderId: string) {
        this.rangeSlider = selectOrError<HTMLDivElement>("#" + sliderId);
        this.lowSlider = selectOrError<HTMLInputElement>("[name=low]", this.rangeSlider);
        this.highSlider = selectOrError<HTMLInputElement>("[name=high]", this.rangeSlider);
        this.minLabel = selectOrError<HTMLSpanElement>(".text-start", this.rangeSlider);
        this.maxLabel = selectOrError<HTMLSpanElement>(".text-end", this.rangeSlider);
        this.rangeLabel = selectOrError<HTMLSpanElement>(".range-values", this.rangeSlider);

        const setValueFromNestedElements = (): void => {
            this.value = { low: parseFloat(this.lowSlider.value), high: parseFloat(this.highSlider.value) };
        };

        this.lowSlider.addEventListener("input", setValueFromNestedElements);
        this.highSlider.addEventListener("input", setValueFromNestedElements);
    }

    public get value(): Range {
        return this._value;
    }

    public set value(value: Range) {
        this._value = value;

        this.lowSlider.value = this.value.low.toString();
        this.highSlider.value = this.value.high.toString();
        if (this.value.low > this.value.high) {
            [this.value.low, this.value.high] = [this.value.high, this.value.low];
        }
        this.rangeLabel.innerText = `${this.value.low} – ${this.value.high}`;

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
            this.updateNestedElements();
            this.reset();
        }
    }

    public reset(): void {
        this.value = { low: this.allowed.low, high: this.allowed.high };
    }

    private updateNestedElements(): void {
        this.lowSlider.min = this.allowed.low.toString();
        this.lowSlider.max = this.allowed.high.toString();
        this.highSlider.min = this.allowed.low.toString();
        this.highSlider.max = this.allowed.high.toString();
        this.minLabel.innerText = this.allowed.low.toString();
        this.maxLabel.innerText = this.allowed.high.toString();
    }
}
