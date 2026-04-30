import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import { toneFor } from "./stages";

/**
 * Minimal, scannable stage indicator. 8px filled dot — one visual token per row.
 */
export default function StageDot({ stage, size = 8, showTooltip = true, sx }) {
  const { color, label } = toneFor(stage);
  const dot = (
    <Box
      aria-label={label}
      sx={{
        width: size,
        height: size,
        borderRadius: "50%",
        bgcolor: color,
        flexShrink: 0,
        ...sx,
      }}
    />
  );
  if (!showTooltip) return dot;
  return (
    <Tooltip title={label} arrow placement="top" enterDelay={300}>
      {dot}
    </Tooltip>
  );
}
