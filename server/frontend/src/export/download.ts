/**
 * Browser file download, shared by every export path.
 *
 * Previously duplicated three times (csvExport, sessionLog, InvestigationGraph),
 * each copy revoking the object URL synchronously after `click()`. That races
 * the download: Firefox and Safari resolve the blob asynchronously, so the
 * revoke can land first and the file arrives empty. Revoking on the next macro
 * task lets the navigation start before the URL is released.
 */
export function download(filename: string, content: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** `download` with the JSON mime type and `JSON.stringify` already applied. */
export function downloadJson(filename: string, payload: unknown): void {
  download(filename, JSON.stringify(payload, null, 2), "application/json");
}
