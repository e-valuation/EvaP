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
    private readonly min = 0;
    private max = 0;
    private low = 0;
    private high = 0;

    private debounceTimeout?: number;

    public constructor(sliderId: string) {
        this.rangeSlider = selectOrError<HTMLDivElement>("#" + sliderId);
        this.lowSlider = selectOrError<HTMLInputElement>("[name=low]", this.rangeSlider);
        this.highSlider = selectOrError<HTMLInputElement>("[name=high]", this.rangeSlider);
        this.minLabel = selectOrError<HTMLSpanElement>(".text-start", this.rangeSlider);
        this.maxLabel = selectOrError<HTMLSpanElement>(".text-end", this.rangeSlider);
        this.rangeLabel = selectOrError<HTMLSpanElement>(".range-values", this.rangeSlider);

        const setRangeFromSlider = (): void => {
            this.range = { low: parseFloat(this.lowSlider.value), high: parseFloat(this.highSlider.value) };
        };

        this.lowSlider.addEventListener("input", setRangeFromSlider);
        this.highSlider.addEventListener("input", setRangeFromSlider);
    }

    public get range(): Range {
        return { low: this.low, high: this.high };
    }

    public set range(range: Range) {
        this.low = range.low;
        this.high = range.high;

        this.lowSlider.value = this.low.toString();
        this.highSlider.value = this.high.toString();
        if (this.low > this.high) {
            [this.low, this.high] = [this.high, this.low];
        }
        this.rangeLabel.innerText = `${this.low} – ${this.high}`;

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
        assert(Math.min(...values) >= this.min);
        const max = Math.max(...values);
        if (max > this.max) {
            this.max = max;
            this.updateLimits();
            this.reset();
        }
    }

    public reset(): void {
        this.range = { low: this.min, high: this.max };
    }

    private updateLimits(): void {
        this.lowSlider.min = this.min.toString();
        this.lowSlider.max = this.max.toString();
        this.highSlider.min = this.min.toString();
        this.highSlider.max = this.max.toString();
        this.minLabel.innerText = this.min.toString();
        this.maxLabel.innerText = this.max.toString();
    }
}
