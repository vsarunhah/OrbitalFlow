import { useMemo } from "react";
import Box from "@mui/material/Box";
import { sanitizeEmailHtml } from "./email";

const readingLightSx = {
  bgcolor: "#ffffff",
  border: "1px solid rgba(0,0,0,0.12)",
  borderRadius: 1,
  p: 2,
  color: "rgba(0,0,0,0.87)",
  "& a": { color: "#0d47a1" },
  "& a:visited": { color: "#6a1b9a" },
};

export default function EmailBody({ html, text, sx, readingLight = false }) {
  const safe = useMemo(() => sanitizeEmailHtml(html || ""), [html]);
  if (safe) {
    return (
      <Box
        component="div"
        sx={[
          (theme) => ({
            ...theme.typography.body2,
            color: theme.palette.text.secondary,
            wordBreak: "break-word",
            "& *": { fontFamily: "inherit" },
            "& pre, & code": {
              fontFamily:
                'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
            },
            "& img": { maxWidth: "100%", height: "auto" },
            "& table": { maxWidth: "100%", display: "block", overflowX: "auto" },
            "& pre": { whiteSpace: "pre-wrap" },
            "& a": { color: "primary.main" },
          }),
          readingLight && readingLightSx,
          sx,
        ]}
        dangerouslySetInnerHTML={{ __html: safe }}
      />
    );
  }
  if (!text) return null;
  return (
    <Box
      component="pre"
      sx={[
        (theme) => ({
          ...theme.typography.body2,
          color: theme.palette.text.secondary,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontFamily: "inherit",
          margin: 0,
          lineHeight: 1.5,
        }),
        readingLight && readingLightSx,
        sx,
      ]}
    >
      {text}
    </Box>
  );
}
