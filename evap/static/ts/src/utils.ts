export const selectOrError = <T extends Element>(elementId: string): T => {
    const elem = document.querySelector<T>(elementId);
    if (elem === null) throw new Error(`Element with id ${elementId} not found`);
    return elem;
};

export const assert = (condition: boolean, message: string = "Assertion Failed") => {
    if (!condition) throw new Error(message);
};

export const sleep = (ms: number) => {
    return new Promise(resolve => setTimeout(resolve, ms));
};
