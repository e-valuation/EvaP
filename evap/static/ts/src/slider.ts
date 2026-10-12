import { assert, clamp, selectOrError } from "./utils.js";

export interface Range {
    low: number;
    high: number;
    isOpenEnd?: boolean;
}

const RANGE_DEBOUNCE_MS = 100.0;

export class RangeSlider {
    public readonly lowSlider: HTMLInputElement;
    public readonly highSlider: HTMLInputElement;

    private readonly rangeSlider: HTMLDivElement;
    private readonly maxLabel: HTMLSpanElement;
    private readonly minLabel: HTMLSpanElement;
    private readonly rangeLabel: HTMLSpanElement;
    private readonly allowed: Range;
    private _value: Range = { low: 0, high: 0 };

    private debounceTimeout?: ReturnType<typeof setTimeout>;

    public constructor(sliderId: string, maxValue: number) {
        this.rangeSlider = selectOrError<HTMLDivElement>("#" + sliderId);
        this.lowSlider = selectOrError<HTMLInputElement>("[name=low]", this.rangeSlider);
        this.highSlider = selectOrError<HTMLInputElement>("[name=high]", this.rangeSlider);
        this.minLabel = selectOrError<HTMLSpanElement>(".text-start", this.rangeSlider);
        this.maxLabel = selectOrError<HTMLSpanElement>(".text-end", this.rangeSlider);
        this.rangeLabel = selectOrError<HTMLSpanElement>(".range-values", this.rangeSlider);
        this.allowed = { low: 0, high: maxValue };
        this.updateNestedElements();
        this.reset();

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
        this._value = {
            low: clamp(value.low, this.allowed.low, this.allowed.high),
            high: clamp(value.high, this.allowed.low, this.allowed.high),
        };

        this.lowSlider.value = this.value.low.toString();
        this.highSlider.value = this.value.high.toString();
        if (this.value.low > this.value.high) {
            [this.value.low, this.value.high] = [this.value.high, this.value.low];
        }
        this.value.isOpenEnd = this.value.high === this.allowed.high;
        this.rangeLabel.innerText = `${this.value.low} – ${this.formatHigh(this.value.high)}`;

        // debounce on range change callback
        if (this.debounceTimeout !== undefined) {
            clearTimeout(this.debounceTimeout);
        }
        this.debounceTimeout = setTimeout(() => {
            this.onRangeChange();
        }, RANGE_DEBOUNCE_MS);
    }

    public onRangeChange(): void {}

    public assertNotBelowMin(values: number[]): void {
        assert(Math.min(...values) >= this.allowed.low);
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
        this.maxLabel.innerText = this.formatHigh(this.allowed.high);
    }

    private formatHigh(value: number): string {
        return value === this.allowed.high ? `${value}+` : value.toString();
    }
}
