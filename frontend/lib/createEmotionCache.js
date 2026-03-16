import createCache from "@emotion/cache";

const isBrowser = typeof document !== "undefined";

/**
 * Create an Emotion cache for MUI that works with Next.js Pages Router.
 * Uses a meta tag for insertion point when available to avoid style order issues.
 */
export default function createEmotionCache() {
  let insertionPoint;

  if (isBrowser) {
    const emotionInsertionPoint = document.querySelector(
      'meta[name="emotion-insertion-point"]'
    );
    insertionPoint = emotionInsertionPoint ?? undefined;
  }

  return createCache({ key: "mui-style", insertionPoint });
}
