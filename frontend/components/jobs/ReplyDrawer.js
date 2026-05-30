import { useEffect, useMemo, useRef, useState } from "react";
import Drawer from "@mui/material/Drawer";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import MenuItem from "@mui/material/MenuItem";
import CloseIcon from "@mui/icons-material/Close";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import SendIcon from "@mui/icons-material/Send";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import ClearAllIcon from "@mui/icons-material/ClearAll";
import {
  createDraftReply,
  createComposeDraft,
  clearJobDrafts,
  fetchAvailabilitySlots,
  getDraftRecipients,
  getJobReplyRecipients,
  startCalendarOAuth,
  updateDraft,
  sendDraft,
} from "../../lib/api";
import { buildReplySubject, normalizeEmail } from "./email";

const MAX_ATTACH_BYTES = 25 * 1024 * 1024;
const MAX_ATTACH_FILES = 15;
const UNRESOLVED_AVAILABILITY_MARKERS = ["[availability]", "{{AVAILABILITY}}"];

/** Inclusive calendar-day count for the default Free from / Free through range (one week). */
const DEFAULT_AVAILABILITY_RANGE_DAYS = 7;

function browserTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function formatLocalYmd(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultAvailabilityDateEndYmd() {
  const t = new Date();
  t.setDate(t.getDate() + (DEFAULT_AVAILABILITY_RANGE_DAYS - 1));
  return formatLocalYmd(t);
}

function formatAvailabilityBlock(slots) {
  if (!slots.length) return "";
  const lines = slots.map((slot) => `- ${slot.display}`);
  return `I'm available at the following times:\n${lines.join("\n")}`;
}

function appendAvailabilityBlock(existingBody, block) {
  const trimmed = existingBody.trimEnd();
  return `${trimmed}${trimmed ? "\n\n" : ""}${block}`;
}

/**
 * Right-side slide-over drawer for composing a reply. Auto-generates an AI
 * draft on open if the user doesn't already have one — removes the extra
 * "Suggest Reply" click that existed in the old dialog.
 *
 * Uses a Drawer instead of a Dialog so the thread stays visible behind it
 * (on wide screens) — a core requirement for composing contextual replies.
 */
export default function ReplyDrawer({
  open,
  jobId,
  draft: incomingDraft,
  sourceMessageId,
  sourceMessageSubject,
  onClose,
  onSent,
  onDraftsCleared,
  autoSuggest = true,
}) {
  const [draft, setDraft] = useState(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [toAddrs, setToAddrs] = useState([]);
  const [ccAddrs, setCcAddrs] = useState([]);
  const [addTo, setAddTo] = useState("");
  const [addCc, setAddCc] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState(null);
  const [selectedVariantId, setSelectedVariantId] = useState(null);
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [dateStart, setDateStart] = useState(() => formatLocalYmd(new Date()));
  const [dateEnd, setDateEnd] = useState(() => defaultAvailabilityDateEndYmd());
  const [timezone, setTimezone] = useState(browserTimezone());
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [availabilitySlots, setAvailabilitySlots] = useState([]);
  const [availabilityCheckedAt, setAvailabilityCheckedAt] = useState(null);
  const [availabilityConnect, setAvailabilityConnect] = useState(null);
  const [selectedSlotKeys, setSelectedSlotKeys] = useState([]);
  const fileInputRef = useRef(null);
  const autoSuggestedForRef = useRef(null);

  const variants = useMemo(
    () => (draft?.variants && Array.isArray(draft.variants) ? draft.variants : []),
    [draft]
  );
  const selectedSlots = useMemo(
    () => availabilitySlots.filter((slot) => selectedSlotKeys.includes(slot.start)),
    [availabilitySlots, selectedSlotKeys]
  );
  const availabilityBlock = useMemo(
    () => formatAvailabilityBlock(selectedSlots),
    [selectedSlots]
  );

  useEffect(() => {
    if (!open) return;
    setError(null);
    setAttachments([]);
    setAvailabilitySlots([]);
    setAvailabilityCheckedAt(null);
    setAvailabilityConnect(null);
    setSelectedSlotKeys([]);
    if (incomingDraft) {
      setDraft(incomingDraft);
      setSubject(incomingDraft.subject || "");
      setBody(incomingDraft.body_text || "");
      setSelectedVariantId(
        incomingDraft.variants?.[0]?.variant_id || null
      );
      getDraftRecipients(incomingDraft.id)
        .then((r) => {
          setToAddrs(r.to_addrs || []);
          setCcAddrs(r.cc_addrs || []);
        })
        .catch(() => {});
      return;
    }
    setDraft(null);
    setSubject(buildReplySubject(sourceMessageSubject));
    setBody("");
    setSelectedVariantId(null);
    if (jobId) {
      getJobReplyRecipients(jobId, sourceMessageId || undefined)
        .then((r) => {
          setToAddrs(r.to_addrs || []);
          setCcAddrs(r.cc_addrs || []);
        })
        .catch(() => {});
    }
  }, [open, incomingDraft?.id, jobId, sourceMessageId, sourceMessageSubject]);

  useEffect(() => {
    if (!open) {
      autoSuggestedForRef.current = null;
      return;
    }
    if (!autoSuggest || incomingDraft || !jobId || draft) return;
    // Kick off at most one auto-suggest per (open, jobId) session. A ref avoids the
    // self-cancelling race that a `suggesting` dep would introduce: flipping state
    // inside the effect must not trigger cleanup while the request is in flight.
    if (autoSuggestedForRef.current === jobId) return;
    autoSuggestedForRef.current = jobId;

    let cancelled = false;
    (async () => {
      setSuggesting(true);
      try {
        const res = await createDraftReply(jobId, {
          sourceMessageId: sourceMessageId || undefined,
        });
        if (cancelled) return;
        const withVariants = { ...res.draft, variants: res.variants || [] };
        setDraft(withVariants);
        setSubject(withVariants.subject || buildReplySubject(sourceMessageSubject));
        setBody(withVariants.body_text || "");
        if (withVariants.variants?.length) {
          setSelectedVariantId(withVariants.variants[0].variant_id);
        }
      } catch (err) {
        if (!cancelled) {
          autoSuggestedForRef.current = null;
          setError(err.message || "Failed to generate draft");
        }
      } finally {
        if (!cancelled) setSuggesting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, autoSuggest, incomingDraft, jobId, draft, sourceMessageId, sourceMessageSubject]);

  const addAttachments = (e) => {
    const picked = Array.from(e.target.files || []);
    e.target.value = "";
    if (!picked.length) return;
    setAttachments((prev) => {
      const merged = [...prev, ...picked];
      if (merged.length > MAX_ATTACH_FILES) {
        setError(`You can attach at most ${MAX_ATTACH_FILES} files.`);
        return prev;
      }
      const total = merged.reduce((s, f) => s + f.size, 0);
      if (total > MAX_ATTACH_BYTES) {
        setError("Total attachment size must be 25MB or less.");
        return prev;
      }
      setError(null);
      return merged;
    });
  };

  const selectVariant = (v) => {
    if (!draft || !v) return;
    setSelectedVariantId(v.variant_id);
    setBody(v.body || "");
    updateDraft(draft.id, { body_text: v.body }).catch(() => {});
  };

  const hasComposerContent =
    Boolean(draft) ||
    Boolean(body.trim()) ||
    subject.trim() !== buildReplySubject(sourceMessageSubject).trim();

  const handleClearDrafts = async () => {
    if (!jobId || draft?.status === "SENT" || clearing) return;
    if (hasComposerContent) {
      const ok = window.confirm(
        "Clear all unsent drafts for this job? Your current reply will be discarded."
      );
      if (!ok) return;
    }
    setClearing(true);
    setError(null);
    try {
      await clearJobDrafts(jobId);
      autoSuggestedForRef.current = jobId;
      setDraft(null);
      setSubject(buildReplySubject(sourceMessageSubject));
      setBody("");
      setSelectedVariantId(null);
      onDraftsCleared?.();
    } catch (err) {
      setError(err.message || "Failed to clear drafts");
    } finally {
      setClearing(false);
    }
  };

  const handleSave = async () => {
    if (!draft || draft.status === "SENT") return;
    setSaving(true);
    setError(null);
    try {
      await updateDraft(draft.id, { subject, body_text: body });
      setDraft((d) => (d ? { ...d, subject, body_text: body } : d));
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const loadAvailability = async () => {
    if (!jobId) return;
    setAvailabilityLoading(true);
    setAvailabilityConnect(null);
    setError(null);
    try {
      if (dateStart > dateEnd) {
        setError("End date must be on or after start date.");
        return;
      }
      const res = await fetchAvailabilitySlots({
        jobId,
        durationMinutes,
        timezone,
        dateStart,
        dateEnd,
      });
      setAvailabilitySlots(res.slots || []);
      setAvailabilityCheckedAt(res.checked_at || null);
      setAvailabilityConnect(res.connect_required || null);
      setSelectedSlotKeys([]);
    } catch (err) {
      setError(err.message || "Failed to load availability");
    } finally {
      setAvailabilityLoading(false);
    }
  };

  const handleCalendarConnect = async () => {
    setError(null);
    try {
      const res = await startCalendarOAuth();
      if (res.auth_url) window.location.href = res.auth_url;
    } catch (err) {
      setError(err.message || "Failed to start Calendar connection");
    }
  };

  const toggleSlot = (slot) => {
    setSelectedSlotKeys((prev) =>
      prev.includes(slot.start)
        ? prev.filter((key) => key !== slot.start)
        : [...prev, slot.start]
    );
  };

  const insertAvailability = () => {
    if (!availabilityBlock) return;
    setBody((prev) => appendAvailabilityBlock(prev, availabilityBlock));
  };

  const handleSend = async () => {
    if (!jobId || toAddrs.length === 0 || draft?.status === "SENT") return;
    if (UNRESOLVED_AVAILABILITY_MARKERS.some((marker) => body.includes(marker))) {
      setError("Resolve the availability placeholder before sending.");
      return;
    }
    setSending(true);
    setError(null);
    try {
      let draftId = draft?.id;
      if (!draftId) {
        const created = await createComposeDraft(jobId, {
          sourceMessageId: sourceMessageId || undefined,
          subject: subject.trim() || undefined,
          body_text: body.trim() || undefined,
        });
        draftId = created.id;
      } else {
        await updateDraft(draftId, { subject, body_text: body });
      }
      await sendDraft(draftId, {
        to_addrs: toAddrs,
        cc_addrs: ccAddrs,
        attachments: attachments.length ? attachments : undefined,
      });
      onSent?.();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  const addToEmail = () => {
    const email = normalizeEmail(addTo);
    if (email && !toAddrs.includes(email)) {
      setToAddrs((p) => [...p, email]);
      setAddTo("");
    }
  };
  const addCcEmail = () => {
    const email = normalizeEmail(addCc);
    if (email && !ccAddrs.includes(email)) {
      setCcAddrs((p) => [...p, email]);
      setAddCc("");
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      anchor="right"
      ModalProps={{ keepMounted: false }}
      PaperProps={{
        sx: {
          width: { xs: "100%", sm: 540 },
          maxWidth: "100vw",
          bgcolor: "background.paper",
          borderLeft: 1,
          borderColor: "divider",
        },
      }}
    >
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 2,
            py: 1.25,
            borderBottom: 1,
            borderColor: "divider",
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={600}>
              Reply
            </Typography>
            {suggesting ? (
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, color: "text.secondary" }}>
                <CircularProgress size={14} thickness={5} />
                <Typography variant="caption">Generating draft…</Typography>
              </Box>
            ) : null}
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            {jobId ? (
              <Button
                size="small"
                variant="outlined"
                color="inherit"
                startIcon={<ClearAllIcon fontSize="small" />}
                onClick={handleClearDrafts}
                disabled={clearing || suggesting || sending || draft?.status === "SENT"}
              >
                {clearing ? "Clearing…" : "Clear drafts"}
              </Button>
            ) : null}
            <IconButton size="small" onClick={onClose} aria-label="Close">
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>

        <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 2 }}>
          {error ? (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
              {error}
            </Alert>
          ) : null}

          <Box sx={{ mb: 1.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
              To
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, alignItems: "center", mt: 0.5 }}>
              {toAddrs.map((e) => (
                <Chip key={e} size="small" label={e} onDelete={() => setToAddrs((p) => p.filter((x) => x !== e))} />
              ))}
              <TextField
                size="small"
                variant="standard"
                placeholder="Add recipient"
                value={addTo}
                onChange={(e) => setAddTo(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addToEmail())}
                sx={{ width: 160 }}
              />
            </Box>
          </Box>

          <Box sx={{ mb: 1.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
              Cc
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, alignItems: "center", mt: 0.5 }}>
              {ccAddrs.map((e) => (
                <Chip key={e} size="small" label={e} onDelete={() => setCcAddrs((p) => p.filter((x) => x !== e))} />
              ))}
              <TextField
                size="small"
                variant="standard"
                placeholder="Add cc"
                value={addCc}
                onChange={(e) => setAddCc(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addCcEmail())}
                sx={{ width: 160 }}
              />
            </Box>
          </Box>

          <TextField
            fullWidth
            size="small"
            placeholder="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            sx={{ mb: 1.5 }}
          />

          {variants.length > 0 ? (
            <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mb: 1.5 }}>
              {variants.map((v) => (
                <Chip
                  key={v.variant_id}
                  size="small"
                  label={v.variant_id.charAt(0).toUpperCase() + v.variant_id.slice(1)}
                  onClick={() => selectVariant(v)}
                  color={selectedVariantId === v.variant_id ? "primary" : "default"}
                  variant={selectedVariantId === v.variant_id ? "filled" : "outlined"}
                />
              ))}
            </Box>
          ) : null}

          <TextField
            fullWidth
            multiline
            minRows={10}
            maxRows={20}
            placeholder={suggesting ? "Generating draft…" : "Write your reply…"}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />

          <Box sx={{ mt: 2, p: 1.5, border: 1, borderColor: "divider", borderRadius: 1 }}>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, mb: 1 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                <EventAvailableIcon fontSize="small" color="action" />
                <Typography variant="subtitle2">Add availability</Typography>
              </Box>
              {availabilityCheckedAt ? (
                <Typography variant="caption" color="text.secondary">
                  Checked {new Date(availabilityCheckedAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                </Typography>
              ) : null}
            </Box>

            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" }, gap: 1 }}>
              <TextField
                select
                size="small"
                label="Length"
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(Number(e.target.value))}
              >
                {[15, 30, 45, 60, 90, 120].map((m) => (
                  <MenuItem key={m} value={m}>{m} min</MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                label="Timezone (IANA)"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                helperText="e.g. America/Los_Angeles"
              />
              <TextField
                size="small"
                type="date"
                label="Free from"
                value={dateStart}
                onChange={(e) => setDateStart(e.target.value)}
                slotProps={{ inputLabel: { shrink: true } }}
                fullWidth
              />
              <TextField
                size="small"
                type="date"
                label="Free through"
                value={dateEnd}
                onChange={(e) => setDateEnd(e.target.value)}
                slotProps={{ inputLabel: { shrink: true } }}
                fullWidth
              />
            </Box>

            <Box sx={{ mt: 1, display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
              <Button
                size="small"
                variant="outlined"
                onClick={loadAvailability}
                disabled={availabilityLoading || !jobId}
              >
                {availabilityLoading ? "Checking…" : "Show free times"}
              </Button>
              {availabilityConnect ? (
                <Button size="small" onClick={handleCalendarConnect}>
                  Connect Calendar
                </Button>
              ) : null}
              {availabilityLoading ? <CircularProgress size={16} thickness={5} /> : null}
            </Box>

            {availabilityConnect ? (
              <Alert severity="info" sx={{ mt: 1 }}>
                {availabilityConnect.detail || "Connect Calendar to view availability."}
              </Alert>
            ) : null}

            {availabilitySlots.length > 0 ? (
              <>
                <Divider sx={{ my: 1.25 }} />
                <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
                  {availabilitySlots.slice(0, 24).map((slot) => {
                    const selected = selectedSlotKeys.includes(slot.start);
                    return (
                      <Chip
                        key={slot.start}
                        size="small"
                        label={slot.display}
                        clickable
                        color={selected ? "primary" : "default"}
                        variant={selected ? "filled" : "outlined"}
                        onClick={() => toggleSlot(slot)}
                      />
                    );
                  })}
                </Box>
                {availabilitySlots.length > 24 ? (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
                    Showing the first 24 available times. Narrow the window to see fewer options.
                  </Typography>
                ) : null}
              </>
            ) : availabilityCheckedAt && !availabilityConnect ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                No free blocks found for that meeting length and window.
              </Typography>
            ) : null}

            {availabilityBlock ? (
              <Box sx={{ mt: 1.25 }}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                  Preview
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    whiteSpace: "pre-wrap",
                    fontFamily: "inherit",
                    fontSize: 13,
                    bgcolor: "action.hover",
                    borderRadius: 1,
                    p: 1,
                    my: 0.75,
                  }}
                >
                  {availabilityBlock}
                </Box>
                <Button size="small" variant="contained" onClick={insertAvailability}>
                  Insert selected times
                </Button>
              </Box>
            ) : null}
          </Box>

          <Box sx={{ mt: 1.5 }}>
            <input ref={fileInputRef} type="file" multiple hidden onChange={addAttachments} />
            <Button
              size="small"
              variant="outlined"
              startIcon={<AttachFileIcon fontSize="small" />}
              onClick={() => fileInputRef.current?.click()}
            >
              Attach
            </Button>
            {attachments.length > 0 ? (
              <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 1 }}>
                {attachments.map((f, i) => (
                  <Chip
                    key={`${i}-${f.name}`}
                    size="small"
                    label={f.name}
                    onDelete={() => setAttachments((p) => p.filter((_, j) => j !== i))}
                  />
                ))}
              </Box>
            ) : null}
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              Up to {MAX_ATTACH_FILES} files, 25MB total (Gmail limit).
            </Typography>
          </Box>
        </Box>

        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: 1,
            px: 2,
            py: 1.25,
            borderTop: 1,
            borderColor: "divider",
          }}
        >
          <Button onClick={onClose} size="small">
            Cancel
          </Button>
          {draft ? (
            <Button onClick={handleSave} size="small" disabled={saving || draft.status === "SENT"}>
              {saving ? "Saving…" : "Save draft"}
            </Button>
          ) : null}
          <Button
            variant="contained"
            size="small"
            startIcon={<SendIcon fontSize="small" />}
            onClick={handleSend}
            disabled={sending || toAddrs.length === 0 || (draft && draft.status === "SENT")}
          >
            {sending ? "Sending…" : "Send"}
          </Button>
        </Box>
      </Box>
    </Drawer>
  );
}
