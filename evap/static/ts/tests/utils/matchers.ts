import { ElementHandle } from "puppeteer";
import MatcherUtils = jest.MatcherUtils;

declare global {
    namespace jest {
        interface Matchers<R> {
            toBeChecked(): Promise<R>;
            toHaveClass(className: string): Promise<R>;
        }
    }
}

function createTagDescription(element: ElementHandle): Promise<string> {
    return element.evaluate(element => {
        let tagDescription = element.tagName.toLowerCase();
        if (element.id) {
            tagDescription += ` id="${element.id}"`;
        }
        if (element.className) {
            tagDescription += ` class="${element.className}"`;
        }
        return `<${tagDescription}>`;
    });
}

async function createElementMessage(
    this: MatcherUtils,
    matcherName: string,
    expectation: string,
    element: ElementHandle,
    value?: any,
): Promise<() => string> {
    const tagDescription = await createTagDescription(element);
    return () => {
        const optionallyNot = this.isNot ? "not " : "";
        const receivedLine = value ? `\nReceived: ${this.utils.printReceived(value)}` : "";
        return (
            this.utils.matcherHint(matcherName, undefined, undefined, { isNot: this.isNot }) +
            "\n\n" +
            `Expected ${this.utils.RECEIVED_COLOR(tagDescription)} to ${optionallyNot}${expectation}` +
            receivedLine
        );
    };
}

expect.extend({
    async toBeChecked(received: ElementHandle): Promise<jest.CustomMatcherResult> {
        const pass = await received.evaluate(element => {
            return (element as HTMLInputElement).checked;
        });
        const message = await createElementMessage.call(this, "toBeChecked", "be checked", received);
        return { message, pass };
    },

    async toHaveClass(received: ElementHandle, className: string): Promise<jest.CustomMatcherResult> {
        const classList = await received.evaluate(element => {
            return [...element.classList];
        });
        const pass = classList.includes(className);
        const message = await createElementMessage.call(
            this,
            "toHaveClass",
            `have the class ${this.utils.printExpected(className)}`,
            received,
            classList,
        );

        return { message, pass };
    },
});
