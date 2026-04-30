import { useEffect } from "react";

function isTypingTarget(el) {
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return false;
}

/**
 * Global keyboard shortcuts for the Jobs page.
 * Handlers are skipped when the user is typing in a field.
 */
export default function useKeyboardShortcuts({
  onFocusSearch,
  onNext,
  onPrev,
  onReply,
  onToggleRead,
  onDismissNeedsReply,
  onShowShortcuts,
  enabled = true,
}) {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e) => {
      // Skip when typing; allow `/` to focus search from anywhere.
      const typing = isTypingTarget(e.target);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        onFocusSearch?.();
        return;
      }
      if (typing) return;
      // Ignore modifier combos so they don't clash with native shortcuts.
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      switch (e.key) {
        case "j":
          e.preventDefault();
          onNext?.();
          break;
        case "k":
          e.preventDefault();
          onPrev?.();
          break;
        case "r":
          e.preventDefault();
          onReply?.();
          break;
        case "e":
          e.preventDefault();
          onToggleRead?.();
          break;
        case "d":
          e.preventDefault();
          onDismissNeedsReply?.();
          break;
        case "?":
          e.preventDefault();
          onShowShortcuts?.();
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    enabled,
    onFocusSearch,
    onNext,
    onPrev,
    onReply,
    onToggleRead,
    onDismissNeedsReply,
    onShowShortcuts,
  ]);
}
