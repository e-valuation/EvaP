export const selectOrError = <T extends Element>(selectors: string, root: Element | Document = document): T => {
    const elem = root.querySelector<T>(selectors);
    assert(elem, `Element with id ${selectors} not found`);
    return elem;
};

export function assert(condition: unknown, message: string = "Assertion Failed"): asserts condition {
    if (!condition) throw new Error(message);
}

export const sleep = (ms: number): Promise<number> => {
    return new Promise(resolve => window.setTimeout(resolve, ms));
};

export const clamp = (val: number, lowest: number, highest: number) => Math.min(highest, Math.max(lowest, val));
