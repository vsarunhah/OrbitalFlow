import { useEffect, useState } from "react";
import Popover from "@mui/material/Popover";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import CheckIcon from "@mui/icons-material/Check";
import StageDot from "./StageDot";
import { STAGES, toneFor } from "./stages";

/**
 * Inline stage picker: click a stage to select; optional reason field;
 * Enter to confirm. Replaces the "Manual Stage Override" Paper block so
 * the most-common action (changing stage) is one click from the pill.
 */
export default function StageChangePopover({
  open,
  anchorEl,
  currentStage,
  onClose,
  onConfirm,
}) {
  const [picked, setPicked] = useState(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setPicked(null);
      setReason("");
      setSubmitting(false);
    }
  }, [open]);

  async function confirm() {
    if (!picked || picked === currentStage) return;
    setSubmitting(true);
    try {
      await onConfirm(picked, reason.trim() || "Manual change");
      onClose?.();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Popover
      open={open}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      transformOrigin={{ vertical: "top", horizontal: "left" }}
      slotProps={{
        paper: {
          sx: { p: 1.5, minWidth: 260, bgcolor: "background.paper", borderRadius: 2 },
        },
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", fontWeight: 600 }}>
        Change stage
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25, mt: 0.75, mb: 1 }}>
        {STAGES.map((s) => {
          const { color, label } = toneFor(s);
          const active = picked === s;
          const isCurrent = s === currentStage;
          return (
            <Box
              key={s}
              component="button"
              type="button"
              onClick={() => setPicked(s)}
              disabled={isCurrent}
              sx={{
                all: "unset",
                display: "flex",
                alignItems: "center",
                gap: 1,
                px: 1,
                py: 0.5,
                borderRadius: 1,
                cursor: isCurrent ? "default" : "pointer",
                opacity: isCurrent ? 0.45 : 1,
                bgcolor: active ? `${color}22` : "transparent",
                "&:hover": isCurrent ? undefined : { bgcolor: "action.hover" },
              }}
            >
              <StageDot stage={s} size={8} showTooltip={false} />
              <Typography variant="body2" sx={{ flex: 1 }}>
                {label}
              </Typography>
              {isCurrent ? (
                <Typography variant="caption" color="text.secondary">
                  current
                </Typography>
              ) : active ? (
                <CheckIcon fontSize="small" sx={{ color }} />
              ) : null}
            </Box>
          );
        })}
      </Box>
      <TextField
        size="small"
        fullWidth
        placeholder="Reason (optional)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && picked && picked !== currentStage) {
            e.preventDefault();
            void confirm();
          }
        }}
        sx={{ mb: 1 }}
      />
      <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1 }}>
        <Button size="small" onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={!picked || picked === currentStage || submitting}
          onClick={confirm}
        >
          {submitting ? "Saving…" : "Update"}
        </Button>
      </Box>
    </Popover>
  );
}
