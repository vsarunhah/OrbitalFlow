import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import { displayCompanyForGroup } from "../../lib/jobMergeSuggest";

export default function SuggestMergesDialog({ groups, onClose, onSelectGroup }) {
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { bgcolor: "background.paper" } }}>
      <DialogTitle>Suggest merges</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Jobs are grouped when the company name matches ignoring capitalization and spaces (e.g. &quot;Acme Inc&quot;
          and &quot;acme inc&quot;).
        </Typography>
        {groups.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No duplicate companies in the jobs loaded here (up to 200). Try clearing search or stage filters and
            refresh.
          </Typography>
        ) : (
          <List dense disablePadding sx={{ width: "100%" }}>
            {groups.map(({ key, jobs }) => {
              const title = displayCompanyForGroup(jobs);
              const subtitle = jobs
                .map((j) => j.role || "No role")
                .slice(0, 4)
                .join(" · ");
              const more = jobs.length > 4 ? ` · +${jobs.length - 4} more` : "";
              return (
                <ListItem
                  key={key}
                  sx={{
                    flexDirection: "column",
                    alignItems: "stretch",
                    gap: 1,
                    py: 1.5,
                    borderBottom: 1,
                    borderColor: "divider",
                  }}
                >
                  <ListItemText
                    primary={title}
                    secondary={
                      <>
                        {subtitle}
                        {more}
                      </>
                    }
                    primaryTypographyProps={{ fontWeight: 600 }}
                    secondaryTypographyProps={{ component: "span", variant: "caption", display: "block", sx: { mt: 0.5 } }}
                  />
                  <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
                    <Button size="small" variant="contained" onClick={() => onSelectGroup(jobs)}>
                      Select {jobs.length} jobs to merge
                    </Button>
                  </Box>
                </ListItem>
              );
            })}
          </List>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
