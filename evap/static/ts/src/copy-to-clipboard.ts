function copyToClipboard(text: string) {
    const selection = document.getSelection()!;
    const el = document.createElement("textarea");
    el.value = text;
    document.body.appendChild(el);
    const selected = selection.rangeCount > 0 ? selection.getRangeAt(0) : false;
    el.select();
    // eslint-disable-next-line @typescript-eslint/no-deprecated
    document.execCommand("copy"); // required by puppeteer tests
    el.remove();
    if (selected) {
        selection.removeAllRanges();
        selection.addRange(selected);
    }
}

function copyHeaders(headers: string[]) {
    copyToClipboard(headers.join("\t"));
}
