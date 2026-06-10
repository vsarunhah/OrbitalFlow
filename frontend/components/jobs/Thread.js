import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import CircularProgress from "@mui/material/CircularProgress";
import LightModeOutlinedIcon from "@mui/icons-material/LightModeOutlined";
import AttachFileOutlinedIcon from "@mui/icons-material/AttachFileOutlined";
import { alpha } from "@mui/material/styles";
import EmailBody from "./EmailBody";
import StageDot from "./StageDot";
import { parseFromAddress, stripHtmlToPlain } from "./email";
import { downloadMessageAttachment } from "../../lib/api";

/**
 * Unified job thread: events + received + sent, newest first. Messages are
 * card-like blocks; system events read as light annotations (not a log tail).
 */

const EVENT_TYPE_LABELS = {
  APPLICATION_RECEIVED: "Application received",
  INTERVIEW_REQUEST: "Interview request",
  INTERVIEW_SCHEDULED: "Interview scheduled",
  INTERVIEW_RESCHEDULE: "Interview rescheduled",
  TAKEHOME_REQUEST: "Take-home request",
  OFFER: "Offer",
  REJECTION: "Rejection",
  FOLLOW_UP: "Follow-up",
  JOB_ALERT: "Job alert",
  REPLY_SENT: "Reply sent",
  NONE: "No event",
  STAGE_CHANGE: "Stage change",
};

function formatEventType(raw) {
  if (raw == null || raw === "") return "Activity";
  if (EVENT_TYPE_LABELS[raw]) return EVENT_TYPE_LABELS[raw];
  return String(raw)
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function normalizeItems(timeline) {
  const merged = [];
  (timeline?.events || []).forEach((e) =>
    merged.push({ kind: "event", id: `ev-${e.id}`, at: e.created_at, data: e })
  );
  (timeline?.messages || []).forEach((m) =>
    merged.push({
      kind: "received",
      id: `msg-${m.id}`,
      at: m.date_header || m.id,
      data: m,
    })
  );
  (timeline?.sent_messages || []).forEach((s) =>
    merged.push({ kind: "sent", id: `sent-${s.id}`, at: s.sent_at, data: s })
  );
  merged.sort((a, b) => new Date(b.at) - new Date(a.at));
  return merged;
}

function shortSnippet(msg) {
  const s = msg.body_snippet || msg.body_text || "";
  if (s) return s.replace(/\s+/g, " ").trim().slice(0, 140);
  const stripped = msg.body_html ? stripHtmlToPlain(msg.body_html) : "";
  return stripped.slice(0, 140);
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatBytes(n) {
  if (n == null || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function attachmentCollapsedLabel(attachments) {
  if (!attachments?.length) return null;
  if (attachments.length === 1) return attachments[0].filename;
  return `${attachments.length} attachments`;
}

function MessageAttachments({ messageId, attachments }) {
  const [downloadingId, setDownloadingId] = useState(null);
  const [error, setError] = useState(null);

  if (!attachments?.length) {
    return null;
  }

  const handleDownload = async (att, e) => {
    e.stopPropagation();
    setError(null);
    setDownloadingId(att.id);
    try {
      await downloadMessageAttachment(messageId, att.id, att.filename);
    } catch (err) {
      const msg = err?.message || "Download failed";
      setError(
        msg.includes("403") || /reconnect/i.test(msg)
          ? "Could not download — reconnect Gmail in Settings."
          : msg
      );
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <Box
      sx={{ mt: 1.5, alignSelf: "flex-start", maxWidth: "100%" }}
      onClick={(e) => e.stopPropagation()}
    >
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
        Attachments
      </Typography>
      {error ? (
        <Typography variant="caption" color="error" sx={{ display: "block", mb: 0.5 }}>
          {error}
        </Typography>
      ) : null}
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 0.25 }}>
        {attachments.map((att) => (
          <Box
            key={att.id}
            component="button"
            type="button"
            disabled={downloadingId === att.id}
            onClick={(e) => handleDownload(att, e)}
            title={att.filename}
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: 0.75,
              width: "auto",
              maxWidth: 320,
              textAlign: "left",
              border: 1,
              borderColor: "divider",
              bgcolor: (theme) => alpha(theme.palette.background.paper, 0.6),
              cursor: downloadingId === att.id ? "wait" : "pointer",
              py: 0.5,
              px: 1,
              borderRadius: 1,
              color: "primary.main",
              "&:hover": { bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08) },
              "&:disabled": { opacity: 0.6 },
            }}
          >
            {downloadingId === att.id ? (
              <CircularProgress size={14} />
            ) : (
              <AttachFileOutlinedIcon sx={{ fontSize: 18, flexShrink: 0 }} />
            )}
            <Typography
              variant="body2"
              sx={{
                fontSize: 13,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {att.filename}
            </Typography>
            {att.size_bytes ? (
              <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
                {formatBytes(att.size_bytes)}
              </Typography>
            ) : null}
          </Box>
        ))}
      </Box>
    </Box>
  );
}

function MessageRow({ item, defaultExpanded }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [readingLight, setReadingLight] = useState(false);
  const isSent = item.kind === "sent";
  const d = item.data;
  const attachments = !isSent ? d.attachments || [] : [];
  const attLabel = !isSent ? attachmentCollapsedLabel(attachments) : null;
  const toLabel = isSent
    ? (() => {
        try {
          const arr = JSON.parse(d.to_addrs_json || "[]");
          return Array.isArray(arr) && arr.length ? `To ${arr.join(", ")}` : "Sent";
        } catch {
          return "Sent";
        }
      })()
    : null;
  const fromParsed = isSent ? null : parseFromAddress(d.from_address || "");
  const subject = d.subject || "(no subject)";
  const snippet = shortSnippet(d);
  const when = isSent ? d.sent_at : d.date_header;

  return (
    <Box
      sx={{
        border: 1,
        borderColor: "divider",
        borderRadius: 2,
        bgcolor: "background.paper",
        overflow: "hidden",
        boxShadow: (theme) =>
          theme.palette.mode === "dark"
            ? "0 1px 0 rgba(0,0,0,0.35)"
            : "0 1px 3px rgba(0,0,0,0.06)",
      }}
    >
      <Box
        onClick={() => setExpanded((v) => !v)}
        sx={{
          display: "flex",
          flexDirection: "row",
          alignItems: "flex-start",
          gap: 1.5,
          py: 1.75,
          px: 2,
          cursor: "pointer",
          "&:hover": { bgcolor: (theme) => alpha(theme.palette.action.hover, 0.4) },
        }}
      >
        <Box
          sx={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            mt: 0.6,
            flexShrink: 0,
            bgcolor: isSent ? "success.main" : "primary.main",
          }}
        />
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Box
            sx={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: 1.5,
            }}
          >
            <Box sx={{ minWidth: 0, flex: 1 }}>
              {isSent ? (
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
                  <Typography
                    fontWeight={600}
                    fontSize={14}
                    sx={{
                      minWidth: 0,
                      lineHeight: 1.3,
                    }}
                  >
                    {toLabel}
                  </Typography>
                  <Chip
                    label="Sent"
                    size="small"
                    color="success"
                    variant="outlined"
                    sx={{ height: 20, fontSize: 10 }}
                  />
                </Box>
              ) : (
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "baseline",
                    gap: 0.5,
                    minWidth: 0,
                    flexWrap: "wrap",
                  }}
                >
                  <Typography
                    fontWeight={600}
                    fontSize={14}
                    sx={{ minWidth: 0, lineHeight: 1.3 }}
                  >
                    {fromParsed.display}
                  </Typography>
                  {expanded && fromParsed.email && fromParsed.display !== fromParsed.email ? (
                    <Typography
                      component="span"
                      color="text.secondary"
                      fontSize={14}
                      fontWeight={400}
                    >
                      &lt;{fromParsed.email}&gt;
                    </Typography>
                  ) : null}
                </Box>
              )}
            </Box>
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.5,
                flexShrink: 0,
                pt: 0.1,
              }}
            >
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: 12 }}>
                {fmtTime(when)}
              </Typography>
              {!isSent && d.provider_msg_id ? (
                <Link
                  href={`https://mail.google.com/mail/u/0/#all/${d.provider_msg_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  color="text.secondary"
                  onClick={(e) => e.stopPropagation()}
                  sx={{ opacity: 0.7, "&:hover": { opacity: 1 }, fontSize: 14, lineHeight: 1 }}
                  title="Open in Gmail"
                >
                  ↗
                </Link>
              ) : null}
            </Box>
          </Box>
          {!expanded ? (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                mt: 0.75,
                fontSize: 13,
                lineHeight: 1.45,
                overflow: "hidden",
                textOverflow: "ellipsis",
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
              }}
            >
              {snippet}
            </Typography>
          ) : null}
          {!expanded && attLabel ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: 0.5, display: "flex", alignItems: "center", gap: 0.5, fontSize: 12 }}
            >
              <AttachFileOutlinedIcon sx={{ fontSize: 14 }} />
              {attLabel}
            </Typography>
          ) : null}
          {expanded ? (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ mt: 0.5, display: "block", fontSize: 13, lineHeight: 1.35 }}
            >
              {subject}
            </Typography>
          ) : null}
        </Box>
      </Box>
      <Collapse in={expanded} unmountOnExit>
        <Box sx={{ px: 2, pb: 2.5, pt: 0.5 }}>
          <Box
            sx={{
              display: "flex",
              justifyContent: "flex-end",
              mb: 0.75,
              minHeight: 32,
              alignItems: "center",
            }}
          >
            <Tooltip
              title={
                readingLight
                  ? "Use the app background for this message"
                  : "Show message on a light background (easier to read in dark mode)"
              }
            >
              <IconButton
                size="small"
                aria-pressed={readingLight}
                aria-label={
                  readingLight ? "Use app theme for message body" : "Light background for message body"
                }
                color={readingLight ? "primary" : "default"}
                onClick={(e) => {
                  e.stopPropagation();
                  setReadingLight((v) => !v);
                }}
              >
                <LightModeOutlinedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          <EmailBody
            html={d.body_html}
            text={d.body_text || d.body_snippet}
            readingLight={readingLight}
          />
          {!isSent ? (
            <MessageAttachments messageId={d.id} attachments={attachments} />
          ) : null}
        </Box>
      </Collapse>
    </Box>
  );
}

function EventRow({ data }) {
  const from = data.stage_before;
  const to = data.stage_after;
  const typeLabel = formatEventType(data.event_type);
  const sameStage = from && to && from === to;
  const showTransition = from && to && !sameStage;

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "stretch",
        gap: 1.25,
        pl: 1.5,
        pr: 2,
        py: 1.1,
        borderRadius: 1,
        bgcolor: (theme) => alpha(theme.palette.text.primary, 0.04),
      }}
    >
      <Box
        sx={{
          width: 3,
          borderRadius: 1,
          flexShrink: 0,
          bgcolor: (theme) => alpha(theme.palette.text.primary, 0.18),
        }}
      />
      <Box sx={{ minWidth: 0, flex: 1, py: 0.1 }}>
        <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 0.75, columnGap: 1.25 }}>
          <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500, fontSize: 13 }}>
            {typeLabel}
          </Typography>
          {showTransition ? (
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap" }}>
              <StageDot stage={from} size={6} showTooltip={false} />
              <Typography variant="body2" color="text.disabled" fontSize={12}>
                {from}
              </Typography>
              <Typography variant="body2" color="text.disabled" fontSize={12} sx={{ mx: 0.25 }}>
                →
              </Typography>
              <StageDot stage={to} size={6} showTooltip={false} />
              <Typography variant="body2" color="text.disabled" fontSize={12}>
                {to}
              </Typography>
            </Box>
          ) : null}
        </Box>
        {data.rationale ? (
          <Typography
            variant="body2"
            color="text.disabled"
            fontStyle="italic"
            sx={{ mt: 0.35, fontSize: 12, lineHeight: 1.4, display: "block" }}
          >
            {data.rationale}
          </Typography>
        ) : null}
        {sameStage && from && !data.rationale ? (
          <Typography variant="body2" color="text.disabled" fontSize={12} sx={{ mt: 0.2 }}>
            {from}
          </Typography>
        ) : null}
      </Box>
      <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0, fontSize: 11, alignSelf: "flex-start" }}>
        {fmtTime(data.created_at)}
      </Typography>
    </Box>
  );
}

export default function Thread({ timeline }) {
  const items = useMemo(() => normalizeItems(timeline), [timeline]);
  if (!items.length) {
    return (
      <Box sx={{ py: 4, textAlign: "center" }}>
        <Typography color="text.secondary" fontStyle="italic">
          No events or messages yet.
        </Typography>
      </Box>
    );
  }
  const newestMessageIndex = (() => {
    for (let i = 0; i < items.length; i++) {
      if (items[i].kind !== "event") return i;
    }
    return -1;
  })();

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
        mt: 1,
      }}
    >
      {items.map((item, i) =>
        item.kind === "event" ? (
          <EventRow key={item.id} data={item.data} />
        ) : (
          <MessageRow
            key={item.id}
            item={item}
            defaultExpanded={i === newestMessageIndex}
          />
        )
      )}
    </Box>
  );
}
