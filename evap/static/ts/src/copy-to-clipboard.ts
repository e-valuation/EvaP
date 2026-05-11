export async function copyHeaders(headers: string[]): Promise<void> {
    await navigator.clipboard.writeText(headers.join("\t"));
}

export async function copyToClipboard(content: string): Promise<void> {
    await navigator.clipboard.writeText(content);
}
