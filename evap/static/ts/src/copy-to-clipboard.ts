function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
}

function copyHeaders(headers: string[]) {
    copyToClipboard(headers.join("\t"));
}
