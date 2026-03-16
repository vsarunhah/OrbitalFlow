import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import Chip from "@mui/material/Chip";
import { fetchMergeSuggestions, applyMergeSuggestion } from "../lib/api";

const STAGE_COLORS = {
  SOURCED: "#6b7280",
  APPLIED: "#3b82f6",
  SCREEN: "#8b5cf6",
  INTERVIEW: "#f59e0b",
  TAKEHOME: "#ec4899",
  FINAL: "#14b8a6",
  OFFER: "#22c55e",
  REJECTED: "#ef4444",
  WITHDRAWN: "#9ca3af",
};

function JobPill({ job }) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1,
        bgcolor: "background.default",
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        px: 1.5,
        py: 1,
      }}
    >
      <Typography fontWeight={600} fontSize={13}>
        {job.company || "Unknown"}
      </Typography>
      <Typography fontSize={12} color="text.secondary">
        {job.role || "No role"}
      </Typography>
      <Chip
        label={job.current_stage}
        size="small"
        sx={{
          bgcolor: STAGE_COLORS[job.current_stage] || "#6b7280",
          color: "#fff",
          fontWeight: 600,
          fontSize: 11,
          textTransform: "uppercase",
        }}
      />
    </Box>
  );
}

function MergeCard({ suggestion, onApply, applying }) {
  return (
    <Card variant="outlined" sx={{ mb: 1.25 }}>
      <CardContent>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.25, flexWrap: "wrap" }}>
          <JobPill job={suggestion.source_job} />
          <Typography fontSize={13} color="text.secondary" fontStyle="italic">
            merge into
          </Typography>
          <JobPill job={suggestion.target_job} />
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.25 }}>
          <Typography fontSize={13} color="text.secondary">
            {suggestion.reason}
          </Typography>
          {suggestion.confidence != null && (
            <Typography fontSize={12} color="primary.main" fontWeight={500}>
              {(suggestion.confidence * 100).toFixed(0)}% confidence
            </Typography>
          )}
        </Box>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Button
            variant="contained"
            size="small"
            disabled={applying}
            onClick={() => onApply(suggestion.id)}
          >
            {applying ? "Merging..." : "Apply Merge"}
          </Button>
          <Typography component="time" variant="caption" color="text.secondary">
            {new Date(suggestion.created_at).toLocaleString()}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

export default function MergeSuggestionsPage() {
  const [suggestions, setSuggestions] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [applyingId, setApplyingId] = useState(null);
  const [statusFilter, setStatusFilter] = useState("pending");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMergeSuggestions({ status: statusFilter });
      setSuggestions(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleApply(id) {
    setApplyingId(id);
    try {
      await applyMergeSuggestion(id);
      await load();
    } catch (err) {
      alert(`Merge failed: ${err.message}`);
    } finally {
      setApplyingId(null);
    }
  }

  return (
    <Box sx={{ maxWidth: 900, mx: "auto", p: 3, minHeight: "100vh" }}>
      <Box sx={{ pb: 2, mb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Typography variant="h5" fontWeight={700}>
          Merge Suggestions
        </Typography>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Status</InputLabel>
          <Select
            value={statusFilter}
            label="Status"
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <MenuItem value="pending">Pending</MenuItem>
            <MenuItem value="applied">Applied</MenuItem>
            <MenuItem value="dismissed">Dismissed</MenuItem>
            <MenuItem value="">All</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary">
          {loading ? "Loading..." : `${total} suggestion${total !== 1 ? "s" : ""}`}
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Box sx={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {suggestions.map((s) => (
          <MergeCard
            key={s.id}
            suggestion={s}
            onApply={handleApply}
            applying={applyingId === s.id}
          />
        ))}
        {!loading && suggestions.length === 0 && (
          <Typography color="text.secondary" fontStyle="italic" sx={{ py: 4, textAlign: "center" }}>
            No merge suggestions
          </Typography>
        )}
      </Box>
    </Box>
  );
}
