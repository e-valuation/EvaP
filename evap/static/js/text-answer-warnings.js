function normalize(string) {
    return string.toLowerCase().replace(/\s{2,}/g, " ").trim();
}

function isTextMeaningless(text) {
    return text.length > 0 && ["", "ka", "na"].includes(text.replace(/\W/g,''));
}

function doesTextContainTriggerString(text, triggerStrings) {
    return triggerStrings.some(triggerString => text.includes(triggerString));
}

function updateTextareaWarning(textarea, textAnswerWarnings) {
    const text = normalize(textarea.val());

    let matchingWarnings = [];
    if (isTextMeaningless(text)) {
        matchingWarnings.push("meaningless");
    }
    for (const [i, triggerStrings] of textAnswerWarnings.entries()) {
        if (doesTextContainTriggerString(text, triggerStrings)) {
            matchingWarnings.push(`trigger-string-${i}`);
        }
    }

    const showWarning = matchingWarnings.length > 0;
    const row = textarea.parents(".row");
    textarea.toggleClass('border border-warning', showWarning);

    row.find("[data-warning]").addClass("d-none");
    for (const matchingWarning of matchingWarnings) {
        row.find(`[data-warning=${matchingWarning}]`).removeClass('d-none');
    }
}

export function initTextAnswerWarnings(textareas, textAnswerWarnings) {
    textAnswerWarnings = textAnswerWarnings.map(triggerStrings => triggerStrings.map(normalize));

    let warningDelayTimer;
    textareas.on("input", function() {
        clearTimeout(warningDelayTimer);
        warningDelayTimer = setTimeout(() => updateTextareaWarning($(this), textAnswerWarnings), 300);
    });
    textareas.blur(function() {
        updateTextareaWarning($(this), textAnswerWarnings);
    });
    textareas.each(function() {
        updateTextareaWarning($(this), textAnswerWarnings);
    });
}
