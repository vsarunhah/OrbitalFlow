import "../styles/globals.css";
import Head from "next/head";
import { CacheProvider } from "@emotion/react";
import createEmotionCache from "../lib/createEmotionCache";
import { getServerEmotionCache } from "../lib/emotionCache";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import Box from "@mui/material/Box";
import { theme } from "../theme";
import { AuthProvider } from "../lib/auth";
import NavBar from "../components/NavBar";
import { useRouter } from "next/router";
import { Analytics } from "@vercel/analytics/next";

const clientSideCache = createEmotionCache();

const PAGE_TITLES = {
  "/": "Dashboard",
  "/jobs": "Jobs",
  "/resumes": "Resumes",
  "/alerts": "Alerts",
  "/analytics": "Analytics",
  "/merge-suggestions": "Merge Suggestions",
  "/recruiters": "Recruiters",
  "/settings": "Settings",
  "/login": "Login",
  "/forgot-password": "Forgot Password",
  "/reset-password": "Reset Password",
};

const PRODUCT_NAME = "OrbitFlow";

function AppContent({ Component, pageProps }) {
  const router = useRouter();
  const showNavBar = router.pathname !== "/login" && router.pathname !== "/forgot-password" && router.pathname !== "/reset-password";
  const pageName = PAGE_TITLES[router.pathname] ?? "OrbitFlow";
  const title = pageName === PRODUCT_NAME ? PRODUCT_NAME : `${pageName} | ${PRODUCT_NAME}`;

  return (
    <>
      <Head>
        <title>{title}</title>
      </Head>
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: "100vh" }}>
        {showNavBar && <NavBar />}
      <Box component="main" sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <Component {...pageProps} />
      </Box>
    </Box>
    </>
  );
}

export default function App(props) {
  const { Component, pageProps } = props;
  const cache = getServerEmotionCache() ?? clientSideCache;
  return (
    <CacheProvider value={cache}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <AppContent Component={Component} pageProps={pageProps} />
        </AuthProvider>
      </ThemeProvider>
      <Analytics />
    </CacheProvider>
  );
}
