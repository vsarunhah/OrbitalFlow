import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import FormControlLabel from "@mui/material/FormControlLabel";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import AttachFile from "@mui/icons-material/AttachFile";
import {
  fetchJobs,
  fetchTimeline,
  changeStage,
  updateJob,
  deleteJob,
  mergeJobs,
  createDraftReply,
  createComposeDraft,
  getDraftForJob,
  getDraftRecipients,
  getJobReplyRecipients,
  updateDraft,
  sendDraft,
  generateFollowUpSuggestion,
} from "../lib/api";
import ConfirmModal from "../components/ConfirmModal";

const STAGES = [
  "SOURCED",
  "APPLIED",
  "SCREEN",
  "INTERVIEW",
  "TAKEHOME",
  "FINAL",
  "OFFER",
  "REJECTED",
  "WITHDRAWN",
];

const STAGE_COLORS = {
  SOURCED: "#6b7280",
  APPLIED: "#3b82f6",
  SCREEN: "#8b5cf6",
  INTERVIEW: "#f59e0b",
  TAKEHOME: "#ec4899",
  FINAL: "#14b8a6",
  OFFER: "#22c55e",
  REJECTED: "#ef4444",
  WITHDRAWN: "#9ca3af",
};

function StageBadge({ stage }) {
  return (
    <Chip
      label={stage}
      size="small"
      sx={{
        bgcolor: STAGE_COLORS[stage] || "#6b7280",
        color: "#fff",
        fontWeight: 600,
        fontSize: 11,
        textTransform: "uppercase",
      }}
    />
  );
}

function JobCard({ job, selected, selectedForMerge, mergeMode, onToggleMerge, onClick }) {
  return (
    <Box
      onClick={(e) => e.target?.type !== "checkbox" && onClick()}
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 1.25,
        py: 1.5,
        px: 1.5,
        mb: 0.5,
        borderRadius: 1,
        cursor: "pointer",
        borderLeft: selected ? 3 : 0,
        borderLeftColor: "primary.main",
        outline: selectedForMerge ? "2px solid" : 0,
        outlineColor: "primary.main",
        outlineOffset: 2,
        bgcolor: selected ? "action.selected" : selectedForMerge ? "primary.dark" : "transparent",
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      {mergeMode && (
        <Checkbox
          size="small"
          checked={!!selectedForMerge}
          onChange={() => onToggleMerge(job.id)}
          onClick={(e) => e.stopPropagation()}
        />
      )}
      <Box sx={{ flex: 1, minWidth: 0 }} onClick={() => onClick()}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 1 }}>
            <Typography fontWeight={600} fontSize={14}>
              {job.company || "Unknown"}
            </Typography>
            <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.5 }}>
              <StageBadge stage={job.current_stage} />
              {job.next_action && (
                <Typography
                  component={job.next_action.scheduling_link ? "a" : "span"}
                  href={job.next_action.scheduling_link}
                  target="_blank"
                  rel="noopener noreferrer"
                  variant="caption"
                  sx={{
                    color: "text.secondary",
                    bgcolor: "action.hover",
                    border: 1,
                    borderColor: "divider",
                    px: 1,
                    py: 0.25,
                    borderRadius: 2,
                    textDecoration: "none",
                    "&:hover": { textDecoration: "underline" },
                  }}
                  onClick={(e) => job.next_action.scheduling_link && e.stopPropagation()}
                >
                  {job.next_action.label}
                </Typography>
              )}
            </Box>
          </Box>
          <Typography variant="body2" color="text.secondary">
            {job.role || "No role"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {job.last_activity ? new Date(job.last_activity).toLocaleDateString() : "No activity"}
          </Typography>
        </Box>
    </Box>
  );
}

function SearchBar({ value, onChange, onSearch }) {
  return (
    <Box sx={{ display: "flex", gap: 1, p: 1.5 }}>
      <TextField
        size="small"
        placeholder="Search jobs, emails..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSearch()}
        sx={{ flex: 1 }}
      />
      <Button variant="contained" onClick={onSearch}>
        Search
      </Button>
    </Box>
  );
}

function StageFilter({ value, onChange }) {
  const selected = Array.isArray(value) ? value : value ? [value] : [];
  const label =
    selected.length === 0
      ? "All stages"
      : selected.length <= 2
        ? selected.join(", ")
        : `${selected.length} stages`;

  return (
    <FormControl size="small" sx={{ m: 1.5, minWidth: 180 }}>
      <InputLabel>Stage</InputLabel>
      <Select
        multiple
        value={selected}
        label="Stage"
        onChange={(e) => {
          const v = e.target.value;
          const next = typeof v === "string" ? (v ? [v] : []) : [...v];
          if (next.includes("")) {
            onChange([]);
            return;
          }
          onChange(next);
        }}
        renderValue={() => label}
      >
        <MenuItem value="">
          <em>All stages</em>
        </MenuItem>
        {STAGES.map((s) => (
          <MenuItem key={s} value={s}>
            <Checkbox checked={selected.includes(s)} size="small" sx={{ mr: 1 }} />
            <Chip
              label={s}
              size="small"
              sx={{
                bgcolor: STAGE_COLORS[s] || "#6b7280",
                color: "#fff",
                fontWeight: 600,
                fontSize: 10,
              }}
            />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

function MergeJobsModal({ jobs, selectedIds, onClose, onConfirm }) {
  const [targetId, setTargetId] = useState(selectedIds[0] || null);
  const selectedJobs = jobs.filter((j) => selectedIds.includes(j.id));

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { bgcolor: "background.paper" } }}>
      <DialogTitle>Merge jobs</DialogTitle>
      <DialogContent>
        <DialogContentText color="text.secondary" sx={{ mb: 2 }}>
          Choose which job to keep. All others will be merged into it and removed.
        </DialogContentText>
        <RadioGroup value={targetId || ""} onChange={(e) => setTargetId(e.target.value)}>
          {selectedJobs.map((j) => (
            <FormControlLabel
              key={j.id}
              value={String(j.id)}
              control={<Radio />}
              label={`${j.company || "Unknown"} – ${j.role || "No role"}`}
              sx={{ display: "flex", m: 0, py: 0.5 }}
            />
          ))}
        </RadioGroup>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => targetId && onConfirm(targetId, selectedIds.filter((id) => id !== targetId))}
        >
          Merge
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function normalizeEmail(input) {
  const s = (input || "").trim().toLowerCase();
  return s.includes("@") ? s : null;
}

function ExpandableTimelineBody({ bodyText, bodySnippet }) {
  const [expanded, setExpanded] = useState(false);
  const fullText = (bodyText || bodySnippet || "").trim();
  if (!fullText) return null;

  const previewText = bodySnippet || fullText;
  const hasMore =
    Boolean(bodyText && bodySnippet && bodyText.length > bodySnippet.length) ||
    Boolean(bodyText && !bodySnippet && bodyText.length > 300);

  const textSx = {
    whiteSpace: "pre-wrap",
    lineHeight: 1.4,
    wordBreak: "break-word",
  };

  if (!hasMore) {
    return (
      <Typography variant="body2" color="text.secondary" component="div" sx={{ ...textSx, mt: 0.5 }}>
        {fullText}
      </Typography>
    );
  }

  if (!expanded) {
    return (
      <Box sx={{ mt: 0.5 }}>
        <Typography
          variant="body2"
          color="text.secondary"
          component="div"
          sx={{
            ...textSx,
            maxHeight: 80,
            overflow: "hidden",
          }}
        >
          {previewText}
        </Typography>
        <Button
          variant="text"
          size="small"
          onClick={() => setExpanded(true)}
          sx={{ mt: 0.25, p: 0, minWidth: 0, textTransform: "none", fontSize: 13 }}
        >
          Show more
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ mt: 0.5 }}>
      <Box
        sx={{
          maxHeight: "min(50vh, 420px)",
          overflowY: "auto",
          pr: 0.5,
          borderRadius: 1,
          bgcolor: "action.hover",
          px: 1.25,
          py: 1,
        }}
      >
        <Typography variant="body2" color="text.secondary" component="div" sx={{ ...textSx, lineHeight: 1.5 }}>
          {bodyText || fullText}
        </Typography>
      </Box>
      <Button
        variant="text"
        size="small"
        onClick={() => setExpanded(false)}
        sx={{ mt: 0.5, p: 0, minWidth: 0, textTransform: "none", fontSize: 13 }}
      >
        Show less
      </Button>
    </Box>
  );
}

const MAX_REPLY_ATTACH_BYTES = 25 * 1024 * 1024;
const MAX_REPLY_ATTACH_FILES = 15;

function ReplyDraftModal({ open, onClose, jobId, draft, sourceMessageId, onDraftCreated, onSaved, onSent }) {
  const [subject, setSubject] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [toAddrs, setToAddrs] = useState([]);
  const [ccAddrs, setCcAddrs] = useState([]);
  const [addToInput, setAddToInput] = useState("");
  const [addCcInput, setAddCcInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState(null);
  const [selectedVariantId, setSelectedVariantId] = useState(null);
  const [attachments, setAttachments] = useState([]);
  const fileInputRef = useRef(null);

  const variants = draft?.variants && Array.isArray(draft.variants) ? draft.variants : [];

  useEffect(() => {
    if (draft) {
      setSubject(draft.subject || "");
      setBodyText(draft.body_text || "");
      setError(null);
      if (variants.length > 0 && !selectedVariantId) {
        setSelectedVariantId(variants[0].variant_id || "concise");
      }
      getDraftRecipients(draft.id)
        .then((r) => {
          setToAddrs(r.to_addrs || []);
          setCcAddrs(r.cc_addrs || []);
        })
        .catch(() => {
          setToAddrs([]);
          setCcAddrs([]);
        });
    } else if (open && jobId) {
      setSubject("");
      setBodyText("");
      setToAddrs([]);
      setCcAddrs([]);
      setAddToInput("");
      setAddCcInput("");
      setError(null);
      setSelectedVariantId(null);
      getJobReplyRecipients(jobId, sourceMessageId || undefined)
        .then((r) => {
          setToAddrs(r.to_addrs || []);
          setCcAddrs(r.cc_addrs || []);
        })
        .catch(() => {
          setToAddrs([]);
          setCcAddrs([]);
        });
    }
  }, [open, jobId, draft?.id, sourceMessageId]);

  useEffect(() => {
    if (open) {
      setAttachments([]);
    }
  }, [open, draft?.id]);

  const addAttachmentsFromInput = (e) => {
    const picked = Array.from(e.target.files || []);
    e.target.value = "";
    if (picked.length === 0) return;
    setAttachments((prev) => {
      const merged = [...prev, ...picked];
      if (merged.length > MAX_REPLY_ATTACH_FILES) {
        setError(`You can attach at most ${MAX_REPLY_ATTACH_FILES} files.`);
        return prev;
      }
      const total = merged.reduce((s, f) => s + f.size, 0);
      if (total > MAX_REPLY_ATTACH_BYTES) {
        setError("Total attachment size must be 25MB or less.");
        return prev;
      }
      setError(null);
      return merged;
    });
  };

  const removeAttachment = (index) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSuggestReply = async () => {
    if (!jobId) return;
    setSuggesting(true);
    setError(null);
    try {
      const res = await createDraftReply(jobId, { sourceMessageId: sourceMessageId || undefined });
      const draftWithVariants = { ...res.draft, variants: res.variants || [] };
      onDraftCreated?.(draftWithVariants);
    } catch (err) {
      setError(err.message);
    } finally {
      setSuggesting(false);
    }
  };

  const handleSelectVariant = (variant) => {
    if (!variant || !draft) return;
    setSelectedVariantId(variant.variant_id);
    // Only update body when switching variants; never change subject (preserve thread subject or user edit).
    setBodyText(variant.body || "");
    updateDraft(draft.id, { body_text: variant.body }).catch(() => {});
  };

  const handleSave = async () => {
    if (!draft || draft.status === "SENT") return;
    setSaving(true);
    setError(null);
    try {
      await updateDraft(draft.id, { subject, body_text: bodyText });
      onSaved?.({ subject, body_text: bodyText });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleSend = async () => {
    if (!jobId || toAddrs.length === 0 || draft?.status === "SENT") return;
    setSending(true);
    setError(null);
    try {
      let draftId = draft?.id;
      if (!draftId) {
        const created = await createComposeDraft(jobId, {
          sourceMessageId: sourceMessageId || undefined,
          subject: subject.trim() || undefined,
          body_text: bodyText.trim() || undefined,
        });
        draftId = created.id;
      }
      await sendDraft(draftId, {
        to_addrs: toAddrs,
        cc_addrs: ccAddrs,
        attachments: attachments.length > 0 ? attachments : undefined,
      });
      onSent?.();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  const removeTo = (email) => setToAddrs((prev) => prev.filter((e) => e !== email));
  const removeCc = (email) => setCcAddrs((prev) => prev.filter((e) => e !== email));

  const addToEmail = () => {
    const email = normalizeEmail(addToInput);
    if (email && !toAddrs.includes(email)) {
      setToAddrs((prev) => [...prev, email]);
      setAddToInput("");
    }
  };
  const addCcEmail = () => {
    const email = normalizeEmail(addCcInput);
    if (email && !ccAddrs.includes(email)) {
      setCcAddrs((prev) => [...prev, email]);
      setAddCcInput("");
    }
  };

  if (!open || !jobId) return null;
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { bgcolor: "background.paper" } }}>
      <DialogTitle>Reply</DialogTitle>
      <DialogContent>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        <TextField
          fullWidth
          size="small"
          label="Subject"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder={draft ? undefined : "Subject (or use Suggest Reply)"}
          multiline
          minRows={1}
          maxRows={3}
          sx={{ mb: 2 }}
        />
        <Box sx={{ mb: 2 }}>
          <Box sx={{ mb: 1 }}>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
              To {draft ? "(remove or add people)" : "(reply-all; remove or add people)"}
            </Typography>
            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", alignItems: "center", mb: 0.5 }}>
              {toAddrs.map((email) => (
                <Chip key={email} label={email} size="small" onDelete={() => removeTo(email)} />
              ))}
              <TextField
                size="small"
                placeholder="Add email"
                value={addToInput}
                onChange={(e) => setAddToInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToEmail())}
                sx={{ width: 160 }}
              />
              <Button size="small" onClick={addToEmail} disabled={!normalizeEmail(addToInput)}>
                Add
              </Button>
            </Box>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
              CC
            </Typography>
            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", alignItems: "center" }}>
              {ccAddrs.map((email) => (
                <Chip key={email} label={email} size="small" onDelete={() => removeCc(email)} />
              ))}
              <TextField
                size="small"
                placeholder="Add email"
                value={addCcInput}
                onChange={(e) => setAddCcInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCcEmail())}
                sx={{ width: 160 }}
              />
              <Button size="small" onClick={addCcEmail} disabled={!normalizeEmail(addCcInput)}>
                Add
              </Button>
            </Box>
          </Box>
        </Box>
        <TextField
          fullWidth
          multiline
          minRows={6}
          label="Body"
          value={bodyText}
          onChange={(e) => setBodyText(e.target.value)}
          placeholder={draft ? "Edit the reply..." : "Use Suggest Reply to generate a draft, or type your own."}
        />
        <Box sx={{ mt: 2 }}>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={addAttachmentsFromInput}
          />
          <Button
            size="small"
            variant="outlined"
            startIcon={<AttachFile />}
            onClick={() => fileInputRef.current?.click()}
            sx={{ mb: attachments.length > 0 ? 1 : 0 }}
          >
            Attach files
          </Button>
          {attachments.length > 0 && (
            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", alignItems: "center" }}>
              {attachments.map((file, i) => (
                <Chip
                  key={`${i}-${file.name}-${file.size}-${file.lastModified}`}
                  label={file.name}
                  size="small"
                  onDelete={() => removeAttachment(i)}
                />
              ))}
            </Box>
          )}
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            Up to {MAX_REPLY_ATTACH_FILES} files, 25MB total (Gmail limit).
          </Typography>
        </Box>
        {draft && variants.length > 0 && (
          <Box sx={{ mt: 2, mb: 1 }}>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Tone
            </Typography>
            <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
              {variants.map((v) => (
                <Chip
                  key={v.variant_id}
                  label={v.variant_id.charAt(0).toUpperCase() + v.variant_id.slice(1)}
                  onClick={() => handleSelectVariant(v)}
                  color={selectedVariantId === v.variant_id ? "primary" : "default"}
                  variant={selectedVariantId === v.variant_id ? "filled" : "outlined"}
                  size="small"
                />
              ))}
            </Box>
          </Box>
        )}
        {!draft && (
          <Box sx={{ mt: 2 }}>
            <Button
              variant="contained"
              color="primary"
              onClick={handleSuggestReply}
              disabled={suggesting}
            >
              {suggesting ? "Generating…" : "Suggest Reply"}
            </Button>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        {draft && (
          <Button onClick={handleSave} disabled={saving || draft.status === "SENT"}>
            {saving ? "Saving..." : "Save"}
          </Button>
        )}
        <Button
          variant="contained"
          onClick={handleSend}
          disabled={sending || (draft && draft.status === "SENT") || toAddrs.length === 0}
        >
          {sending ? "Sending..." : "Send"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function TimelineView({ timeline, onStageChange, onJobUpdate, onRequestDelete, onTimelineRefresh }) {
  const [overrideStage, setOverrideStage] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editCompany, setEditCompany] = useState("");
  const [editRole, setEditRole] = useState("");
  const [editReqId, setEditReqId] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  const [draftModalOpen, setDraftModalOpen] = useState(false);
  const [currentDraft, setCurrentDraft] = useState(null);
  const [generatingFollowUp, setGeneratingFollowUp] = useState(false);
  useEffect(() => {
    if (!timeline || !timeline.job) {
      return;
    }
    setEditing(false);
  }, [timeline?.job?.id]);

  const sourceMessageId = useMemo(() => {
    const msgs = timeline?.messages;
    if (!msgs?.length) return null;
    const sorted = [...msgs].sort(
      (a, b) => new Date(b.date_header || b.id) - new Date(a.date_header || a.id)
    );
    return sorted[0]?.id ?? null;
  }, [timeline?.messages]);

  if (!timeline) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "text.secondary" }}>
        Select a job to view timeline
      </Box>
    );
  }

  const { job, events, messages, sent_messages = [] } = timeline;

  function startEditing() {
    setEditCompany(job.company || "");
    setEditRole(job.role || "");
    setEditReqId(job.req_id || "");
    setEditing(true);
  }

  function cancelEditing() {
    setEditing(false);
  }

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

  async function handleOverride() {
    if (!overrideStage || !reason.trim()) return;
    setSubmitting(true);
    try {
      await onStageChange(job.id, overrideStage, reason.trim());
      setOverrideStage("");
      setReason("");
    } finally {
      setSubmitting(false);
    }
  }

  const merged = [];
  events.forEach((e) => merged.push({ type: "event", data: e, date: e.created_at }));
  messages.forEach((m) => merged.push({ type: "message", data: m, date: m.date_header || m.id }));
  sent_messages.forEach((s) => merged.push({ type: "sent", data: s, date: s.sent_at }));
  merged.sort((a, b) => new Date(a.date) - new Date(b.date));

  return (
    <Box>
      <Box sx={{ pb: 2, mb: 2, borderBottom: 1, borderColor: "divider", display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 2 }}>
        {editing ? (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25, flex: 1 }}>
            <TextField
              size="small"
              label="Company"
              value={editCompany}
              onChange={(e) => setEditCompany(e.target.value)}
              placeholder="Company name"
            />
            <TextField
              size="small"
              label="Role"
              value={editRole}
              onChange={(e) => setEditRole(e.target.value)}
              placeholder="Role / title"
            />
            <TextField
              size="small"
              label="Req ID"
              value={editReqId}
              onChange={(e) => setEditReqId(e.target.value)}
              placeholder="Requisition ID (optional)"
            />
            <Box sx={{ display: "flex", gap: 1, mt: 0.5 }}>
              <Button variant="contained" size="small" onClick={saveEdits} disabled={editSaving}>
                {editSaving ? "Saving..." : "Save"}
              </Button>
              <Button variant="outlined" size="small" onClick={cancelEditing} disabled={editSaving}>
                Cancel
              </Button>
            </Box>
          </Box>
        ) : (
          <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5 }}>
            <Box>
              <Typography variant="h5" fontWeight={700}>
                {job.company || "Unknown"}
              </Typography>
              <Typography color="text.secondary">{job.role || "No role"}</Typography>
              {job.req_id && (
                <Typography variant="body2" color="text.secondary">
                  Req: {job.req_id}
                </Typography>
              )}
              {job.next_action && (
                <Typography variant="body2" color="text.secondary">
                  {job.next_action.label}
                </Typography>
              )}
            </Box>
            <Box sx={{ display: "flex", gap: 1, flexShrink: 0, flexWrap: "wrap" }}>
              <Button
                variant="outlined"
                size="small"
                color="primary"
                onClick={async () => {
                  if (currentDraft?.job_id !== job?.id) {
                    setCurrentDraft(null);
                    try {
                      const existing = await getDraftForJob(job.id);
                      if (existing) setCurrentDraft(existing);
                    } catch (_) {
                      // leave currentDraft null
                    }
                  }
                  setDraftModalOpen(true);
                }}
              >
                Reply
              </Button>
              {job.suggest_followup && (
                <Button
                  variant="outlined"
                  size="small"
                  color="secondary"
                  onClick={async () => {
                    setGeneratingFollowUp(true);
                    try {
                      const res = await generateFollowUpSuggestion(job.id);
                      if (res.draft) {
                        setCurrentDraft(res.draft);
                        setDraftModalOpen(true);
                      }
                    } catch (err) {
                      alert(err.message || "Failed to generate follow-up");
                    } finally {
                      setGeneratingFollowUp(false);
                    }
                  }}
                  disabled={generatingFollowUp}
                >
                  {generatingFollowUp ? "Generating…" : "Generate Follow-Up"}
                </Button>
              )}
              <Button variant="outlined" size="small" color="primary" onClick={startEditing}>
                Edit
              </Button>
              <Button variant="outlined" size="small" color="error" onClick={() => onRequestDelete(job)}>
                Delete
              </Button>
            </Box>
          </Box>
        )}
        {!editing && <StageBadge stage={job.current_stage} />}
      </Box>

      <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
        <Typography variant="overline" color="text.secondary" display="block" gutterBottom>
          Manual Stage Override
        </Typography>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Change to...</InputLabel>
            <Select
              value={overrideStage}
              label="Change to..."
              onChange={(e) => setOverrideStage(e.target.value)}
            >
              <MenuItem value="">Change to...</MenuItem>
              {STAGES.filter((s) => s !== job.current_stage).map((s) => (
                <MenuItem key={s} value={s}>{s}</MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            placeholder="Reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            sx={{ flex: 1, minWidth: 120 }}
          />
          <Button
            variant="contained"
            size="small"
            onClick={handleOverride}
            disabled={!overrideStage || !reason.trim() || submitting}
          >
            {submitting ? "Saving..." : "Override"}
          </Button>
        </Box>
      </Paper>

      <Typography variant="overline" color="text.secondary" display="block" gutterBottom>
        Timeline
      </Typography>
      {merged.length === 0 && (
        <Typography color="text.secondary" fontStyle="italic">
          No events or messages yet.
        </Typography>
      )}
      <Box sx={{ position: "relative", pl: 3 }}>
        <Box
          sx={{
            position: "absolute",
            left: 7,
            top: 0,
            bottom: 0,
            width: 2,
            bgcolor: "divider",
          }}
        />
        {merged.map((item, i) =>
          item.type === "event" ? (
            <Box key={`ev-${item.data.id}`} sx={{ display: "flex", gap: 1.5, mb: 2, position: "relative" }}>
              <Box
                sx={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  bgcolor: "primary.main",
                  border: "2px solid",
                  borderColor: "background.default",
                  position: "absolute",
                  left: -24,
                  top: 3,
                  zIndex: 1,
                }}
              />
              <Card variant="outlined" sx={{ flex: 1, p: 1.5 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                  <Typography fontWeight={600}>{item.data.event_type || "Stage change"}</Typography>
                  <Typography variant="caption" color="text.secondary" textTransform="uppercase">
                    {item.data.source}
                  </Typography>
                </Box>
                {item.data.stage_before && item.data.stage_after && (
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, my: 0.75 }}>
                    <StageBadge stage={item.data.stage_before} />
                    <Typography color="text.secondary">→</Typography>
                    <StageBadge stage={item.data.stage_after} />
                  </Box>
                )}
                {item.data.rationale && (
                  <Typography variant="body2" color="text.secondary" fontStyle="italic" sx={{ mt: 0.5 }}>
                    {item.data.rationale}
                  </Typography>
                )}
                <Typography component="time" variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                  {new Date(item.data.created_at).toLocaleString()}
                </Typography>
              </Card>
            </Box>
          ) : item.type === "message" ? (
            <Box key={`msg-${item.data.id}`} sx={{ display: "flex", gap: 1.5, mb: 2, position: "relative" }}>
              <Box
                sx={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  bgcolor: "#3b82f6",
                  border: "2px solid",
                  borderColor: "background.default",
                  position: "absolute",
                  left: -24,
                  top: 3,
                  zIndex: 1,
                }}
              />
              <Card variant="outlined" sx={{ flex: 1, p: 1.5 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                  <Typography fontWeight={600}>{item.data.subject || "(no subject)"}</Typography>
                  {item.data.provider_msg_id && (
                    <Link
                      href={`https://mail.google.com/mail/u/0/#all/${item.data.provider_msg_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      color="text.secondary"
                      sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}
                      title="Open in Gmail"
                    >
                      ↗
                    </Link>
                  )}
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                  {item.data.from_address}
                </Typography>
                <ExpandableTimelineBody bodyText={item.data.body_text} bodySnippet={item.data.body_snippet} />
                <Typography component="time" variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                  {item.data.date_header ? new Date(item.data.date_header).toLocaleString() : ""}
                </Typography>
              </Card>
            </Box>
          ) : item.type === "sent" ? (
            <Box key={`sent-${item.data.id}`} sx={{ display: "flex", gap: 1.5, mb: 2, position: "relative" }}>
              <Box
                sx={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  bgcolor: "success.main",
                  border: "2px solid",
                  borderColor: "background.default",
                  position: "absolute",
                  left: -24,
                  top: 3,
                  zIndex: 1,
                }}
              />
              <Card variant="outlined" sx={{ flex: 1, p: 1.5, borderColor: "success.light" }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                  <Chip label="Sent" size="small" color="success" sx={{ fontWeight: 600 }} />
                  <Typography fontWeight={600}>{item.data.subject || "(no subject)"}</Typography>
                </Box>
                {item.data.to_addrs_json && (
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                    To: {(() => {
                      try {
                        const to = JSON.parse(item.data.to_addrs_json);
                        return Array.isArray(to) ? to.join(", ") : item.data.to_addrs_json;
                      } catch {
                        return item.data.to_addrs_json;
                      }
                    })()}
                  </Typography>
                )}
                <ExpandableTimelineBody bodyText={item.data.body_text} bodySnippet={item.data.body_snippet} />
                <Typography component="time" variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                  {new Date(item.data.sent_at).toLocaleString()}
                </Typography>
              </Card>
            </Box>
          ) : null
        )}
      </Box>

      <ReplyDraftModal
        open={draftModalOpen}
        onClose={() => setDraftModalOpen(false)}
        jobId={job?.id ?? null}
        draft={currentDraft}
        sourceMessageId={sourceMessageId}
        onDraftCreated={setCurrentDraft}
        onSaved={(updates) => setCurrentDraft((d) => (d && updates ? { ...d, ...updates } : d))}
        onSent={() => { onTimelineRefresh?.(); setCurrentDraft(null); }}
      />
    </Box>
  );
}

export default function JobsPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [stageFilter, setStageFilter] = useState([]);
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelectedIds, setMergeSelectedIds] = useState(new Set());
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [mergeSubmitting, setMergeSubmitting] = useState(false);
  const [deleteConfirmJob, setDeleteConfirmJob] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJobs({
        query: searchQuery || undefined,
        stage: stageFilter.length ? stageFilter.join(",") : undefined,
      });
      setJobs(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, stageFilter]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!router.isReady || !router.query.job) return;
    const jobId = router.query.job;
    setSelectedJobId(jobId);
    router.replace("/jobs", undefined, { shallow: true });
  }, [router.isReady, router.query.job]);

  useEffect(() => {
    if (!selectedJobId) {
      setTimeline(null);
      return;
    }
    let cancelled = false;
    setTimelineLoading(true);
    setTimelineError(null);
    fetchTimeline(selectedJobId)
      .then((data) => {
        if (!cancelled) setTimeline(data);
      })
      .catch((err) => {
        if (!cancelled) setTimelineError(err.message);
      })
      .finally(() => {
        if (!cancelled) setTimelineLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedJobId]);

  async function handleStageChange(jobId, newStage, reason) {
    try {
      await changeStage(jobId, newStage, reason);
      await loadJobs();
      const tl = await fetchTimeline(jobId);
      setTimeline(tl);
    } catch (err) {
      alert(`Failed to change stage: ${err.message}`);
    }
  }

  async function handleJobUpdate(jobId, fields) {
    await updateJob(jobId, fields);
    await loadJobs();
    const tl = await fetchTimeline(jobId);
    setTimeline(tl);
  }

  async function handleTimelineRefresh() {
    if (!selectedJobId) return;
    try {
      const tl = await fetchTimeline(selectedJobId);
      setTimeline(tl);
    } catch (err) {
      setTimelineError(err.message);
    }
  }

  async function handleDeleteJob(jobId) {
    try {
      await deleteJob(jobId);
      setSelectedJobId(null);
      setTimeline(null);
      await loadJobs();
    } catch (err) {
      alert(`Failed to delete job: ${err.message}`);
    }
  }

  function toggleMergeSelection(jobId) {
    setMergeSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  }

  async function handleMergeConfirm(targetId, sourceIds) {
    if (sourceIds.length === 0) return;
    setMergeSubmitting(true);
    try {
      await mergeJobs(targetId, sourceIds);
      setShowMergeModal(false);
      setMergeSelectedIds(new Set());
      setSelectedJobId(targetId);
      await loadJobs();
      const tl = await fetchTimeline(targetId);
      setTimeline(tl);
    } catch (err) {
      alert(`Merge failed: ${err.message}`);
    } finally {
      setMergeSubmitting(false);
    }
  }

  return (
    <Box sx={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Box
        sx={{
          width: 380,
          minWidth: 300,
          borderRight: 1,
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          bgcolor: "background.paper",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1.5, p: 2, flexWrap: "wrap" }}>
          <Typography variant="h6" fontWeight={600}>
            Jobs
          </Typography>
          {!mergeMode ? (
            <Button variant="outlined" size="small" onClick={() => setMergeMode(true)}>
              Merge
            </Button>
          ) : (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {mergeSelectedIds.size >= 2 ? `${mergeSelectedIds.size} selected` : "Select 2+ to merge"}
              </Typography>
              {mergeSelectedIds.size >= 2 && (
                <Button variant="contained" size="small" onClick={() => setShowMergeModal(true)}>
                  Merge
                </Button>
              )}
              <Button size="small" color="inherit" onClick={() => { setMergeMode(false); setMergeSelectedIds(new Set()); }}>
                Done
              </Button>
            </Box>
          )}
        </Box>
        <SearchBar value={searchQuery} onChange={setSearchQuery} onSearch={loadJobs} />
        <StageFilter value={stageFilter} onChange={setStageFilter} />
        <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 1 }}>
          {loading ? "Loading..." : `${total} job${total !== 1 ? "s" : ""}`}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mx: 2, mb: 1 }}>
            {error}
          </Alert>
        )}
        <Box sx={{ flex: 1, overflowY: "auto", px: 1, pb: 1 }}>
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              selected={job.id === selectedJobId}
              selectedForMerge={mergeSelectedIds.has(job.id)}
              mergeMode={mergeMode}
              onToggleMerge={toggleMergeSelection}
              onClick={() => setSelectedJobId(job.id)}
            />
          ))}
          {!loading && jobs.length === 0 && (
            <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              No jobs found
            </Typography>
          )}
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", p: 3, bgcolor: "background.default" }}>
        {timelineLoading && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", gap: 1 }}>
            <CircularProgress size={24} />
            <Typography color="text.secondary">Loading timeline...</Typography>
          </Box>
        )}
        {timelineError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {timelineError}
          </Alert>
        )}
        {!timelineLoading && !timelineError && (
          <TimelineView
            timeline={timeline}
            onStageChange={handleStageChange}
            onJobUpdate={handleJobUpdate}
            onRequestDelete={setDeleteConfirmJob}
            onTimelineRefresh={handleTimelineRefresh}
          />
        )}
      </Box>

      {showMergeModal && (
        <MergeJobsModal
          jobs={jobs}
          selectedIds={Array.from(mergeSelectedIds)}
          onClose={() => !mergeSubmitting && setShowMergeModal(false)}
          onConfirm={handleMergeConfirm}
        />
      )}

      <ConfirmModal
        open={!!deleteConfirmJob}
        title="Delete job?"
        message={
          deleteConfirmJob
            ? `Delete "${deleteConfirmJob.company || "this job"} – ${deleteConfirmJob.role || "no role"}"? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        danger={true}
        onConfirm={() => {
          if (deleteConfirmJob) handleDeleteJob(deleteConfirmJob.id);
          setDeleteConfirmJob(null);
        }}
        onCancel={() => setDeleteConfirmJob(null)}
      />
    </Box>
  );
}
