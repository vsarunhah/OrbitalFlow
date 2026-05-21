import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import Paper from "@mui/material/Paper";
import IconButton from "@mui/material/IconButton";
import Drawer from "@mui/material/Drawer";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import CircularProgress from "@mui/material/CircularProgress";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DownloadIcon from "@mui/icons-material/Download";
import RateReviewIcon from "@mui/icons-material/RateReview";
import SaveIcon from "@mui/icons-material/Save";
import PreviewOutlinedIcon from "@mui/icons-material/PreviewOutlined";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import CloseIcon from "@mui/icons-material/Close";
import { alpha } from "@mui/material/styles";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  fetchResumes,
  fetchResume,
  createResume,
  updateResume,
  deleteResume,
  reviewResume,
  exportResumePdf,
} from "../lib/api";
import {
  ensureParsedShape,
  formFromApi,
  generateId,
  getDefaultForm,
  markdownPayloadFromApi,
  structuredToMarkdown,
  toStoredJson,
} from "../lib/resumeStructured";
import ResumeFormEditor from "../components/ResumeFormEditor";
import ConfirmModal from "../components/ConfirmModal";

function ResumeListItemCard({ resume, onOpen, onDelete, onPreview }) {
  const updated = resume.updated_at
    ? new Date(resume.updated_at).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "";
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 1.5,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        cursor: "pointer",
        "&:hover": { bgcolor: "action.hover" },
      }}
      onClick={() => onOpen(resume.id)}
    >
      <Box>
        <Typography fontWeight={600}>{resume.name}</Typography>
        <Typography variant="body2" color="text.secondary">
          Updated {updated}
        </Typography>
      </Box>
      <Box sx={{ display: "flex", alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
        {onPreview && (
          <Tooltip title="Preview">
            <IconButton size="small" aria-label="Preview resume" onClick={() => onPreview(resume)}>
              <PreviewOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title="Delete">
          <IconButton size="small" aria-label="Delete" onClick={() => onDelete(resume)}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
    </Paper>
  );
}

function SuggestionsDrawer({ open, onClose, suggestions, onApply }) {
  return (
    <Drawer anchor="right" open={open} onClose={onClose}>
      <Box sx={{ width: 360, p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Review suggestions
        </Typography>
        {!suggestions || suggestions.length === 0 ? (
          <Typography color="text.secondary">No suggestions at this time.</Typography>
        ) : (
          <List dense>
            {suggestions.map((s, i) => (
              <ListItem
                key={i}
                alignItems="flex-start"
                sx={{
                  flexDirection: "column",
                  alignItems: "stretch",
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 1,
                  mb: 1,
                  p: 1.5,
                }}
              >
                <Typography variant="caption" color="primary.main" fontWeight={600}>
                  {s.section} · {s.suggestion_type}
                </Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>
                  {s.comment}
                </Typography>
                {s.current_value && (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                    Current: {String(s.current_value).slice(0, 120)}
                    {String(s.current_value).length > 120 ? "…" : ""}
                  </Typography>
                )}
                {s.suggested_value && (
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
                    Suggested: {String(s.suggested_value).slice(0, 120)}
                    {String(s.suggested_value).length > 120 ? "…" : ""}
                  </Typography>
                )}
                {s.suggested_value && (
                  <Button
                    size="small"
                    variant="outlined"
                    sx={{ mt: 1 }}
                    onClick={() => onApply(s)}
                  >
                    Apply
                  </Button>
                )}
              </ListItem>
            ))}
          </List>
        )}
        <Button onClick={onClose} sx={{ mt: 2 }}>
          Close
        </Button>
      </Box>
    </Drawer>
  );
}

const previewSx = {
  fontFamily: '"Helvetica Neue", Helvetica, Arial, sans-serif',
  fontSize: "11pt",
  lineHeight: 1.23,
  color: "text.primary",
  maxWidth: "7.5in",
  mx: "auto",
  "& h1": {
    fontSize: "16pt",
    fontWeight: 700,
    lineHeight: 1.2,
    mt: 0,
    mb: 1,
    pb: 0.5,
    borderBottom: 2,
    borderColor: "primary.main",
  },
  "& h2": { fontSize: "12pt", fontWeight: 700, color: "primary.main", mt: 2, mb: 0.75, lineHeight: 1.2 },
  "& h3": { fontSize: "11pt", fontWeight: 700, mt: 1.5, mb: 0.5, lineHeight: 1.2 },
  "& p": { my: 0.75, lineHeight: 1.23, fontSize: "11pt" },
  "& ul": { my: 0.75, pl: 2.5, fontSize: "10pt" },
  "& ol": { my: 0.75, pl: 2.5, fontSize: "10pt" },
  "& li": { mb: 0.35, lineHeight: 1.15 },
  "& a": { color: "primary.main" },
  "& table": { borderCollapse: "collapse", width: "100%", my: 1, fontSize: "11pt" },
  "& th, & td": { border: 1, borderColor: "divider", px: 1, py: 0.5 },
  "& th": { bgcolor: "action.hover" },
  "& code": {
    fontFamily: "ui-monospace, 'Courier New', monospace",
    fontSize: "9pt",
    bgcolor: "action.hover",
    px: 0.5,
    borderRadius: 0.5,
  },
};

/** Matches backend PDF: US Letter (11in) with 0.4in top and bottom margin (see resume_pdf.MARGIN). */
const PDF_PAGE_BODY_HEIGHT = "10.2in";

function MarkdownPreview({
  markdown,
  emptyFallback = "*Nothing to preview*",
  showPageGuides = true,
}) {
  const mdContent = markdown?.trim() ? markdown : emptyFallback;
  const inner = (
    <Box sx={previewSx}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{mdContent}</ReactMarkdown>
    </Box>
  );
  if (!showPageGuides) return inner;
  return (
    <Box sx={{ position: "relative" }}>
      <Box sx={{ position: "relative", zIndex: 1 }}>{inner}</Box>
      <Box
        aria-hidden
        sx={(theme) => ({
          position: "absolute",
          inset: 0,
          zIndex: 0,
          pointerEvents: "none",
          backgroundImage: `repeating-linear-gradient(
            to bottom,
            transparent 0,
            transparent calc(${PDF_PAGE_BODY_HEIGHT} - 3px),
            ${alpha(theme.palette.primary.main, 0.5)} calc(${PDF_PAGE_BODY_HEIGHT} - 3px),
            ${alpha(theme.palette.primary.main, 0.5)} calc(${PDF_PAGE_BODY_HEIGHT} - 1px),
            transparent calc(${PDF_PAGE_BODY_HEIGHT} - 1px),
            transparent ${PDF_PAGE_BODY_HEIGHT}
          )`,
        })}
      />
    </Box>
  );
}

function ResumePreviewDialog({
  open,
  title,
  markdown,
  loading,
  onClose,
  footer,
  onDownloadPdf,
  downloadLoading = false,
}) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth scroll="paper">
      <DialogTitle
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1,
          pr: 1,
          flexWrap: "wrap",
        }}
      >
        <Typography component="span" variant="h6" sx={{ fontSize: "1.1rem", flex: "1 1 auto", minWidth: 0 }}>
          {title}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, ml: "auto" }}>
          {onDownloadPdf && (
            <Tooltip title="PDF is generated from the saved resume on the server. Save first if you have unsaved changes.">
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={downloadLoading ? <CircularProgress size={16} /> : <DownloadIcon />}
                  disabled={downloadLoading || loading}
                  onClick={onDownloadPdf}
                >
                  Download PDF
                </Button>
              </span>
            </Tooltip>
          )}
          <IconButton aria-label="Close preview" onClick={onClose} size="small">
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>
      <DialogContent dividers sx={{ minHeight: 280 }}>
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress />
          </Box>
        ) : (
          <MarkdownPreview markdown={markdown} />
        )}
      </DialogContent>
      {footer}
    </Dialog>
  );
}

export default function ResumesPage() {
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [resume, setResume] = useState(null);
  const [editingName, setEditingName] = useState("");
  const [editingForm, setEditingForm] = useState(() => getDefaultForm());
  const [saveLoading, setSaveLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [editorLayout, setEditorLayout] = useState("split");
  const [listPreview, setListPreview] = useState(null);
  const [editPreviewOpen, setEditPreviewOpen] = useState(false);
  const [listExportLoading, setListExportLoading] = useState(false);

  const derivedMarkdown = useMemo(() => structuredToMarkdown(editingForm), [editingForm]);

  const loadList = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const list = await fetchResumes();
      setResumes(list);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const handleOpen = useCallback(async (id) => {
    setError(null);
    setSelectedId(id);
    try {
      const r = await fetchResume(id);
      setResume(r);
      setEditingName(r.name || "");
      setEditingForm(formFromApi(r.parsed_json));
      setEditorLayout("split");
      setEditPreviewOpen(false);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const handleBack = useCallback(() => {
    setSelectedId(null);
    setResume(null);
    setSuggestions([]);
    setSuggestionsOpen(false);
    setEditPreviewOpen(false);
    setListPreview(null);
    loadList();
  }, [loadList]);

  const handleSave = useCallback(async () => {
    if (!selectedId) return;
    setSaveLoading(true);
    setError(null);
    try {
      const updated = await updateResume(selectedId, {
        name: editingName,
        parsed_json: toStoredJson(editingForm),
      });
      setResume(updated);
      setEditingForm(formFromApi(updated.parsed_json));
    } catch (e) {
      setError(e.message);
    } finally {
      setSaveLoading(false);
    }
  }, [selectedId, editingName, editingForm]);

  const handleNew = useCallback(async () => {
    setError(null);
    setCreating(true);
    try {
      const form = getDefaultForm();
      const md = structuredToMarkdown(form);
      const created = await createResume({
        name: "Untitled resume",
        markdown: md,
        sourceForm: form,
      });
      setResumes((prev) => [created, ...prev]);
      await handleOpen(created.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }, [handleOpen]);

  const handleReview = useCallback(async () => {
    if (!selectedId) return;
    setReviewLoading(true);
    setError(null);
    try {
      const { suggestions: s } = await reviewResume(selectedId);
      setSuggestions(s || []);
      setSuggestionsOpen(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setReviewLoading(false);
    }
  }, [selectedId]);

  const applySuggestion = useCallback((s) => {
    if (!s.suggested_value) return;
    const ref = (s.section || "").trim();
    const refLower = ref.toLowerCase();
    if (refLower === "markdown" || refLower.startsWith("markdown")) {
      setEditingForm(formFromApi({ format: "markdown", markdown: String(s.suggested_value) }));
      return;
    }
    setEditingForm((prev) => {
      const next = JSON.parse(JSON.stringify(ensureParsedShape(prev)));
      const contactMatch = refLower;
      if (contactMatch === "name") {
        next.contact = next.contact || {};
        next.contact.name = s.suggested_value;
        return next;
      }
      if (contactMatch === "email") {
        next.contact = next.contact || {};
        next.contact.email = s.suggested_value;
        return next;
      }
      if (contactMatch === "phone") {
        next.contact = next.contact || {};
        next.contact.phone = s.suggested_value;
        return next;
      }
      if (contactMatch === "linkedin") {
        next.contact = next.contact || {};
        next.contact.linkedin = s.suggested_value;
        return next;
      }
      if (contactMatch === "websites" || contactMatch === "website") {
        next.contact = next.contact || {};
        next.contact.websites = s.suggested_value;
        return next;
      }
      const secIndexMatch = ref.match(/sections\[(\d+)\](?:\.items\[(\d+)\])?(?:\.(body|heading|subheading))?/);
      if (secIndexMatch) {
        const si = parseInt(secIndexMatch[1], 10);
        const itemIndex = secIndexMatch[2] != null ? parseInt(secIndexMatch[2], 10) : null;
        const field = secIndexMatch[3] || "text";
        if (si < 0 || !next.sections || si >= next.sections.length) return next;
        const sec = next.sections[si];
        if (itemIndex != null) {
          if (!sec.items) sec.items = [];
          if (itemIndex < sec.items.length) {
            sec.items[itemIndex][field] = s.suggested_value;
          }
        } else if (field === "text") {
          sec.text = s.suggested_value;
        }
        return next;
      }
      const byName = next.sections.find(
        (sec) => sec.name && sec.name.toLowerCase() === refLower,
      );
      if (byName) {
        if (byName.content_type === "text") byName.text = s.suggested_value;
        return next;
      }
      if (refLower === "summary") {
        const sum = next.sections.find((sec) => sec.name && sec.name.toLowerCase() === "summary");
        if (sum) sum.text = s.suggested_value;
        else {
          next.sections.push({
            id: generateId(),
            name: "Summary",
            order: next.sections.length,
            content_type: "text",
            text: s.suggested_value,
            items: [],
          });
        }
        return next;
      }
      if (refLower.includes("skills")) {
        const sk = next.sections.find((sec) => sec.name && sec.name.toLowerCase() === "skills");
        if (sk) {
          sk.items = s.suggested_value
            .split(/[,;\n]+/)
            .map((x) => ({ heading: "", subheading: "", body: x.trim() }))
            .filter((x) => x.body);
        }
        return next;
      }
      return next;
    });
  }, []);

  const handleExport = useCallback(async () => {
    if (!selectedId) return;
    setExportLoading(true);
    setError(null);
    try {
      await exportResumePdf(selectedId);
    } catch (e) {
      setError(e.message);
    } finally {
      setExportLoading(false);
    }
  }, [selectedId]);

  const handleListPreviewExport = useCallback(async () => {
    const id = listPreview?.id;
    if (!id) return;
    setListExportLoading(true);
    setError(null);
    try {
      await exportResumePdf(id);
    } catch (e) {
      setError(e.message);
    } finally {
      setListExportLoading(false);
    }
  }, [listPreview?.id]);

  const openListPreview = useCallback(async (r) => {
    setListPreview({ id: r.id, title: r.name, markdown: "", loading: true });
    try {
      const full = await fetchResume(r.id);
      setListPreview({
        id: r.id,
        title: full.name || r.name,
        markdown: markdownPayloadFromApi(full.parsed_json),
        loading: false,
      });
    } catch (e) {
      setError(e.message);
      setListPreview(null);
    }
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      await deleteResume(deleteTarget.id);
      if (selectedId === deleteTarget.id) handleBack();
      else loadList();
    } catch (e) {
      setError(e.message);
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, selectedId, handleBack, loadList]);

  if (selectedId && resume) {
    return (
      <Box sx={{ maxWidth: 1200, mx: "auto", p: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
          <IconButton onClick={handleBack} aria-label="Back to list">
            <ArrowBackIcon />
          </IconButton>
          <Typography variant="h6">Edit resume</Typography>
        </Box>
        {error && (
          <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        <TextField
          fullWidth
          label="Resume name"
          value={editingName}
          onChange={(e) => setEditingName(e.target.value)}
          sx={{ mb: 2 }}
        />

        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            flexWrap: "wrap",
            mb: 1,
          }}
        >
          <Typography variant="subtitle2" color="text.secondary">
            Details
          </Typography>
          <ToggleButtonGroup
            value={editorLayout}
            exclusive
            onChange={(_, v) => v != null && setEditorLayout(v)}
            size="small"
            aria-label="Form and preview layout"
          >
            <ToggleButton value="split">Split</ToggleButton>
            <ToggleButton value="form">Form only</ToggleButton>
            <ToggleButton value="preview">Preview only</ToggleButton>
          </ToggleButtonGroup>
          <Tooltip title="Open large preview (Markdown)">
            <IconButton size="small" aria-label="Open large preview" onClick={() => setEditPreviewOpen(true)}>
              <OpenInFullIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          Fill in the form; the preview shows Markdown generated for PDF export and review.
        </Typography>

        <Box
          sx={{
            display: "flex",
            flexDirection:
              editorLayout === "split" ? { xs: "column", md: "row" } : "column",
            gap: 2,
            alignItems: "stretch",
            mb: 2,
          }}
        >
          {editorLayout !== "preview" && (
            <Box
              sx={{
                flex: editorLayout === "split" ? 1 : undefined,
                minWidth: 0,
                maxHeight: editorLayout === "split" ? { md: "min(70vh, 720px)" } : undefined,
                overflow: editorLayout === "split" ? { md: "auto" } : "visible",
              }}
            >
              <ResumeFormEditor value={editingForm} onChange={(next) => setEditingForm(ensureParsedShape(next))} />
            </Box>
          )}
          {editorLayout !== "form" && (
            <Paper
              variant="outlined"
              sx={{
                flex: editorLayout === "split" ? 1 : undefined,
                minWidth: 0,
                p: 2,
                maxHeight: { md: "min(70vh, 720px)" },
                overflow: "auto",
                bgcolor: "background.default",
              }}
            >
              <Box
                sx={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  gap: 1,
                  mb: 1,
                  flexWrap: "wrap",
                }}
              >
                <Typography variant="caption" color="text.secondary" sx={{ flex: "1 1 200px", minWidth: 0 }}>
                  Horizontal lines mark approximate page breaks (US Letter, same margins as export). Preview uses
                  the same point sizes and column width as the PDF; spacing may still differ slightly.
                </Typography>
                <Tooltip title="PDF is generated from the saved resume on the server. Save first if you have unsaved changes.">
                  <span>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={exportLoading ? <CircularProgress size={16} /> : <DownloadIcon />}
                      disabled={exportLoading}
                      onClick={handleExport}
                    >
                      Download PDF
                    </Button>
                  </span>
                </Tooltip>
              </Box>
              <MarkdownPreview markdown={derivedMarkdown} />
            </Paper>
          )}
        </Box>

        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          <Button
            variant="contained"
            startIcon={saveLoading ? <CircularProgress size={18} /> : <SaveIcon />}
            disabled={saveLoading}
            onClick={handleSave}
          >
            Save
          </Button>
          <Button
            variant="outlined"
            startIcon={reviewLoading ? <CircularProgress size={18} /> : <RateReviewIcon />}
            disabled={reviewLoading}
            onClick={handleReview}
          >
            Review resume
          </Button>
          <Button
            variant="outlined"
            startIcon={exportLoading ? <CircularProgress size={18} /> : <DownloadIcon />}
            disabled={exportLoading}
            onClick={handleExport}
          >
            Download PDF
          </Button>
        </Box>

        <ResumePreviewDialog
          open={editPreviewOpen}
          title={editingName ? `Preview — ${editingName}` : "Preview"}
          markdown={derivedMarkdown}
          loading={false}
          onClose={() => setEditPreviewOpen(false)}
          onDownloadPdf={handleExport}
          downloadLoading={exportLoading}
        />

        <SuggestionsDrawer
          open={suggestionsOpen}
          onClose={() => setSuggestionsOpen(false)}
          suggestions={suggestions}
          onApply={applySuggestion}
        />
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 600, mx: "auto", p: 2 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Resumes
      </Typography>
      {error && (
        <Alert severity="error" onClose={() => setError(null)} sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
        <Button
          variant="contained"
          disabled={creating}
          startIcon={creating ? <CircularProgress size={18} /> : <AddIcon />}
          onClick={handleNew}
        >
          {creating ? "Creating…" : "New resume"}
        </Button>
      </Box>
      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <CircularProgress />
        </Box>
      ) : resumes.length === 0 ? (
        <Typography color="text.secondary">
          No resumes yet. Create one by filling in the form; we convert it to Markdown for preview and PDF.
        </Typography>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {resumes.map((r) => (
            <ResumeListItemCard
              key={r.id}
              resume={r}
              onOpen={handleOpen}
              onPreview={openListPreview}
              onDelete={(res) => setDeleteTarget(res)}
            />
          ))}
        </Box>
      )}

      <ResumePreviewDialog
        open={!!listPreview}
        title={listPreview?.title || "Preview"}
        markdown={listPreview?.markdown}
        loading={!!listPreview?.loading}
        onClose={() => setListPreview(null)}
        onDownloadPdf={listPreview?.id ? handleListPreviewExport : undefined}
        downloadLoading={listExportLoading}
        footer={
          <DialogActions sx={{ px: 2, pb: 2 }}>
            <Button onClick={() => setListPreview(null)}>Close</Button>
            <Button
              variant="contained"
              onClick={() => {
                const id = listPreview?.id;
                setListPreview(null);
                if (id) handleOpen(id);
              }}
            >
              Edit
            </Button>
          </DialogActions>
        }
      />

      <ConfirmModal
        open={!!deleteTarget}
        title="Delete resume"
        message={deleteTarget ? `Delete "${deleteTarget.name}"? This cannot be undone.` : ""}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
        confirmLabel="Delete"
        confirmColor="error"
      />
    </Box>
  );
}
