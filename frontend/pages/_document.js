import Document, { Html, Head, Main, NextScript } from "next/document";
import createEmotionServer from "@emotion/server/create-instance";
import createEmotionCache from "../lib/createEmotionCache";
import {
  setServerEmotionCache,
  clearServerEmotionCache,
} from "../lib/emotionCache";
import { CacheProvider } from "@emotion/react";

export default function MyDocument(props) {
  const { emotionStyleTags } = props;
  return (
    <Html lang="en">
      <Head>
        <meta name="emotion-insertion-point" content="" />
        <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
        <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
        <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
        <link rel="icon" type="image/png" sizes="192x192" href="/android-chrome-192x192.png" />
        <link rel="icon" type="image/png" sizes="512x512" href="/android-chrome-512x512.png" />
        {emotionStyleTags}
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}

MyDocument.getInitialProps = async (ctx) => {
  const originalRenderPage = ctx.renderPage;
  const cache = createEmotionCache();
  setServerEmotionCache(cache);
  const { extractCriticalToChunks } = createEmotionServer(cache);

  try {
    ctx.renderPage = () =>
      originalRenderPage({
        enhanceApp: (App) =>
          function EnhancedApp(props) {
            return (
              <CacheProvider value={cache}>
                <App {...props} />
              </CacheProvider>
            );
          },
      });

    const initialProps = await Document.getInitialProps(ctx);
    const chunks = extractCriticalToChunks(initialProps.html);
    const emotionStyleTags = chunks.styles.map((style) => (
      <style
        key={style.key}
        data-emotion={`${style.key} ${style.ids.join(" ")}`}
        dangerouslySetInnerHTML={{ __html: style.css }}
      />
    ));

    return {
      ...initialProps,
      emotionStyleTags,
    };
  } finally {
    clearServerEmotionCache();
  }
};
