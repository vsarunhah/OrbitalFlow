import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

const SHORTCUTS = [
  { keys: ["/"], desc: "Focus search" },
  { keys: ["j"], desc: "Next job" },
  { keys: ["k"], desc: "Previous job" },
  { keys: ["r"], desc: "Reply to selected job" },
  { keys: ["e"], desc: "Toggle read / unread" },
  { keys: ["d"], desc: "No reply needed (dismiss nudge when shown)" },
  { keys: ["?"], desc: "Show this help" },
  { keys: ["Esc"], desc: "Close reply or dialog" },
];

function Kbd({ children }) {
  return (
    <Box
      component="kbd"
      sx={{
        display: "inline-block",
        minWidth: 22,
        textAlign: "center",
        px: 0.75,
        py: 0.25,
        borderRadius: 1,
        border: 1,
        borderColor: "divider",
        bgcolor: "action.hover",
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace',
        fontSize: 12,
        fontWeight: 600,
        color: "text.primary",
      }}
    >
      {children}
    </Box>
  );
}

export default function ShortcutsDialog({ open, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth PaperProps={{ sx: { bgcolor: "background.paper" } }}>
      <DialogTitle sx={{ pb: 1 }}>Keyboard shortcuts</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          {SHORTCUTS.map(({ keys, desc }) => (
            <Box key={desc} sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
              <Box sx={{ display: "flex", gap: 0.5, minWidth: 90 }}>
                {keys.map((k) => (
                  <Kbd key={k}>{k}</Kbd>
                ))}
              </Box>
              <Typography variant="body2" color="text.secondary">
                {desc}
              </Typography>
            </Box>
          ))}
        </Box>
      </DialogContent>
    </Dialog>
  );
}
