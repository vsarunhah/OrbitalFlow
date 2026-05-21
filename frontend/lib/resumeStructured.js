/** Structured resume form ↔ Markdown storage helpers (client). */

export const DEFAULT_MARKDOWN = `# Your Name

you@email.com · (555) 555-5555
[LinkedIn](https://linkedin.com/in/your-profile)

https://your-portfolio.com

## Summary

One or two lines about your focus and strengths.

## Experience

### Senior Engineer — Acme Inc.
*Jan 2020 – Present*

- Shipped features that improved reliability by 40%.
- Led migrations with clear runbooks and rollbacks.

## Education

**B.S. Computer Science** — State University *(2016)*

## Skills

Python · SQL · System design · Communication
`;

export function generateId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function defaultParsed() {
  return {
    contact: { name: "", email: "", phone: "", linkedin: "", websites: "" },
    sections: [],
  };
}

export function ensureParsedShape(parsed) {
  if (!parsed || typeof parsed !== "object") return defaultParsed();
  if (parsed.sections && Array.isArray(parsed.sections)) {
    const contact =
      parsed.contact && typeof parsed.contact === "object"
        ? {
            name: parsed.contact.name ?? "",
            email: parsed.contact.email ?? "",
            phone: parsed.contact.phone ?? "",
            linkedin: parsed.contact.linkedin ?? "",
            websites: parsed.contact.websites ?? "",
          }
        : {
            name: parsed.name ?? "",
            email: parsed.email ?? "",
            phone: parsed.phone ?? "",
            linkedin: "",
            websites: "",
          };
    const sections = parsed.sections.map((s, i) => ({
      id: s.id || generateId(),
      name: s.name ?? "Section",
      order: typeof s.order === "number" ? s.order : i,
      content_type: s.content_type === "list" ? "list" : "text",
      text: s.content_type === "text" ? (s.text ?? "") : "",
      items:
        s.content_type === "list" && Array.isArray(s.items)
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
    linkedin: parsed.linkedin ?? "",
    websites: parsed.websites ?? "",
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
      text: "",
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
      text: "",
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
      text: "",
      items: (Array.isArray(sk) ? sk : [sk]).map((s) => ({
        heading: "",
        subheading: "",
        body: String(s),
      })),
    });
  }
  sections.forEach((s, i) => {
    s.order = i;
  });
  return { contact, sections };
}

function parseSectionBody(name, bodyLines, order) {
  while (bodyLines.length && !bodyLines[bodyLines.length - 1].trim()) bodyLines.pop();
  const joined = bodyLines.join("\n").trim();
  if (!joined) {
    return {
      id: generateId(),
      name,
      order,
      content_type: "text",
      text: "",
      items: [],
    };
  }
  const hasH3 = bodyLines.some((l) => /^###\s+/.test(l.trim()));
  const bulletRx = /^\s*[-*•]\s+/;
  const hasBullets = bodyLines.some((l) => bulletRx.test(l));
  if (!hasH3 && !hasBullets) {
    return {
      id: generateId(),
      name,
      order,
      content_type: "text",
      text: joined,
      items: [],
    };
  }
  const items = [];
  if (!hasH3 && hasBullets) {
    for (const line of bodyLines) {
      if (bulletRx.test(line)) {
        items.push({
          heading: "",
          subheading: "",
          body: line.replace(bulletRx, "").trim(),
        });
      }
    }
    return {
      id: generateId(),
      name,
      order,
      content_type: "list",
      text: "",
      items,
    };
  }
  let curItem = null;
  for (const line of bodyLines) {
    const t = line.trim();
    if (/^###\s+/.test(t)) {
      if (curItem) items.push(curItem);
      const rest = t.replace(/^###\s+/, "");
      const emOnly = rest.match(/^\*(.+)\*$/);
      if (emOnly) {
        curItem = { heading: "", subheading: emOnly[1], body: "" };
      } else if (rest.includes(" — ")) {
        const idx = rest.indexOf(" — ");
        curItem = {
          heading: rest.slice(0, idx).trim(),
          subheading: rest.slice(idx + 3).trim(),
          body: "",
        };
      } else {
        curItem = { heading: rest, subheading: "", body: "" };
      }
    } else if (/^\*(.+)\*$/.test(t) && curItem && !curItem.subheading) {
      curItem.subheading = t.slice(1, -1);
    } else if (bulletRx.test(line) && curItem) {
      const bullet = line.replace(bulletRx, "").trim();
      curItem.body = curItem.body ? `${curItem.body}\n${bullet}` : bullet;
    } else if (t && curItem) {
      curItem.body = curItem.body ? `${curItem.body}\n${t}` : t;
    }
  }
  if (curItem) items.push(curItem);
  return {
    id: generateId(),
    name,
    order,
    content_type: "list",
    text: "",
    items,
  };
}

/** Best-effort reverse of structuredToMarkdown for round-trips and legacy Markdown-only saves. */
export function markdownToForm(md) {
  const text = (md || "").replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  const contact = { name: "", email: "", phone: "", linkedin: "", websites: "" };
  let i = 0;
  while (i < lines.length && !lines[i].trim()) i++;
  if (i < lines.length && /^#\s+/.test(lines[i])) {
    contact.name = lines[i].replace(/^#\s+/, "").trim();
    i++;
  }
  while (i < lines.length && !lines[i].trim()) i++;
  if (i < lines.length && !/^##\s+/.test(lines[i])) {
    const parts = lines[i]
      .split("·")
      .map((s) => s.trim())
      .filter(Boolean);
    contact.email = parts[0] || "";
    contact.phone = parts[1] || "";
    i++;
  }
  const extraSites = [];
  while (i < lines.length && !/^##\s+/.test(lines[i])) {
    const raw = lines[i].trim();
    i++;
    if (!raw) continue;
    const mdLinkedIn = raw.match(/^\[LinkedIn\]\(([^)]+)\)$/i);
    if (mdLinkedIn) {
      contact.linkedin = mdLinkedIn[1].trim();
    } else if (/linkedin\.com/i.test(raw) && /^https?:\/\//i.test(raw)) {
      contact.linkedin = raw;
    } else if (/^https?:\/\//i.test(raw) || /^www\./i.test(raw)) {
      extraSites.push(raw);
    }
  }
  contact.websites = extraSites.join("\n");
  const sections = [];
  while (i < lines.length) {
    while (i < lines.length && !lines[i].trim()) i++;
    if (i >= lines.length) break;
    const hm = lines[i].match(/^##\s+(.+)$/);
    if (!hm) {
      i++;
      continue;
    }
    const secName = hm[1].trim();
    i++;
    const bodyLines = [];
    while (i < lines.length && !/^##\s+/.test(lines[i])) {
      bodyLines.push(lines[i]);
      i++;
    }
    sections.push(parseSectionBody(secName, bodyLines, sections.length));
  }
  return ensureParsedShape({ contact, sections });
}

export function structuredToMarkdown(parsed) {
  const { contact, sections } = ensureParsedShape(parsed);
  const lines = [];
  if (contact?.name) lines.push(`# ${contact.name}`, "");
  const bits = [contact?.email, contact?.phone].filter(Boolean);
  if (bits.length) lines.push(`${bits.join(" · ")}`, "");
  const li = (contact?.linkedin || "").trim();
  if (li) {
    const url = /^https?:\/\//i.test(li) ? li : `https://${li.replace(/^\/+/, "")}`;
    lines.push(`[LinkedIn](${url})`, "");
  }
  const sites = (contact?.websites || "")
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  for (const u of sites) {
    lines.push(u, "");
  }
  for (const sec of sections || []) {
    if (!sec.name) continue;
    lines.push(`## ${sec.name}`, "");
    if (sec.content_type === "text") {
      if (sec.text) lines.push(sec.text, "");
    } else {
      for (const it of sec.items || []) {
        const sub = [it.heading, it.subheading].filter(Boolean).join(" — ");
        if (sub) lines.push(`### ${sub}`, "");
        if (it.body) {
          for (const rawLine of String(it.body).split("\n")) {
            const line = rawLine.trim();
            if (!line) continue;
            const cleaned = line.replace(/^[-*•]\s+/, "");
            lines.push(`- ${cleaned}`);
          }
          lines.push("");
        }
      }
    }
  }
  return lines.join("\n").trim() || DEFAULT_MARKDOWN;
}

export function getDefaultForm() {
  return markdownToForm(DEFAULT_MARKDOWN);
}

export function formFromApi(parsedJson) {
  if (!parsedJson || typeof parsedJson !== "object") return defaultParsed();
  if (parsedJson.source_form && Array.isArray(parsedJson.source_form.sections)) {
    return ensureParsedShape(parsedJson.source_form);
  }
  if (parsedJson.format === "markdown" && typeof parsedJson.markdown === "string") {
    return ensureParsedShape(markdownToForm(parsedJson.markdown));
  }
  return ensureParsedShape(parsedJson);
}

export function markdownPayloadFromApi(parsedJson) {
  return structuredToMarkdown(formFromApi(parsedJson));
}

export function toStoredJson(form) {
  const shape = ensureParsedShape(form);
  return {
    format: "markdown",
    markdown: structuredToMarkdown(shape),
    source_form: shape,
  };
}
