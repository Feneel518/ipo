const LAST_VIEWED_IPO_KEY = "ipo-milega:last-viewed-ipo";
const LAST_VIEWED_IPO_EVENT = "ipo-milega:last-viewed-ipo-change";
const DIRECTORY_FALLBACK = "/ipos";

function isIpoRecordPath(value: string | null): value is string {
  return value?.startsWith("/ipo/") ?? false;
}

export function getLastViewedIpo() {
  const savedRecord = window.localStorage.getItem(LAST_VIEWED_IPO_KEY);
  return isIpoRecordPath(savedRecord) ? savedRecord : DIRECTORY_FALLBACK;
}

export function getLastViewedIpoFallback() {
  return DIRECTORY_FALLBACK;
}

export function rememberIpo(slug: string) {
  window.localStorage.setItem(LAST_VIEWED_IPO_KEY, `/ipo/${encodeURIComponent(slug)}`);
  window.dispatchEvent(new Event(LAST_VIEWED_IPO_EVENT));
}

export function subscribeToLastViewedIpo(onChange: () => void) {
  const handleStorage = (event: StorageEvent) => {
    if (event.key === LAST_VIEWED_IPO_KEY) onChange();
  };

  window.addEventListener("storage", handleStorage);
  window.addEventListener(LAST_VIEWED_IPO_EVENT, onChange);

  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(LAST_VIEWED_IPO_EVENT, onChange);
  };
}
