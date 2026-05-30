import { useMemo, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Autocomplete from "@mui/material/Autocomplete";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";

const NEW_JOB_OPTION = { id: null, label: "Create new job" };

function jobLabel(job) {
  const company = job.company || "Unknown company";
  const role = job.role || "No role";
  return `${company} – ${role}`;
}

export default function ImportEmailDialog({ jobs, onClose, onConfirm, submitting }) {
  const [emailUrl, setEmailUrl] = useState("");
  const [selectedJob, setSelectedJob] = useState(NEW_JOB_OPTION);
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [error, setError] = useState(null);

  const options = useMemo(
    () => [NEW_JOB_OPTION, ...jobs.map((j) => ({ id: j.id, label: jobLabel(j) }))],
    [jobs]
  );

  const creatingNew = !selectedJob?.id;

  const handleSubmit = async () => {
    setError(null);
    const trimmed = emailUrl.trim();
    if (!trimmed) {
      setError("Paste a Gmail link or message id.");
      return;
    }
    try {
      await onConfirm({
        email_url: trimmed,
        job_id: selectedJob?.id ?? null,
        company: creatingNew && company.trim() ? company.trim() : null,
        role: creatingNew && role.trim() ? role.trim() : null,
      });
    } catch (e) {
      setError(e.message || "Import failed");
    }
  };

  return (
    <Dialog
      open
      onClose={submitting ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { bgcolor: "background.paper" } }}
    >
      <DialogTitle>Import email link</DialogTitle>
      <DialogContent>
        <DialogContentText color="text.secondary" sx={{ mb: 2 }}>
          Paste a Gmail link to fetch and attach that thread to a job. If the email is already
          indexed, it will be moved to the job you choose.
        </DialogContentText>
        <TextField
          autoFocus
          fullWidth
          size="small"
          label="Gmail link"
          placeholder="https://mail.google.com/mail/u/0/#all/…"
          value={emailUrl}
          onChange={(e) => setEmailUrl(e.target.value)}
          sx={{ mb: 2 }}
        />
        <Autocomplete
          size="small"
          options={options}
          value={selectedJob}
          onChange={(_, v) => setSelectedJob(v || NEW_JOB_OPTION)}
          getOptionLabel={(o) => o.label}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="Attach to job" />}
          sx={{ mb: creatingNew ? 2 : 0 }}
        />
        {creatingNew ? (
          <Box sx={{ display: "flex", gap: 1.5, mt: 0.5 }}>
            <TextField
              fullWidth
              size="small"
              label="Company (optional)"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
            <TextField
              fullWidth
              size="small"
              label="Role (optional)"
              value={role}
              onChange={(e) => setRole(e.target.value)}
            />
          </Box>
        ) : null}
        {error ? (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleSubmit} disabled={submitting}>
          {submitting ? "Importing…" : "Import"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
