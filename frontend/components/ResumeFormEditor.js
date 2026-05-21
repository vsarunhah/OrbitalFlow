import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Paper from "@mui/material/Paper";
import IconButton from "@mui/material/IconButton";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import { generateId } from "../lib/resumeStructured";

/**
 * Form-based resume editor: contact + ordered sections (text or list items).
 * Parent owns state; we emit immutable updates via onChange.
 */
export default function ResumeFormEditor({ value, onChange }) {
  const editingParsed = value;
  const contact = editingParsed.contact || {};
  const sections = editingParsed.sections || [];

  const patch = (next) => onChange(next);

  const updateContact = (field, v) => {
    patch({
      ...editingParsed,
      contact: { ...(editingParsed.contact || {}), [field]: v },
    });
  };

  const updateSection = (sectionIndex, updates) => {
    const nextSections = [...(editingParsed.sections || [])];
    nextSections[sectionIndex] = { ...nextSections[sectionIndex], ...updates };
    patch({ ...editingParsed, sections: nextSections });
  };

  const updateSectionItem = (sectionIndex, itemIndex, field, v) => {
    const nextSections = [...(editingParsed.sections || [])];
    const sec = { ...nextSections[sectionIndex], items: [...(nextSections[sectionIndex].items || [])] };
    sec.items[itemIndex] = { ...sec.items[itemIndex], [field]: v };
    nextSections[sectionIndex] = sec;
    patch({ ...editingParsed, sections: nextSections });
  };

  const moveSection = (fromIndex, direction) => {
    const toIndex = direction === "up" ? fromIndex - 1 : fromIndex + 1;
    if (toIndex < 0 || toIndex >= sections.length) return;
    const nextSections = [...sections];
    [nextSections[fromIndex], nextSections[toIndex]] = [nextSections[toIndex], nextSections[fromIndex]];
    nextSections.forEach((s, i) => {
      s.order = i;
    });
    patch({ ...editingParsed, sections: nextSections });
  };

  const addSection = () => {
    patch({
      ...editingParsed,
      sections: [
        ...sections,
        {
          id: generateId(),
          name: "New Section",
          order: sections.length,
          content_type: "text",
          text: "",
          items: [],
        },
      ],
    });
  };

  const removeSection = (index) => {
    const nextSections = sections.filter((_, i) => i !== index);
    nextSections.forEach((s, i) => {
      s.order = i;
    });
    patch({ ...editingParsed, sections: nextSections });
  };

  const addSectionItem = (sectionIndex) => {
    const nextSections = [...sections];
    const sec = {
      ...nextSections[sectionIndex],
      items: [...(nextSections[sectionIndex].items || []), { heading: "", subheading: "", body: "" }],
    };
    nextSections[sectionIndex] = sec;
    patch({ ...editingParsed, sections: nextSections });
  };

  const removeSectionItem = (sectionIndex, itemIndex) => {
    const nextSections = [...sections];
    const sec = {
      ...nextSections[sectionIndex],
      items: (nextSections[sectionIndex].items || []).filter((_, i) => i !== itemIndex),
    };
    nextSections[sectionIndex] = sec;
    patch({ ...editingParsed, sections: nextSections });
  };

  const getBullets = (body) => {
    if (body == null || body === "") return [""];
    const lines = String(body).split(/\n/).map((l) => l.trim());
    return lines.length ? lines : [""];
  };

  const updateSectionItemBullet = (sectionIndex, itemIndex, bulletIndex, v) => {
    const nextSections = [...sections];
    const sec = nextSections[sectionIndex];
    const items = [...(sec.items || [])];
    const item = { ...items[itemIndex] };
    const bullets = getBullets(item.body);
    const next = [...bullets];
    if (bulletIndex >= next.length) next.length = bulletIndex + 1;
    next[bulletIndex] = v;
    item.body = next.join("\n");
    items[itemIndex] = item;
    nextSections[sectionIndex] = { ...sec, items };
    patch({ ...editingParsed, sections: nextSections });
  };

  const addSectionItemBullet = (sectionIndex, itemIndex) => {
    const nextSections = [...sections];
    const sec = nextSections[sectionIndex];
    const items = [...(sec.items || [])];
    const item = { ...items[itemIndex] };
    const bullets = getBullets(item.body);
    item.body = [...bullets, ""].join("\n");
    items[itemIndex] = item;
    nextSections[sectionIndex] = { ...sec, items };
    patch({ ...editingParsed, sections: nextSections });
  };

  const removeSectionItemBullet = (sectionIndex, itemIndex, bulletIndex) => {
    const nextSections = [...sections];
    const sec = nextSections[sectionIndex];
    const items = [...(sec.items || [])];
    const item = { ...items[itemIndex] };
    const bullets = getBullets(item.body).filter((_, i) => i !== bulletIndex);
    item.body = bullets.join("\n");
    items[itemIndex] = item;
    nextSections[sectionIndex] = { ...sec, items };
    patch({ ...editingParsed, sections: nextSections });
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
      startDate || endDate ? [startDate, endDate || "Present"].filter(Boolean).join(" - ") : "";
    if (datePart) parts.push(datePart);
    return parts.join(" | ");
  };

  const updateExperienceMetaField = (sectionIndex, itemIndex, field, v) => {
    const nextSections = [...sections];
    const sec = nextSections[sectionIndex];
    const items = [...(sec.items || [])];
    const item = { ...items[itemIndex] };
    const meta = parseExperienceMeta(item.subheading);
    const nextMeta = { ...meta, [field]: v };
    item.subheading = formatExperienceMeta(nextMeta);
    items[itemIndex] = item;
    nextSections[sectionIndex] = { ...sec, items };
    patch({ ...editingParsed, sections: nextSections });
  };

  const setSectionContentType = (sectionIndex, content_type) => {
    const nextSections = [...sections];
    nextSections[sectionIndex] = {
      ...nextSections[sectionIndex],
      content_type,
      text: content_type === "text" ? (nextSections[sectionIndex].text || "") : "",
      items:
        content_type === "list"
          ? nextSections[sectionIndex].items?.length
            ? nextSections[sectionIndex].items
            : [{ heading: "", subheading: "", body: "" }]
          : [],
    };
    patch({ ...editingParsed, sections: nextSections });
  };

  return (
    <Box>
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
        <TextField
          size="small"
          label="LinkedIn"
          placeholder="Profile URL or linkedin.com/in/you"
          value={contact.linkedin ?? ""}
          onChange={(e) => updateContact("linkedin", e.target.value)}
        />
        <TextField
          size="small"
          label="Additional websites"
          placeholder="One URL per line (portfolio, GitHub, etc.)"
          value={contact.websites ?? ""}
          onChange={(e) => updateContact("websites", e.target.value)}
          multiline
          minRows={2}
        />
      </Box>

      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
        Sections (use arrows to reorder)
      </Typography>
      {sections.map((sec, secIdx) => (
        <Paper key={sec.id || secIdx} variant="outlined" sx={{ p: 2, mb: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", mb: 1.5 }}>
            <IconButton size="small" onClick={() => moveSection(secIdx, "up")} disabled={secIdx === 0} aria-label="Move up">
              <ArrowUpwardIcon fontSize="small" />
            </IconButton>
            <IconButton
              size="small"
              onClick={() => moveSection(secIdx, "down")}
              disabled={secIdx === sections.length - 1}
              aria-label="Move down"
            >
              <ArrowDownwardIcon fontSize="small" />
            </IconButton>
            <TextField
              size="small"
              label="Section name"
              value={sec.name}
              onChange={(e) => updateSection(secIdx, { name: e.target.value })}
              sx={{ width: 200 }}
            />
            <Button size="small" variant={sec.content_type === "text" ? "outlined" : "text"} onClick={() => setSectionContentType(secIdx, "text")}>
              Text
            </Button>
            <Button size="small" variant={sec.content_type === "list" ? "outlined" : "text"} onClick={() => setSectionContentType(secIdx, "list")}>
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
                            onChange={(e) => updateExperienceMetaField(secIdx, itemIdx, "company", e.target.value)}
                            sx={{ flex: 1, minWidth: 140 }}
                          />
                          <TextField
                            size="small"
                            label="Location (optional)"
                            value={meta.location}
                            onChange={(e) => updateExperienceMetaField(secIdx, itemIdx, "location", e.target.value)}
                            sx={{ flex: 1, minWidth: 140 }}
                          />
                        </Box>
                        <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
                          <TextField
                            size="small"
                            label="Start date"
                            placeholder="Jan 2020"
                            value={meta.startDate}
                            onChange={(e) => updateExperienceMetaField(secIdx, itemIdx, "startDate", e.target.value)}
                            sx={{ flex: 1, minWidth: 140 }}
                          />
                          <TextField
                            size="small"
                            label="End date or Present"
                            placeholder="Present"
                            value={meta.endDate}
                            onChange={(e) => updateExperienceMetaField(secIdx, itemIdx, "endDate", e.target.value)}
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
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                          Bullet points
                        </Typography>
                        {bullets.map((bullet, bulletIdx) => (
                          <Box key={bulletIdx} sx={{ display: "flex", alignItems: "flex-start", gap: 0.5, mb: 1 }}>
                            <TextField
                              size="small"
                              fullWidth
                              placeholder={`Bullet ${bulletIdx + 1}`}
                              value={bullet}
                              onChange={(e) => updateSectionItemBullet(secIdx, itemIdx, bulletIdx, e.target.value)}
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
                        <Button size="small" startIcon={<AddIcon />} onClick={() => addSectionItemBullet(secIdx, itemIdx)}>
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
      <Button startIcon={<AddIcon />} onClick={addSection} sx={{ mb: 1 }}>
        Add section
      </Button>
    </Box>
  );
}
