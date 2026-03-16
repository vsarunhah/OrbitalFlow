import { useEffect } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";

/**
 * Reusable confirmation modal. Use instead of window.confirm().
 * @param {boolean} open - Whether the modal is visible
 * @param {string} title - Modal title
 * @param {string} message - Body text
 * @param {string} confirmLabel - Label for confirm button (e.g. "Delete")
 * @param {boolean} danger - If true, confirm button uses danger styling
 * @param {() => void} onConfirm - Called when user confirms
 * @param {() => void} onCancel - Called when user cancels or closes
 */
export default function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  danger = true,
  onConfirm,
  onCancel,
}) {
  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onCancel]);

  const handleConfirm = () => {
    onConfirm();
    onCancel();
  };

  return (
    <Dialog
      open={open}
      onClose={onCancel}
      aria-labelledby="confirm-modal-title"
      aria-describedby="confirm-modal-desc"
      PaperProps={{
        sx: {
          bgcolor: "background.paper",
          border: 1,
          borderColor: "divider",
          maxWidth: 420,
        },
      }}
    >
      <DialogTitle id="confirm-modal-title">{title}</DialogTitle>
      <DialogContent>
        <DialogContentText id="confirm-modal-desc" color="text.secondary">
          {message}
        </DialogContentText>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, pt: 0 }}>
        <Button onClick={onCancel} variant="outlined" color="inherit">
          Cancel
        </Button>
        <Button
          onClick={handleConfirm}
          variant="contained"
          color={danger ? "error" : "primary"}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
