export const selectOrError = <T extends Element>(selectors: string): T => {
    const elem = document.querySelector<T>(selectors);
    assert(elem, `Element with id ${selectors} not found`);
    return elem;
};

export function assert(condition: unknown, message = "Assertion Failed"): asserts condition {
    if (!condition) throw new Error(message);
}

export const sleep = (ms: number): Promise<number> => {
    return new Promise(resolve => window.setTimeout(resolve, ms));
};
