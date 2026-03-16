/**
 * Per-request server emotion cache for SSR.
 * _document sets this before renderPage; _app uses it when present.
 */

let serverCache = null;

export function setServerEmotionCache(cache) {
  serverCache = cache;
}

export function getServerEmotionCache() {
  return serverCache;
}

export function clearServerEmotionCache() {
  serverCache = null;
}
