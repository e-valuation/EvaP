export async function copyHeaders(headers: string[]): Promise<void> {
    await navigator.clipboard.writeText(headers.join("\t"));
}
