import { useMemo } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import { STAGES, toneFor } from "./stages";

/**
 * Horizontal pipeline strip. Each segment represents one stage; width is
 * proportional to count, filled with the stage tone. Clicking a segment
 * toggles that stage into the active filter. Provides at-a-glance shape
 * of the user's pipeline that a dropdown never could.
 */
export default function PipelineStrip({ jobs, activeStages, onToggleStage }) {
  const counts = useMemo(() => {
    const c = Object.fromEntries(STAGES.map((s) => [s, 0]));
    (jobs || []).forEach((j) => {
      const s = j.current_stage;
      if (c[s] != null) c[s] += 1;
    });
    return c;
  }, [jobs]);

  const total = useMemo(
    () => Object.values(counts).reduce((a, b) => a + b, 0),
    [counts]
  );
  const activeSet = useMemo(() => new Set(activeStages || []), [activeStages]);
  const hasFilter = activeSet.size > 0;

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1,
        px: 2,
        py: 1,
        borderBottom: 1,
        borderColor: "divider",
        bgcolor: "background.paper",
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, minWidth: 60 }}>
        Pipeline
      </Typography>
      <Box sx={{ display: "flex", flex: 1, gap: 0.5, minWidth: 0 }}>
        {STAGES.map((s) => {
          const { color, label } = toneFor(s);
          const count = counts[s];
          const active = activeSet.has(s);
          const dim = hasFilter && !active;
          const width = total > 0 ? Math.max(count / total, count === 0 ? 0.02 : 0.04) : 1 / STAGES.length;
          return (
            <Tooltip key={s} title={`${label}: ${count}`} arrow>
              <Box
                component="button"
                type="button"
                onClick={() => onToggleStage?.(s)}
                sx={{
                  all: "unset",
                  cursor: "pointer",
                  flex: width,
                  minWidth: 18,
                  height: 28,
                  borderRadius: 1,
                  position: "relative",
                  bgcolor: count === 0 ? "action.hover" : `${color}33`,
                  border: 1,
                  borderColor: active ? color : "transparent",
                  opacity: dim ? 0.35 : 1,
                  transition: "opacity 0.15s, border-color 0.15s, background-color 0.15s",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  "&:hover": { bgcolor: count === 0 ? "action.hover" : `${color}55` },
                  "&:focus-visible": { outline: "2px solid", outlineColor: color, outlineOffset: 1 },
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    color: count === 0 ? "text.disabled" : color,
                    fontWeight: 700,
                    fontSize: 11,
                    lineHeight: 1,
                  }}
                >
                  {count}
                </Typography>
              </Box>
            </Tooltip>
          );
        })}
      </Box>
    </Box>
  );
}
