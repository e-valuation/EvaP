export function expectElementById<HTMLElementType extends HTMLElement>(elementId: string): HTMLElementType {
    let elem = document.getElementById(elementId);
    if (elem === null) throw new Error(`Element with id ${elementId} not found`);
    return elem as HTMLElementType;
}

export function assert(condition: boolean) {
    if (!condition) throw new Error("Assertion Failed!");
}

export function sleep(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
