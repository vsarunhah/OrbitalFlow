import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogActions from "@mui/material/DialogActions";
import FormControlLabel from "@mui/material/FormControlLabel";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import CircularProgress from "@mui/material/CircularProgress";
import { fetchRecruiters, fetchRecruiter, deleteRecruiter, mergeRecruiters } from "../lib/api";
import ConfirmModal from "../components/ConfirmModal";

const SEARCH_DEBOUNCE_MS = 350;

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

function getInitial(nameOrEmail) {
  if (!nameOrEmail) return "?";
  const part = String(nameOrEmail).trim().split(/\s+/)[0] || nameOrEmail;
  return (part[0] || "?").toUpperCase();
}

function RecruiterCard({ recruiter, selected, selectedForMerge, mergeMode, onToggleMerge, onClick }) {
  const displayName = recruiter.name || recruiter.email;
  return (
    <Box
      onClick={(e) => e.target?.type !== "checkbox" && onClick()}
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 1.25,
        py: 1.5,
        px: 1.5,
        mb: 0.5,
        borderRadius: 1,
        cursor: "pointer",
        borderLeft: selected ? 3 : 0,
        borderLeftColor: "primary.main",
        outline: selectedForMerge ? "2px solid" : 0,
        outlineColor: "primary.main",
        outlineOffset: 2,
        bgcolor: selected ? "action.selected" : selectedForMerge ? "primary.dark" : "transparent",
        "&:hover": { bgcolor: "action.hover" },
      }}
    >
      {mergeMode && (
        <Checkbox
          size="small"
          checked={!!selectedForMerge}
          onChange={() => onToggleMerge(recruiter.id)}
          onClick={(e) => e.stopPropagation()}
        />
      )}
      <Avatar
          sx={{
            width: 36,
            height: 36,
            bgcolor: selectedForMerge ? "primary.main" : "action.hover",
            color: selectedForMerge ? "primary.contrastText" : "text.secondary",
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          {getInitial(displayName)}
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }} onClick={() => onClick()}>
          <Typography fontWeight={600} fontSize={14}>
            {displayName}
          </Typography>
          {recruiter.name && (
            <Typography variant="body2" color="text.secondary">
              {recruiter.email}
            </Typography>
          )}
          {recruiter.primary_agency && (
            <Typography variant="caption" color="text.secondary" display="block">
              Agency recruiter: {recruiter.primary_agency}
            </Typography>
          )}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 1, mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ flex: 1 }}>
              {recruiter.affiliations?.length > 0
                ? recruiter.affiliations.map((a) => a.company).filter(Boolean).join(", ") || "No company"
                : "\u00A0"}
            </Typography>
            <Typography variant="caption" fontWeight={500} color="primary.main">
              {recruiter.job_count} job{recruiter.job_count !== 1 ? "s" : ""}
            </Typography>
          </Box>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mt: 0.75 }}>
            {recruiter.message_count > 0 && (
              <Chip
                size="small"
                label={`${recruiter.message_count} email${recruiter.message_count !== 1 ? "s" : ""}`}
                sx={{ fontSize: 11, height: 22 }}
              />
            )}
            {recruiter.company_count > 0 && (
              <Chip
                size="small"
                label={`${recruiter.company_count} ${recruiter.company_count === 1 ? "company" : "companies"}`}
                sx={{ fontSize: 11, height: 22 }}
              />
            )}
          </Box>
        </Box>
    </Box>
  );
}

function SearchBar({ value, onChange, onFlushSearch }) {
  return (
    <Box sx={{ display: "flex", gap: 1, p: 1.5 }}>
      <TextField
        size="small"
        placeholder="Search by name or email..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onFlushSearch()}
        sx={{ flex: 1 }}
      />
      <Button variant="contained" onClick={onFlushSearch}>
        Search
      </Button>
    </Box>
  );
}

function MergeRecruitersModal({ recruiters, selectedIds, onClose, onConfirm }) {
  const [targetId, setTargetId] = useState(selectedIds[0] || null);
  const selected = recruiters.filter((r) => selectedIds.includes(r.id));

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth PaperProps={{ sx: { bgcolor: "background.paper" } }}>
      <DialogTitle>Merge recruiters</DialogTitle>
      <DialogContent>
        <DialogContentText color="text.secondary" sx={{ mb: 2 }}>
          Choose which recruiter to keep. All others will be merged into it and removed.
        </DialogContentText>
        <RadioGroup value={targetId || ""} onChange={(e) => setTargetId(e.target.value)}>
          {selected.map((r) => (
            <FormControlLabel
              key={r.id}
              value={String(r.id)}
              control={<Radio />}
              label={r.name || r.email}
              sx={{ display: "flex", m: 0, py: 0.5 }}
            />
          ))}
        </RadioGroup>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => targetId && onConfirm(Number(targetId), selectedIds.filter((id) => id !== Number(targetId)))}
        >
          Merge
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function RecruiterDetail({ detail, onRequestDelete }) {
  if (!detail) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "text.secondary" }}>
        Select a recruiter to view details
      </Box>
    );
  }

  return (
    <Box>
      <Box sx={{ pb: 2, mb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1.5 }}>
          <Typography variant="h5" fontWeight={700}>
            {detail.name || detail.email}
          </Typography>
          <Button variant="outlined" color="error" size="small" onClick={() => onRequestDelete(detail)}>
            Delete
          </Button>
        </Box>
        {detail.name && (
          <Typography variant="body2" color="text.secondary">
            {detail.email}
          </Typography>
        )}
        {detail.phone && (
          <Typography variant="body2" color="text.secondary">
            {detail.phone}
          </Typography>
        )}
        <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
          <Typography variant="body2" fontWeight={500} color="text.secondary" gutterBottom>
            Relationship
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {detail.primary_agency && (
              <Chip
                label={detail.primary_agency}
                size="small"
                sx={{ bgcolor: "primary.dark", color: "text.primary", borderColor: "primary.main" }}
              />
            )}
            {detail.message_count > 0 && (
              <Chip size="small" label={`${detail.message_count} email${detail.message_count !== 1 ? "s" : ""}`} />
            )}
            {detail.company_count > 0 && (
              <Chip
                size="small"
                label={`${detail.company_count} ${detail.company_count === 1 ? "company" : "companies"}`}
              />
            )}
          </Box>
        </Box>
      </Box>

      {detail.affiliations?.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="overline" color="text.secondary" display="block" gutterBottom>
            Affiliations
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
            {detail.affiliations.map((a) => (
              <Card key={a.id} variant="outlined" sx={{ p: 1.5 }}>
                <Typography fontWeight={600} fontSize={13}>
                  {a.company || "Unknown"}
                </Typography>
                {a.title && (
                  <Typography variant="caption" color="text.secondary">
                    {a.title}
                  </Typography>
                )}
              </Card>
            ))}
          </Box>
        </Box>
      )}

      {detail.companies?.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="overline" color="text.secondary" display="block" gutterBottom>
            Companies
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {detail.companies.join(", ")}
          </Typography>
        </Box>
      )}

      <Box>
        <Typography variant="overline" color="text.secondary" display="block" gutterBottom>
          Associated Jobs
        </Typography>
        {detail.jobs?.length === 0 ? (
          <Typography color="text.secondary" fontStyle="italic">
            No associated jobs
          </Typography>
        ) : (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
            {detail.jobs?.map((j) => (
              <Link
                key={j.job_id}
                href={`/jobs?job=${j.job_id}`}
                style={{ textDecoration: "none", color: "inherit" }}
              >
                <Card
                  variant="outlined"
                  sx={{
                    py: 1.25,
                    px: 1.5,
                    display: "flex",
                    alignItems: "center",
                    gap: 1.5,
                    "&:hover": { borderColor: "primary.main", bgcolor: "action.hover" },
                  }}
                >
                  <Typography fontWeight={600} fontSize={13} sx={{ minWidth: 120 }}>
                    {j.company || "Unknown"}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
                    {j.role || "No role"}
                  </Typography>
                  <Chip
                    size="small"
                    label={j.current_stage}
                    sx={{
                      bgcolor: STAGE_COLORS[j.current_stage] || "#6b7280",
                      color: "#fff",
                      fontWeight: 600,
                      fontSize: 10,
                    }}
                  />
                  <Typography variant="caption" color="text.secondary" textTransform="uppercase">
                    {j.contact_role}
                  </Typography>
                </Card>
              </Link>
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}

export default function RecruitersPage() {
  const [recruiters, setRecruiters] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const searchDebounceRef = useRef(null);
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelectedIds, setMergeSelectedIds] = useState(new Set());
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [mergeSubmitting, setMergeSubmitting] = useState(false);
  const [deleteConfirmRecruiter, setDeleteConfirmRecruiter] = useState(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const q = (debouncedSearch || "").trim() || undefined;
      const data = await fetchRecruiters({ query: q });
      setRecruiters(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch]);

  useEffect(() => {
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    searchDebounceRef.current = setTimeout(() => {
      searchDebounceRef.current = null;
      setDebouncedSearch((searchQuery || "").trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, [searchQuery]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const flushRecruiterSearch = useCallback(() => {
    if (searchDebounceRef.current) {
      clearTimeout(searchDebounceRef.current);
      searchDebounceRef.current = null;
    }
    setDebouncedSearch((searchQuery || "").trim());
  }, [searchQuery]);

  async function handleDeleteRecruiter(recruiterId) {
    try {
      await deleteRecruiter(recruiterId);
      setSelectedId(null);
      setDetail(null);
      await loadList();
    } catch (err) {
      alert(`Failed to delete recruiter: ${err.message}`);
    }
  }

  function toggleMergeSelection(recruiterId) {
    setMergeSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(recruiterId)) next.delete(recruiterId);
      else next.add(recruiterId);
      return next;
    });
  }

  async function handleMergeConfirm(targetId, sourceIds) {
    if (sourceIds.length === 0) return;
    setMergeSubmitting(true);
    try {
      await mergeRecruiters(targetId, sourceIds);
      setShowMergeModal(false);
      setMergeSelectedIds(new Set());
      setSelectedId(targetId);
      setDetail(null);
      await loadList();
      const data = await fetchRecruiter(targetId);
      setDetail(data);
    } catch (err) {
      alert(`Merge failed: ${err.message}`);
    } finally {
      setMergeSubmitting(false);
    }
  }

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    fetchRecruiter(selectedId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  return (
    <Box sx={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      <Box
        sx={{
          width: 380,
          minWidth: 300,
          borderRight: 1,
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          bgcolor: "background.paper",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1.5, p: 2, flexWrap: "wrap" }}>
          <Typography variant="h6" fontWeight={600}>
            Recruiters
          </Typography>
          {!mergeMode ? (
            <Button variant="outlined" size="small" onClick={() => setMergeMode(true)}>
              Merge
            </Button>
          ) : (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {mergeSelectedIds.size >= 2 ? `${mergeSelectedIds.size} selected` : "Select 2+ to merge"}
              </Typography>
              {mergeSelectedIds.size >= 2 && (
                <Button variant="contained" size="small" onClick={() => setShowMergeModal(true)}>
                  Merge
                </Button>
              )}
              <Button size="small" color="inherit" onClick={() => { setMergeMode(false); setMergeSelectedIds(new Set()); }}>
                Done
              </Button>
            </Box>
          )}
        </Box>
        <SearchBar value={searchQuery} onChange={setSearchQuery} onFlushSearch={flushRecruiterSearch} />
        <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 1 }}>
          {loading ? "Loading..." : `${total} recruiter${total !== 1 ? "s" : ""}`}
        </Typography>
        {error && (
          <Alert severity="error" sx={{ mx: 2, mb: 1 }}>
            {error}
          </Alert>
        )}
        <Box sx={{ flex: 1, overflowY: "auto", px: 1, pb: 1 }}>
          {recruiters.map((r) => (
            <RecruiterCard
              key={r.id}
              recruiter={r}
              selected={r.id === selectedId}
              selectedForMerge={mergeSelectedIds.has(r.id)}
              mergeMode={mergeMode}
              onToggleMerge={toggleMergeSelection}
              onClick={() => setSelectedId(r.id)}
            />
          ))}
          {!loading && recruiters.length === 0 && (
            <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              No recruiters found
            </Typography>
          )}
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", p: 3, bgcolor: "background.default" }}>
        {detailLoading && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", gap: 1 }}>
            <CircularProgress size={24} />
            <Typography color="text.secondary">Loading details...</Typography>
          </Box>
        )}
        {!detailLoading && (
          <RecruiterDetail detail={detail} onRequestDelete={setDeleteConfirmRecruiter} />
        )}
      </Box>

      {showMergeModal && (
        <MergeRecruitersModal
          recruiters={recruiters}
          selectedIds={Array.from(mergeSelectedIds)}
          onClose={() => !mergeSubmitting && setShowMergeModal(false)}
          onConfirm={handleMergeConfirm}
        />
      )}

      <ConfirmModal
        open={!!deleteConfirmRecruiter}
        title="Delete recruiter?"
        message={
          deleteConfirmRecruiter
            ? `Delete recruiter "${deleteConfirmRecruiter.name || deleteConfirmRecruiter.email}"? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        danger={true}
        onConfirm={() => {
          if (deleteConfirmRecruiter) handleDeleteRecruiter(deleteConfirmRecruiter.id);
          setDeleteConfirmRecruiter(null);
        }}
        onCancel={() => setDeleteConfirmRecruiter(null)}
      />
    </Box>
  );
}
