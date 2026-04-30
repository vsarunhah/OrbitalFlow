import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import TextField from "@mui/material/TextField";
import MoreHorizIcon from "@mui/icons-material/MoreHoriz";
import EditIcon from "@mui/icons-material/Edit";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import MarkEmailReadIcon from "@mui/icons-material/MarkEmailRead";
import MarkEmailUnreadIcon from "@mui/icons-material/MarkEmailUnread";
import DoNotDisturbOnOutlinedIcon from "@mui/icons-material/DoNotDisturbOnOutlined";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import ReplyIcon from "@mui/icons-material/Reply";
import StagePill from "./StagePill";
import StageChangePopover from "./StageChangePopover";

/**
 * Sticky job header. Visual hierarchy:
 *   h4 Company  + stage pill on same line
 *   role · req  (secondary)
 *   [Reply]  [Generate follow-up?]        [⋮ overflow]
 *
 * One primary action chosen by context:
 *   - unread incoming  → "Reply" (contained)
 *   - suggest_followup → "Generate follow-up" (contained)
 *   - else             → "Reply" (outlined)
 *
 * Rare actions (Edit, Mark read/unread, Delete) live under ⋮.
 */
export default function JobHeader({
  job,
  onStageChange,
  onJobUpdate,
  onRequestDelete,
  onMarkReadState,
  onDismissNeedsReply,
  onReply,
  onGenerateFollowUp,
  followUpBusy,
}) {
  const [menuAnchor, setMenuAnchor] = useState(null);
  const [editing, setEditing] = useState(false);
  const [editCompany, setEditCompany] = useState("");
  const [editRole, setEditRole] = useState("");
  const [editReqId, setEditReqId] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  const pillRef = useRef(null);
  const [pillPopover, setPillPopover] = useState(false);

  useEffect(() => {
    setEditing(false);
  }, [job?.id]);

  if (!job) return null;

  const unread = (job.unread_incoming_count ?? 0) > 0;
  const canFollowUp = !!job.suggest_followup;
  const canDismissNudge = ["needs_reply", "follow_up"].includes(
    job.next_action?.type
  );

  const primaryIsReply = unread || !canFollowUp;
  const primaryAction = primaryIsReply
    ? {
        label: "Reply",
        onClick: onReply,
        icon: <ReplyIcon fontSize="small" />,
        variant: unread ? "contained" : "outlined",
      }
    : {
        label: followUpBusy ? "Generating…" : "Generate follow-up",
        onClick: onGenerateFollowUp,
        icon: <AutoAwesomeIcon fontSize="small" />,
        variant: "contained",
        disabled: followUpBusy,
      };

  async function saveEdits() {
    setEditSaving(true);
    try {
      const fields = {};
      if (editCompany.trim() !== (job.company || "")) fields.company = editCompany.trim() || null;
      if (editRole.trim() !== (job.role || "")) fields.role = editRole.trim() || null;
      if (editReqId.trim() !== (job.req_id || "")) fields.req_id = editReqId.trim() || null;
      if (Object.keys(fields).length === 0) {
        setEditing(false);
        return;
      }
      await onJobUpdate(job.id, fields);
      setEditing(false);
    } catch (err) {
      alert(`Failed to update job: ${err.message}`);
    } finally {
      setEditSaving(false);
    }
  }

  if (editing) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1, mb: 2 }}>
        <TextField size="small" label="Company" value={editCompany} onChange={(e) => setEditCompany(e.target.value)} />
        <TextField size="small" label="Role" value={editRole} onChange={(e) => setEditRole(e.target.value)} />
        <TextField size="small" label="Req ID" value={editReqId} onChange={(e) => setEditReqId(e.target.value)} />
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button variant="contained" size="small" onClick={saveEdits} disabled={editSaving}>
            {editSaving ? "Saving…" : "Save"}
          </Button>
          <Button variant="outlined" size="small" onClick={() => setEditing(false)} disabled={editSaving}>
            Cancel
          </Button>
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        position: "sticky",
        top: 0,
        zIndex: 2,
        bgcolor: "background.default",
        pt: 2,
        pb: 1.5,
        mb: 2,
        borderBottom: 1,
        borderColor: "divider",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, flexWrap: "wrap" }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            <Typography variant="h5" fontWeight={700} sx={{ lineHeight: 1.1 }}>
              {job.company || "Unknown"}
            </Typography>
            <StagePill
              ref={pillRef}
              stage={job.current_stage}
              onClick={() => setPillPopover(true)}
            />
          </Box>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {job.role || "No role"}
            {job.req_id ? (
              <Typography component="span" variant="body2" color="text.disabled" sx={{ ml: 1 }}>
                · Req {job.req_id}
              </Typography>
            ) : null}
          </Typography>
          {job.next_action ? (
            <Typography variant="body2" color="warning.main" sx={{ mt: 0.5, fontWeight: 500 }}>
              {job.next_action.label}
            </Typography>
          ) : null}
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexShrink: 0 }}>
          <Button
            variant={primaryAction.variant}
            color="primary"
            size="small"
            startIcon={primaryAction.icon}
            onClick={primaryAction.onClick}
            disabled={primaryAction.disabled}
          >
            {primaryAction.label}
          </Button>
          {!primaryIsReply ? (
            <Button
              variant="outlined"
              size="small"
              startIcon={<ReplyIcon fontSize="small" />}
              onClick={onReply}
            >
              Reply
            </Button>
          ) : canFollowUp ? (
            <Button
              variant="outlined"
              color="secondary"
              size="small"
              startIcon={<AutoAwesomeIcon fontSize="small" />}
              onClick={onGenerateFollowUp}
              disabled={followUpBusy}
            >
              {followUpBusy ? "Generating…" : "Follow-up"}
            </Button>
          ) : null}
          <IconButton size="small" aria-label="More" onClick={(e) => setMenuAnchor(e.currentTarget)}>
            <MoreHorizIcon fontSize="small" />
          </IconButton>
          <Menu
            anchorEl={menuAnchor}
            open={Boolean(menuAnchor)}
            onClose={() => setMenuAnchor(null)}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
          >
            <MenuItem
              onClick={() => {
                setMenuAnchor(null);
                setEditCompany(job.company || "");
                setEditRole(job.role || "");
                setEditReqId(job.req_id || "");
                setEditing(true);
              }}
            >
              <ListItemIcon>
                <EditIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText primary="Edit details" />
            </MenuItem>
            <MenuItem
              onClick={() => {
                setMenuAnchor(null);
                onMarkReadState?.(job.id, unread);
              }}
            >
              <ListItemIcon>
                {unread ? <MarkEmailReadIcon fontSize="small" /> : <MarkEmailUnreadIcon fontSize="small" />}
              </ListItemIcon>
              <ListItemText primary={unread ? "Mark as read" : "Mark as unread"} />
            </MenuItem>
            {canDismissNudge && onDismissNeedsReply ? (
              <MenuItem
                onClick={() => {
                  setMenuAnchor(null);
                  onDismissNeedsReply(job.id);
                }}
              >
                <ListItemIcon>
                  <DoNotDisturbOnOutlinedIcon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary="No reply needed" secondary="Hides the nudge until a new message" />
              </MenuItem>
            ) : null}
            <MenuItem
              onClick={() => {
                setMenuAnchor(null);
                onRequestDelete?.(job);
              }}
              sx={{ color: "error.main" }}
            >
              <ListItemIcon sx={{ color: "error.main" }}>
                <DeleteOutlineIcon fontSize="small" />
              </ListItemIcon>
              <ListItemText primary="Delete job" />
            </MenuItem>
          </Menu>
        </Box>
      </Box>
      <StageChangePopover
        open={pillPopover}
        anchorEl={pillRef.current}
        currentStage={job.current_stage}
        onClose={() => setPillPopover(false)}
        onConfirm={(newStage, reason) => onStageChange(job.id, newStage, reason)}
      />
    </Box>
  );
}
