import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Alert from "@mui/material/Alert";
import Paper from "@mui/material/Paper";
import IconButton from "@mui/material/IconButton";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import CircularProgress from "@mui/material/CircularProgress";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DownloadIcon from "@mui/icons-material/Download";
import RateReviewIcon from "@mui/icons-material/RateReview";
import SaveIcon from "@mui/icons-material/Save";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import {
  fetchResumes,
  fetchResume,
  uploadResume,
  updateResume,
  deleteResume,
  reviewResume,
  exportResumePdf,
} from "../lib/api";
import ConfirmModal from "../components/ConfirmModal";

function generateId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

const defaultParsed = () => ({
  contact: { name: "", email: "", phone: "" },
  sections: [],
});

function ensureParsedShape(parsed) {
  if (!parsed || typeof parsed !== "object") return defaultParsed();
  if (parsed.sections && Array.isArray(parsed.sections)) {
    const contact = parsed.contact && typeof parsed.contact === "object"
      ? {
          name: parsed.contact.name ?? "",
          email: parsed.contact.email ?? "",
          phone: parsed.contact.phone ?? "",
        }
      : {
          name: parsed.name ?? "",
          email: parsed.email ?? "",
          phone: parsed.phone ?? "",
        };
    const sections = parsed.sections.map((s, i) => ({
      id: s.id || generateId(),
      name: s.name ?? "Section",
      order: typeof s.order === "number" ? s.order : i,
      content_type: s.content_type === "list" ? "list" : "text",
      text: s.content_type === "text" ? (s.text ?? "") : "",
      items: (s.content_type === "list" && Array.isArray(s.items))
        ? s.items.map((it) => ({
            heading: it?.heading ?? "",
            subheading: it?.subheading ?? "",
            body: it?.body ?? "",
          }))
        : [],
    }));
    sections.sort((a, b) => a.order - b.order);
    sections.forEach((s, i) => {
      s.order = i;
    });
    return { contact, sections };
  }
  const contact = {
    name: parsed.name ?? "",
    email: parsed.email ?? "",
    phone: parsed.phone ?? "",
  };
  const sections = [];
  let order = 0;
  if (parsed.summary) {
    sections.push({
      id: "summary",
      name: "Summary",
      order: order++,
      content_type: "text",
      text: parsed.summary,
      items: [],
    });
  }
  const exp = parsed.experience || [];
  if (exp.length) {
    sections.push({
      id: "experience",
      name: "Experience",
      order: order++,
      content_type: "list",
      text: null,
      items: exp.map((e) => ({
        heading: e?.title ?? "",
        subheading: [e?.company, e?.dates].filter(Boolean).join(" — "),
        body: e?.description ?? "",
      })),
    });
  }
  const edu = parsed.education || [];
  if (edu.length) {
    sections.push({
      id: "education",
      name: "Education",
      order: order++,
      content_type: "list",
      text: null,
      items: edu.map((e) => ({
        heading: e?.degree ?? "",
        subheading: [e?.institution, e?.dates].filter(Boolean).join(" — "),
        body: "",
      })),
    });
  }
  const sk = parsed.skills;
  if (sk && (Array.isArray(sk) ? sk.length : sk)) {
    sections.push({
      id: "skills",
      name: "Skills",
      order: order++,
      content_type: "list",
      text: null,
      items: (Array.isArray(sk) ? sk : [sk]).map((s) => ({ heading: "", subheading: "", body: String(s) })),
    });
  }
  sections.forEach((s, i) => {
    s.order = i;
  });
  return { contact, sections };
}

function ResumeListItemCard({ resume, onOpen, onDelete }) {
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
      <IconButton
        size="small"
        aria-label="Delete"
        onClick={(e) => {
          e.stopPropagation();
          onDelete(resume);
        }}
      >
        <DeleteOutlineIcon fontSize="small" />
      </IconButton>
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

export default function ResumesPage() {
  const [resumes, setResumes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [resume, setResume] = useState(null);
  const [editingName, setEditingName] = useState("");
  const [editingParsed, setEditingParsed] = useState(defaultParsed());
  const [saveLoading, setSaveLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

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
      setEditingParsed(ensureParsedShape(r.parsed_json));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const handleBack = useCallback(() => {
    setSelectedId(null);
    setResume(null);
    setSuggestions([]);
    setSuggestionsOpen(false);
    loadList();
  }, [loadList]);

  const handleSave = useCallback(async () => {
    if (!selectedId) return;
    setSaveLoading(true);
    setError(null);
    try {
      const updated = await updateResume(selectedId, {
        name: editingName,
        parsed_json: editingParsed,
      });
      setResume(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaveLoading(false);
    }
  }, [selectedId, editingName, editingParsed]);

  const handleUpload = useCallback(async (e) => {
    const file = e.target?.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const created = await uploadResume(file);
      setResumes((prev) => [created, ...prev]);
      handleOpen(created.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      e.target.value = "";
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
    setEditingParsed((prev) => {
      const next = JSON.parse(JSON.stringify(prev));
      const contactMatch = ref.toLowerCase();
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
        } else {
          if (field === "text") sec.text = s.suggested_value;
        }
        return next;
      }
      const byName = next.sections.find(
        (sec) => sec.name && sec.name.toLowerCase() === ref.toLowerCase()
      );
      if (byName) {
        if (byName.content_type === "text") byName.text = s.suggested_value;
        return next;
      }
      if (ref.toLowerCase() === "summary") {
        const sum = next.sections.find((sec) => sec.name && sec.name.toLowerCase() === "summary");
        if (sum) sum.text = s.suggested_value;
        else next.sections.push({ id: generateId(), name: "Summary", order: next.sections.length, content_type: "text", text: s.suggested_value, items: [] });
        return next;
      }
      if (ref.toLowerCase().includes("skills")) {
        const sk = next.sections.find((sec) => sec.name && sec.name.toLowerCase() === "skills");
        if (sk) {
          sk.items = s.suggested_value.split(/[,;\n]+/).map((x) => ({ heading: "", subheading: "", body: x.trim() })).filter((x) => x.body);
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

  const updateContact = (field, value) => {
    setEditingParsed((prev) => ({
      ...prev,
      contact: { ...(prev.contact || {}), [field]: value },
    }));
  };

  const updateSection = (sectionIndex, updates) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      sections[sectionIndex] = { ...sections[sectionIndex], ...updates };
      return { ...prev, sections };
    });
  };

  const updateSectionItem = (sectionIndex, itemIndex, field, value) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      const sec = { ...sections[sectionIndex], items: [...(sections[sectionIndex].items || [])] };
      sec.items[itemIndex] = { ...sec.items[itemIndex], [field]: value };
      sections[sectionIndex] = sec;
      return { ...prev, sections };
    });
  };

  const moveSection = (fromIndex, direction) => {
    const toIndex = direction === "up" ? fromIndex - 1 : fromIndex + 1;
    if (toIndex < 0 || toIndex >= (editingParsed.sections || []).length) return;
    setEditingParsed((prev) => {
      const sections = [...prev.sections];
      [sections[fromIndex], sections[toIndex]] = [sections[toIndex], sections[fromIndex]];
      sections.forEach((s, i) => {
        s.order = i;
      });
      return { ...prev, sections };
    });
  };

  const addSection = () => {
    setEditingParsed((prev) => ({
      ...prev,
      sections: [
        ...(prev.sections || []),
        { id: generateId(), name: "New Section", order: (prev.sections || []).length, content_type: "text", text: "", items: [] },
      ],
    }));
  };

  const removeSection = (index) => {
    setEditingParsed((prev) => {
      const sections = (prev.sections || []).filter((_, i) => i !== index);
      sections.forEach((s, i) => {
        s.order = i;
      });
      return { ...prev, sections };
    });
  };

  const addSectionItem = (sectionIndex) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      const sec = { ...sections[sectionIndex], items: [...(sections[sectionIndex].items || []), { heading: "", subheading: "", body: "" }] };
      sections[sectionIndex] = sec;
      return { ...prev, sections };
    });
  };

  const removeSectionItem = (sectionIndex, itemIndex) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      const sec = { ...sections[sectionIndex], items: (sections[sectionIndex].items || []).filter((_, i) => i !== itemIndex) };
      sections[sectionIndex] = sec;
      return { ...prev, sections };
    });
  };

  /** Body as newline-separated bullets → array (empty body → one empty string for one textbox). */
  const getBullets = (body) => {
    if (body == null || body === "") return [""];
    const lines = String(body).split(/\n/).map((l) => l.trim());
    return lines.length ? lines : [""];
  };

  const updateSectionItemBullet = (sectionIndex, itemIndex, bulletIndex, value) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      const sec = sections[sectionIndex];
      const items = [...(sec.items || [])];
      const item = { ...items[itemIndex] };
      const bullets = getBullets(item.body);
      const next = [...bullets];
      if (bulletIndex >= next.length) next.length = bulletIndex + 1;
      next[bulletIndex] = value;
      item.body = next.join("\n");
      items[itemIndex] = item;
      sections[sectionIndex] = { ...sec, items };
      return { ...prev, sections };
    });
  };

  const addSectionItemBullet = (sectionIndex, itemIndex) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      const sec = sections[sectionIndex];
      const items = [...(sec.items || [])];
      const item = { ...items[itemIndex] };
      const bullets = getBullets(item.body);
      item.body = [...bullets, ""].join("\n");
      items[itemIndex] = item;
      sections[sectionIndex] = { ...sec, items };
      return { ...prev, sections };
    });
  };

  const removeSectionItemBullet = (sectionIndex, itemIndex, bulletIndex) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      const sec = sections[sectionIndex];
      const items = [...(sec.items || [])];
      const item = { ...items[itemIndex] };
      const bullets = getBullets(item.body).filter((_, i) => i !== bulletIndex);
      item.body = bullets.join("\n");
      items[itemIndex] = item;
      sections[sectionIndex] = { ...sec, items };
      return { ...prev, sections };
    });
  };

  const parseExperienceMeta = (subheading) => {
    if (!subheading) {
      return { company: "", location: "", startDate: "", endDate: "" };
    }
    const parts = String(subheading).split("|").map((p) => p.trim()).filter(Boolean);
    const company = parts[0] || "";
    let location = "";
    let datePart = "";
    if (parts.length >= 3) {
      location = parts[1];
      datePart = parts.slice(2).join(" | ");
    } else if (parts.length === 2) {
      datePart = parts[1];
    }
    let startDate = "";
    let endDate = "";
    const m = datePart.match(/^(.*?)-(.*)$/);
    if (m) {
      startDate = m[1].trim();
      endDate = m[2].trim();
    } else {
      startDate = datePart;
    }
    return { company, location, startDate, endDate };
  };

  const formatExperienceMeta = ({ company, location, startDate, endDate }) => {
    const parts = [];
    if (company) parts.push(company);
    if (location) parts.push(location);
    const datePart =
      startDate || endDate
        ? [startDate, endDate || "Present"].filter(Boolean).join(" - ")
        : "";
    if (datePart) parts.push(datePart);
    return parts.join(" | ");
  };

  const updateExperienceMetaField = (sectionIndex, itemIndex, field, value) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      const sec = sections[sectionIndex];
      const items = [...(sec.items || [])];
      const item = { ...items[itemIndex] };
      const meta = parseExperienceMeta(item.subheading);
      const nextMeta = { ...meta, [field]: value };
      item.subheading = formatExperienceMeta(nextMeta);
      items[itemIndex] = item;
      sections[sectionIndex] = { ...sec, items };
      return { ...prev, sections };
    });
  };

  const setSectionContentType = (sectionIndex, content_type) => {
    setEditingParsed((prev) => {
      const sections = [...(prev.sections || [])];
      sections[sectionIndex] = {
        ...sections[sectionIndex],
        content_type,
        text: content_type === "text" ? (sections[sectionIndex].text || "") : "",
        items: content_type === "list" ? (sections[sectionIndex].items?.length ? sections[sectionIndex].items : [{ heading: "", subheading: "", body: "" }]) : [],
      };
      return { ...prev, sections };
    });
  };

  const contact = editingParsed.contact || {};
  const sections = editingParsed.sections || [];

  if (selectedId && resume) {
    return (
      <Box sx={{ maxWidth: 800, mx: "auto", p: 2 }}>
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
        <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 2, mb: 1 }}>
          Contact
        </Typography>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5, mb: 3 }}>
          <TextField
            size="small"
            label="Full name"
            value={contact.name}
            onChange={(e) => updateContact("name", e.target.value)}
          />
          <TextField
            size="small"
            label="Email"
            type="email"
            value={contact.email}
            onChange={(e) => updateContact("email", e.target.value)}
          />
          <TextField
            size="small"
            label="Phone"
            value={contact.phone}
            onChange={(e) => updateContact("phone", e.target.value)}
          />
        </Box>

        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          Sections (drag order with arrows)
        </Typography>
        {sections.map((sec, secIdx) => (
          <Paper key={sec.id || secIdx} variant="outlined" sx={{ p: 2, mb: 2 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 1.5 }}>
              <IconButton size="small" onClick={() => moveSection(secIdx, "up")} disabled={secIdx === 0} aria-label="Move up">
                <ArrowUpwardIcon fontSize="small" />
              </IconButton>
              <IconButton size="small" onClick={() => moveSection(secIdx, "down")} disabled={secIdx === sections.length - 1} aria-label="Move down">
                <ArrowDownwardIcon fontSize="small" />
              </IconButton>
              <TextField
                size="small"
                label="Section name"
                value={sec.name}
                onChange={(e) => updateSection(secIdx, { name: e.target.value })}
                sx={{ width: 200 }}
              />
              <Button
                size="small"
                variant={sec.content_type === "text" ? "outlined" : "text"}
                onClick={() => setSectionContentType(secIdx, "text")}
              >
                Text
              </Button>
              <Button
                size="small"
                variant={sec.content_type === "list" ? "outlined" : "text"}
                onClick={() => setSectionContentType(secIdx, "list")}
              >
                List
              </Button>
              <IconButton size="small" onClick={() => removeSection(secIdx)} aria-label="Remove section">
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Box>
            {sec.content_type === "text" ? (
              <TextField
                fullWidth
                multiline
                rows={4}
                label="Content"
                value={sec.text || ""}
                onChange={(e) => updateSection(secIdx, { text: e.target.value })}
              />
            ) : (
              <>
                {(sec.items || []).map((item, itemIdx) => {
                  const isExperience = (sec.name || "").toLowerCase() === "experience";
                  const bullets = getBullets(item.body);
                  const meta = isExperience ? parseExperienceMeta(item.subheading) : null;
                  return (
                    <Box key={itemIdx} sx={{ mb: 1.5, pl: 1, borderLeft: 2, borderColor: "divider" }}>
                      <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
                        <IconButton size="small" onClick={() => removeSectionItem(secIdx, itemIdx)}>
                          <DeleteOutlineIcon fontSize="small" />
                        </IconButton>
                      </Box>
                      <TextField
                        size="small"
                        fullWidth
                        label="Heading"
                        value={item.heading || ""}
                        onChange={(e) => updateSectionItem(secIdx, itemIdx, "heading", e.target.value)}
                        sx={{ mb: 1 }}
                      />
                      {isExperience ? (
                        <>
                          <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
                            <TextField
                              size="small"
                              label="Company"
                              value={meta.company}
                              onChange={(e) =>
                                updateExperienceMetaField(secIdx, itemIdx, "company", e.target.value)
                              }
                              sx={{ flex: 1, minWidth: 140 }}
                            />
                            <TextField
                              size="small"
                              label="Location (optional)"
                              value={meta.location}
                              onChange={(e) =>
                                updateExperienceMetaField(secIdx, itemIdx, "location", e.target.value)
                              }
                              sx={{ flex: 1, minWidth: 140 }}
                            />
                          </Box>
                          <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
                            <TextField
                              size="small"
                              label="Start date"
                              placeholder="Jan 2020"
                              value={meta.startDate}
                              onChange={(e) =>
                                updateExperienceMetaField(secIdx, itemIdx, "startDate", e.target.value)
                              }
                              sx={{ flex: 1, minWidth: 140 }}
                            />
                            <TextField
                              size="small"
                              label="End date or Present"
                              placeholder="Present"
                              value={meta.endDate}
                              onChange={(e) =>
                                updateExperienceMetaField(secIdx, itemIdx, "endDate", e.target.value)
                              }
                              sx={{ flex: 1, minWidth: 140 }}
                            />
                          </Box>
                        </>
                      ) : (
                        <TextField
                          size="small"
                          fullWidth
                          label="Subheading"
                          value={item.subheading || ""}
                          onChange={(e) => updateSectionItem(secIdx, itemIdx, "subheading", e.target.value)}
                          sx={{ mb: 1 }}
                        />
                      )}
                      {isExperience ? (
                        <Box sx={{ mt: 1 }}>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            display="block"
                            sx={{ mb: 0.5 }}
                          >
                            Bullet points
                          </Typography>
                          {bullets.map((bullet, bulletIdx) => (
                            <Box
                              key={bulletIdx}
                              sx={{ display: "flex", alignItems: "flex-start", gap: 0.5, mb: 1 }}
                            >
                              <TextField
                                size="small"
                                fullWidth
                                placeholder={`Bullet ${bulletIdx + 1}`}
                                value={bullet}
                                onChange={(e) =>
                                  updateSectionItemBullet(secIdx, itemIdx, bulletIdx, e.target.value)
                                }
                              />
                              <IconButton
                                size="small"
                                onClick={() => removeSectionItemBullet(secIdx, itemIdx, bulletIdx)}
                                aria-label="Remove bullet"
                              >
                                <DeleteOutlineIcon fontSize="small" />
                              </IconButton>
                            </Box>
                          ))}
                          <Button
                            size="small"
                            startIcon={<AddIcon />}
                            onClick={() => addSectionItemBullet(secIdx, itemIdx)}
                          >
                            Add bullet
                          </Button>
                        </Box>
                      ) : (
                        <TextField
                          size="small"
                          fullWidth
                          multiline
                          rows={2}
                          label="Body"
                          value={item.body || ""}
                          onChange={(e) => updateSectionItem(secIdx, itemIdx, "body", e.target.value)}
                        />
                      )}
                    </Box>
                  );
                })}
                <Button size="small" startIcon={<AddIcon />} onClick={() => addSectionItem(secIdx)}>
                  Add item
                </Button>
              </>
            )}
          </Paper>
        ))}
        <Button startIcon={<AddIcon />} onClick={addSection} sx={{ mb: 3 }}>
          Add section
        </Button>

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
          component="label"
          disabled={uploading}
          startIcon={uploading ? <CircularProgress size={18} /> : <AddIcon />}
        >
          {uploading ? "Uploading…" : "Upload resume"}
          <input type="file" accept=".pdf,application/pdf" hidden onChange={handleUpload} />
        </Button>
      </Box>
      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <CircularProgress />
        </Box>
      ) : resumes.length === 0 ? (
        <Typography color="text.secondary">No resumes yet. Upload a PDF to get started.</Typography>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {resumes.map((r) => (
            <ResumeListItemCard
              key={r.id}
              resume={r}
              onOpen={handleOpen}
              onDelete={(res) => setDeleteTarget(res)}
            />
          ))}
        </Box>
      )}

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
