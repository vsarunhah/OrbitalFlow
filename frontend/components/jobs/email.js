import DOMPurify from "isomorphic-dompurify";

let domPurifyLinkHooksInstalled = false;

export function stripHtmlToPlain(html) {
  if (!html) return "";
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function sanitizeEmailHtml(html) {
  if (!html) return "";
  if (!domPurifyLinkHooksInstalled) {
    domPurifyLinkHooksInstalled = true;
    DOMPurify.addHook("afterSanitizeAttributes", (node) => {
      if (node.tagName === "A") {
        node.setAttribute("target", "_blank");
        node.setAttribute("rel", "noopener noreferrer");
      }
    });
  }
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
}

export function normalizeEmail(input) {
  const s = (input || "").trim().toLowerCase();
  return s.includes("@") ? s : null;
}

/**
 * Parse a single RFC-style From for UI (e.g. "Name <a@b.com>" or "a@b.com").
 * @returns {{ display: string, email: string | null, full: string }}
 */
export function parseFromAddress(raw) {
  const s = (raw || "").trim();
  if (!s) {
    return { display: "(unknown sender)", email: null, full: "" };
  }
  const open = s.lastIndexOf("<");
  const close = s.lastIndexOf(">");
  if (open >= 0 && close > open) {
    const email = s.slice(open + 1, close).trim();
    if (email.includes("@")) {
      const namePart = s.slice(0, open).replace(/^["']|["']$/g, "").trim();
      return {
        display: namePart || email,
        email: email || null,
        full: s,
      };
    }
  }
  return {
    display: s,
    email: s.includes("@") ? s : null,
    full: s,
  };
}

export function buildReplySubject(original) {
  const raw = (original || "").trim();
  if (!raw) return "";
  return /^re:/i.test(raw) ? raw : `Re: ${raw}`;
}
