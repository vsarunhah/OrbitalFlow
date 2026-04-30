import { forwardRef } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import { toneFor } from "./stages";

/**
 * Interactive stage pill: clickable chip with a subtle tinted fill and
 * dropdown affordance. Used in the timeline header so users can change
 * stage inline instead of hunting for the "Manual Stage Override" panel.
 */
const StagePill = forwardRef(function StagePill(
  { stage, onClick, interactive = true, size = "md", ...rest },
  ref
) {
  const { color, label } = toneFor(stage);
  const padY = size === "sm" ? 0.25 : 0.5;
  const padX = size === "sm" ? 0.75 : 1;
  const fontSize = size === "sm" ? 11 : 12;

  return (
    <Box
      ref={ref}
      component={interactive ? "button" : "div"}
      type={interactive ? "button" : undefined}
      onClick={interactive ? onClick : undefined}
      {...rest}
      sx={{
        all: "unset",
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        py: padY,
        px: padX,
        borderRadius: 999,
        border: 1,
        borderColor: color,
        bgcolor: `${color}1f`,
        color,
        fontWeight: 600,
        fontSize,
        letterSpacing: 0.3,
        textTransform: "uppercase",
        cursor: interactive ? "pointer" : "default",
        transition: "background-color 0.12s, border-color 0.12s",
        "&:hover": interactive ? { bgcolor: `${color}33` } : undefined,
        "&:focus-visible": interactive
          ? { outline: "2px solid", outlineColor: color, outlineOffset: 2 }
          : undefined,
      }}
    >
      <Typography
        component="span"
        sx={{ fontSize: "inherit", fontWeight: "inherit", color: "inherit", lineHeight: 1 }}
      >
        {label}
      </Typography>
      {interactive ? <KeyboardArrowDownIcon sx={{ fontSize: 14, opacity: 0.8 }} /> : null}
    </Box>
  );
});

export default StagePill;
