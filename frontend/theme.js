import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "dark",
    background: {
      default: "#0f1117",
      paper: "#1a1d27",
    },
    primary: {
      main: "#6366f1",
      light: "#818cf8",
    },
    text: {
      primary: "#e4e6ed",
      secondary: "#8b8fa3",
    },
    error: {
      main: "#ef4444",
    },
    divider: "#2e3348",
  },
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: 14,
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: "#0f1117",
          color: "#e4e6ed",
        },
      },
    },
  },
});
