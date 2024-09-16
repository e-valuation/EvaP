import { selectOrError } from "./utils.js";

export interface Range {
    low: number;
    high: number;
}

export class RangeSlider {
    public readonly lowSlider: HTMLInputElement;
    public readonly highSlider: HTMLInputElement;

    private readonly rangeSlider: HTMLDivElement;
    private readonly maxLabel: HTMLSpanElement;
    private readonly minLabel: HTMLSpanElement;
    private readonly rangeLabel: HTMLSpanElement;
    private readonly min: number = 0;
    private max = 0;
    private low = 0;
    private high = 0;

    public constructor(sliderId: string) {
        this.rangeSlider = selectOrError<HTMLDivElement>("#" + sliderId);
        this.lowSlider = selectOrError<HTMLInputElement>("[name=low]", this.rangeSlider);
        this.highSlider = selectOrError<HTMLInputElement>("[name=high]", this.rangeSlider);
        this.minLabel = selectOrError<HTMLSpanElement>(".text-start", this.rangeSlider);
        this.maxLabel = selectOrError<HTMLSpanElement>(".text-end", this.rangeSlider);
        this.rangeLabel = selectOrError<HTMLSpanElement>(".range-values", this.rangeSlider);

        const updateFromSlider = (): void => {
            this.low = parseFloat(this.lowSlider.value);
            this.high = parseFloat(this.highSlider.value);
            this.updateRange();
        };

        this.lowSlider.addEventListener("input", updateFromSlider);
        this.highSlider.addEventListener("input", updateFromSlider);
    }

    public get range(): Range {
        return { low: this.low, high: this.high };
    }

    public set range(range: Range) {
        this.low = range.low;
        this.high = range.high;
        this.updateRange();
    }

    public onRangeChange(): void {}

    public includeValues(values: number[]): void {
        const max = Math.max(...values);
        if (max > this.max) {
            this.max = max;
            this.updateLimits();
            this.reset();
        }
    }

    public reset(): void {
        this.range = { low: this.min, high: this.max };
        this.lowSlider.value = this.low.toString();
        this.highSlider.value = this.high.toString();
        this.updateRange();
    }

    private updateRange(): void {
        if (this.low > this.high) {
            const tmp = this.low;
            this.low = this.high;
            this.high = tmp;
        }
        this.rangeLabel.innerText = `${this.low} – ${this.high}`;
        this.onRangeChange();
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
