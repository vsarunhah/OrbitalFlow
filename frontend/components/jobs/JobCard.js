import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Checkbox from "@mui/material/Checkbox";
import Tooltip from "@mui/material/Tooltip";
import StageDot from "./StageDot";
import { formatRelativeActivity, formatActivityTooltip } from "./time";

/**
 * Dense, inbox-style job card. Visual weight ranks by signal:
 *   - Company title always visible; role is secondary.
 *   - Unread -> company name goes bold white + red dot (right, z-index on top).
 *   - Next action -> amber dot; with unread, both show stacked so red stays visible on top.
 *   - Selected -> left accent bar + tint.
 *
 * One row, one accent, one action. No duplicated Reply button on the card
 * — Reply is promoted on the timeline side once the job is opened.
 */
export default function JobCard({
  job,
  selected,
  selectedForMerge,
  mergeMode,
  onToggleMerge,
  onClick,
  compact,
}) {
  const unread = (job.unread_incoming_count ?? 0) > 0;
  const nudge = job.next_action;
  const activityRel = formatRelativeActivity(job.last_activity);
  const activityTitle = job.last_activity ? formatActivityTooltip(job.last_activity) : undefined;

  const showNudgeDot = Boolean(nudge);
  const showUnreadDot = unread;
  const showSignalDots = showNudgeDot || showUnreadDot;
  const signalTooltip = showUnreadDot && nudge
    ? `Unread recruiter email · ${nudge.label}`
    : showUnreadDot
      ? "Unread recruiter email"
      : nudge?.label || "";

  const handleClick = (e) => {
    if (e.target?.type === "checkbox") return;
    if (e.target?.closest?.(".job-card__control")) return;
    onClick();
  };

  return (
    <Box
      data-job-id={job.id}
      onClick={handleClick}
      sx={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        gap: 1,
        width: "100%",
        minWidth: 0,
        boxSizing: "border-box",
        pl: 1.5,
        pr: mergeMode ? 4.5 : 0.25,
        py: compact ? 0.75 : 1.25,
        mb: 0.25,
        borderRadius: 0.5,
        cursor: "pointer",
        bgcolor: selected
          ? (theme) =>
              theme.palette.mode === "dark"
                ? "rgba(99, 102, 241, 0.14)"
                : "action.selected"
          : selectedForMerge
            ? "primary.dark"
            : "transparent",
        outline: selectedForMerge ? "2px solid" : 0,
        outlineColor: "primary.main",
        outlineOffset: -2,
        transition: "background-color 0.12s",
        "&::before": selected
          ? {
              content: '""',
              position: "absolute",
              left: 0,
              top: 4,
              bottom: 4,
              width: 3,
              borderRadius: 0.5,
              bgcolor: "primary.main",
            }
          : undefined,
        "&:hover": {
          bgcolor: selected
            ? (theme) =>
                theme.palette.mode === "dark"
                  ? "rgba(99, 102, 241, 0.2)"
                  : "action.selected"
            : "action.hover",
        },
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          flex: 1,
          minWidth: 0,
        }}
      >
        {mergeMode ? (
          <Checkbox
            className="job-card__control"
            size="small"
            checked={!!selectedForMerge}
            onChange={() => onToggleMerge(job.id)}
            onClick={(e) => e.stopPropagation()}
            sx={{ p: 0.25, ml: -0.5, mr: 0, flexShrink: 0 }}
          />
        ) : null}

        <Box sx={{ flexShrink: 0 }}>
          <StageDot stage={job.current_stage} size={8} />
        </Box>

        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75, minWidth: 0 }}>
            <Typography
              fontWeight={unread ? 700 : 600}
              fontSize={14}
              sx={{
                color: unread ? "text.primary" : "text.primary",
                flex: "0 1 auto",
                flexShrink: 1,
                minWidth: 0,
                whiteSpace: "nowrap",
                textOverflow: "ellipsis",
                overflow: "hidden",
              }}
            >
              {job.company || "Unknown"}
            </Typography>
            {job.role ? (
              <Typography
                component="span"
                variant="body2"
                color="text.secondary"
                sx={{
                  flex: "1 1 0%",
                  flexShrink: 100,
                  minWidth: 0,
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                  overflow: "hidden",
                  fontSize: 13,
                }}
              >
                {job.role}
              </Typography>
            ) : null}
          </Box>

          {!compact && nudge ? (
            <Typography
              variant="caption"
              sx={{
                display: "block",
                color: unread ? "error.main" : "warning.main",
                fontWeight: 500,
                mt: 0.25,
                whiteSpace: "nowrap",
                textOverflow: "ellipsis",
                overflow: "hidden",
              }}
            >
              {nudge.label}
            </Typography>
          ) : null}
        </Box>
      </Box>

      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 0.35,
          flexShrink: 0,
        }}
      >
        <Box
          sx={{
            position: "relative",
            width: showNudgeDot && showUnreadDot ? 10 : 6,
            height: showNudgeDot && showUnreadDot ? 10 : 6,
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {showSignalDots ? (
            <Tooltip title={signalTooltip} arrow placement="top">
              <Box
                component="span"
                sx={{
                  position: "relative",
                  display: "block",
                  width: "100%",
                  height: "100%",
                }}
              >
                {showNudgeDot && showUnreadDot ? (
                  <>
                    <Box
                      aria-hidden
                      sx={{
                        position: "absolute",
                        left: 0,
                        top: 4,
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        bgcolor: "warning.main",
                        zIndex: 0,
                        boxShadow: (theme) =>
                          `0 0 0 1px ${theme.palette.background.paper}`,
                      }}
                    />
                    <Box
                      aria-hidden
                      sx={{
                        position: "absolute",
                        left: 3,
                        top: 0,
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        bgcolor: "error.main",
                        zIndex: 1,
                        boxShadow: (theme) =>
                          `0 0 0 1px ${theme.palette.background.paper}`,
                      }}
                    />
                  </>
                ) : showUnreadDot ? (
                  <Box
                    sx={{
                      position: "absolute",
                      left: "50%",
                      top: "50%",
                      transform: "translate(-50%, -50%)",
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      bgcolor: "error.main",
                    }}
                  />
                ) : (
                  <Box
                    sx={{
                      position: "absolute",
                      left: "50%",
                      top: "50%",
                      transform: "translate(-50%, -50%)",
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      bgcolor: "warning.main",
                    }}
                  />
                )}
              </Box>
            </Tooltip>
          ) : null}
        </Box>
        <Typography
          variant="caption"
          color="text.secondary"
          component="time"
          dateTime={job.last_activity || undefined}
          title={activityTitle || undefined}
          sx={{
            fontSize: 11,
            fontVariantNumeric: "tabular-nums",
            minWidth: "2rem",
            textAlign: "right",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {activityRel}
        </Typography>
      </Box>
    </Box>
  );
}
