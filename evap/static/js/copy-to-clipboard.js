function copyToClipboard(str) {
    const el = document.createElement("textarea");
    el.value = str;
    document.body.appendChild(el);
    const selected =
        document.getSelection().rangeCount > 0
            ? document.getSelection().getRangeAt(0)
            : false;
    el.select();
    document.execCommand("copy");
    el.remove();
    if (selected) {
        document.getSelection().removeAllRanges();
        document.getSelection().addRange(selected);
    }
}

function copyHeaders(headers) {
    copyToClipboard(headers.join("\t"));
}
