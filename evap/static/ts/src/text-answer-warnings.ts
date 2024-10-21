function normalize(text: string) {
    return text.toLowerCase().replace(/\s+/g, " ").trim();
}

function isTextMeaningless(text: string): boolean {
    return text.length > 0 && ["", "ka", "na", "none", "keine", "keines", "keiner"].includes(text.replace(/\W/g, ""));
}

function doesTextContainTriggerString(text: string, triggerStrings: string[]): boolean {
    return triggerStrings.some(triggerString => text.includes(triggerString));
}

function updateTextareaWarning(textarea: HTMLTextAreaElement, textAnswerWarnings: string[][]) {
    const text = normalize(textarea.value);

    const matchingWarnings = [];
    if (isTextMeaningless(text)) {
        matchingWarnings.push("meaningless");
    }
    for (const [i, triggerStrings] of textAnswerWarnings.entries()) {
        if (doesTextContainTriggerString(text, triggerStrings)) {
            matchingWarnings.push(`trigger-string-${i}`);
        }
    }

    const showWarning = matchingWarnings.length > 0;
    textarea.classList.toggle("border", showWarning);
    textarea.classList.toggle("border-warning", showWarning);
    const row = textarea.closest(".row")!;

    for (const warning of row.querySelectorAll<HTMLElement>("[data-warning]")) {
        warning.classList.toggle("d-none", !matchingWarnings.includes(warning.dataset.warning!));
    }
}

export function initTextAnswerWarnings(textareas: NodeListOf<HTMLTextAreaElement>, textAnswerWarnings: string[][]) {
    textAnswerWarnings = textAnswerWarnings.map(triggerStrings => triggerStrings.map(normalize));

    textareas.forEach(textarea => {
        let warningDelayTimer: ReturnType<typeof setTimeout>;
        textarea.addEventListener("input", () => {
            clearTimeout(warningDelayTimer);
            warningDelayTimer = setTimeout(() => updateTextareaWarning(textarea, textAnswerWarnings), 300);
        });
        textarea.addEventListener("blur", () => {
            updateTextareaWarning(textarea, textAnswerWarnings);
        });
        updateTextareaWarning(textarea, textAnswerWarnings);
    });
}

export const testable = {
    normalize,
    isTextMeaningless,
    doesTextContainTriggerString,
};
