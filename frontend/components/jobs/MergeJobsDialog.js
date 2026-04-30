import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import RadioGroup from "@mui/material/RadioGroup";
import FormControlLabel from "@mui/material/FormControlLabel";
import Radio from "@mui/material/Radio";
import Button from "@mui/material/Button";

export default function MergeJobsDialog({ jobs, selectedIds, onClose, onConfirm }) {
  const [targetId, setTargetId] = useState(selectedIds[0] || null);
  const selectedJobs = jobs.filter((j) => selectedIds.includes(j.id));

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { bgcolor: "background.paper" } }}>
      <DialogTitle>Merge jobs</DialogTitle>
      <DialogContent>
        <DialogContentText color="text.secondary" sx={{ mb: 2 }}>
          Choose which job to keep. All others will be merged into it and removed.
        </DialogContentText>
        <RadioGroup value={targetId || ""} onChange={(e) => setTargetId(e.target.value)}>
          {selectedJobs.map((j) => (
            <FormControlLabel
              key={j.id}
              value={String(j.id)}
              control={<Radio />}
              label={`${j.company || "Unknown"} – ${j.role || "No role"}`}
              sx={{ display: "flex", m: 0, py: 0.5 }}
            />
          ))}
        </RadioGroup>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => targetId && onConfirm(targetId, selectedIds.filter((id) => id !== targetId))}
        >
          Merge
        </Button>
      </DialogActions>
    </Dialog>
  );
}
