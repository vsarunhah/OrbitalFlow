import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import {
  fetchJobs,
  fetchTimeline,
  changeStage,
  updateJob,
  deleteJob,
  mergeJobs,
  getDraftForJob,
  setJobTimelineReadState,
  generateFollowUpSuggestion,
  dismissNeedsReply,
} from "../lib/api";
import ConfirmModal from "../components/ConfirmModal";
import PipelineStrip from "../components/jobs/PipelineStrip";
import JobListToolbar from "../components/jobs/JobListToolbar";
import JobCard from "../components/jobs/JobCard";
import JobHeader from "../components/jobs/JobHeader";
import Thread from "../components/jobs/Thread";
import ReplyDrawer from "../components/jobs/ReplyDrawer";
import MergeJobsDialog from "../components/jobs/MergeJobsDialog";
import ShortcutsDialog from "../components/jobs/ShortcutsDialog";
import useKeyboardShortcuts from "../components/jobs/useKeyboardShortcuts";
import {
  normalizeStageFilter,
  parseStagesFromQuery,
  firstQueryValue,
  buildJobsListQuery,
} from "../components/jobs/stages";

/** Server caps at 200; we fetch the top chunk so "all" is close to all. */
const JOB_LIST_LIMIT = 200;
const SEARCH_DEBOUNCE_MS = 350;
const VALID_VIEWS = new Set(["needs", "awaiting", "all"]);

function scrollJobListItemIntoView(jobId) {
  if (typeof document === "undefined" || !jobId) return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-job-id="${jobId}"]`);
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  });
}

function applyViewFilter(items, view) {
  if (!Array.isArray(items)) return [];
  if (view === "needs") {
    return items.filter(
      (j) => (j.unread_incoming_count ?? 0) > 0 || j.next_action != null
    );
  }
  if (view === "awaiting") {
    return items.filter(
      (j) => (j.unread_incoming_count ?? 0) === 0 && j.next_action == null
    );
  }
  return items;
}

export default function JobsPage() {
  const router = useRouter();

  // --- list state ------------------------------------------------------
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [stageFilter, setStageFilter] = useState([]);
  const [view, setView] = useState("all");
  const [unreadFilter, setUnreadFilter] = useState(false);
  const [filtersSyncedFromUrl, setFiltersSyncedFromUrl] = useState(false);
  const searchDebounceRef = useRef(null);
  const fetchJobsRequestIdRef = useRef(0);
  const searchInputRef = useRef(null);

  // --- selection + timeline -------------------------------------------
  const [selectedJobId, setSelectedJobId] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState(null);

  // --- ui state --------------------------------------------------------
  const [compact, setCompact] = useState(false);
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelectedIds, setMergeSelectedIds] = useState(new Set());
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [mergeSubmitting, setMergeSubmitting] = useState(false);
  const [deleteConfirmJob, setDeleteConfirmJob] = useState(null);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyDraft, setReplyDraft] = useState(null);
  const [generatingFollowUp, setGeneratingFollowUp] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const visibleJobs = useMemo(() => {
    const filteredByView = applyViewFilter(jobs, view);
    if (!stageFilter.length) return filteredByView;
    const set = new Set(stageFilter);
    return filteredByView.filter((j) => set.has(j.current_stage));
  }, [jobs, view, stageFilter]);

  // --- data fetching ---------------------------------------------------
  const fetchJobsList = useCallback(async (q) => {
    const requestId = ++fetchJobsRequestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJobs({
        query: (q || "").trim() || undefined,
        limit: JOB_LIST_LIMIT,
        unreadOnly: unreadFilter,
      });
      if (requestId !== fetchJobsRequestIdRef.current) return;
      setJobs(data.items);
      setTotal(data.total);
    } catch (err) {
      if (requestId !== fetchJobsRequestIdRef.current) return;
      setError(err.message);
    } finally {
      if (requestId === fetchJobsRequestIdRef.current) setLoading(false);
    }
  }, [unreadFilter]);

  const refreshJobList = useCallback(
    () => fetchJobsList((debouncedSearch || "").trim()),
    [fetchJobsList, debouncedSearch]
  );

  // --- search debounce -------------------------------------------------
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
    if (!filtersSyncedFromUrl) return;
    void refreshJobList();
  }, [filtersSyncedFromUrl, debouncedSearch, refreshJobList]);

  // --- URL sync --------------------------------------------------------
  useEffect(() => {
    if (!router.isReady) return;
    const q = (firstQueryValue(router.query.q) || "").trim();
    const stages = parseStagesFromQuery(firstQueryValue(router.query.stage));
    const urlView = firstQueryValue(router.query.view);
    const u = firstQueryValue(router.query.unread);
    setSearchQuery(q);
    setDebouncedSearch(q);
    setStageFilter(stages);
    setView(VALID_VIEWS.has(urlView) ? urlView : "all");
    setUnreadFilter(u === "1" || u === "true");
    setFiltersSyncedFromUrl(true);
  }, [router.isReady, router.query.q, router.query.stage, router.query.view, router.query.unread]);

  useEffect(() => {
    if (!router.isReady || !filtersSyncedFromUrl) return;
    const urlQ = (firstQueryValue(router.query.q) || "").trim();
    const urlStages = parseStagesFromQuery(firstQueryValue(router.query.stage));
    const urlView = firstQueryValue(router.query.view) || "all";
    const u = firstQueryValue(router.query.unread);
    const urlUnread = u === "1" || u === "true";
    const localQ = (debouncedSearch || "").trim();
    const localStages = normalizeStageFilter(stageFilter);
    if (
      localQ === urlQ &&
      JSON.stringify(localStages) === JSON.stringify(urlStages) &&
      view === urlView &&
      unreadFilter === urlUnread
    ) {
      return;
    }
    router.replace(
      {
        pathname: "/jobs",
        query: buildJobsListQuery({ q: debouncedSearch, stage: stageFilter, view, unreadOnly: unreadFilter }),
      },
      undefined,
      { shallow: true }
    );
  }, [
    router.isReady,
    filtersSyncedFromUrl,
    debouncedSearch,
    stageFilter,
    view,
    unreadFilter,
    router.query.q,
    router.query.stage,
    router.query.view,
    router.query.unread,
  ]);

  // Deep link ?job=<id>
  useEffect(() => {
    if (!router.isReady || !router.query.job) return;
    const raw = router.query.job;
    const jobId = Array.isArray(raw) ? raw[0] : raw;
    if (jobId) setSelectedJobId(jobId);
    const { job: _removed, ...rest } = router.query;
    router.replace(
      {
        pathname: "/jobs",
        query: Object.fromEntries(Object.entries(rest).filter(([, v]) => v != null && v !== "")),
      },
      undefined,
      { shallow: true }
    );
  }, [router.isReady, router.query.job]);

  // Load timeline when selection changes.
  useEffect(() => {
    if (!selectedJobId) {
      setTimeline(null);
      return;
    }
    let cancelled = false;
    setTimelineLoading(true);
    setTimelineError(null);
    fetchTimeline(selectedJobId)
      .then((data) => {
        if (cancelled) return;
        setTimeline(data);
        setJobs((prev) =>
          prev.map((j) =>
            j.id === selectedJobId ? { ...j, unread_incoming_count: 0 } : j
          )
        );
      })
      .catch((err) => {
        if (!cancelled) setTimelineError(err.message);
      })
      .finally(() => {
        if (!cancelled) setTimelineLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedJobId]);

  // --- handlers --------------------------------------------------------
  const handleStageChange = useCallback(
    async (jobId, newStage, reason) => {
      try {
        await changeStage(jobId, newStage, reason);
        await refreshJobList();
        scrollJobListItemIntoView(jobId);
        const tl = await fetchTimeline(jobId);
        setTimeline(tl);
      } catch (err) {
        alert(`Failed to change stage: ${err.message}`);
      }
    },
    [refreshJobList]
  );

  const handleJobUpdate = useCallback(
    async (jobId, fields) => {
      await updateJob(jobId, fields);
      await refreshJobList();
      scrollJobListItemIntoView(jobId);
      const tl = await fetchTimeline(jobId);
      setTimeline(tl);
    },
    [refreshJobList]
  );

  const handleTimelineReadState = useCallback(
    async (jobId, read) => {
      try {
        const detail = await setJobTimelineReadState(jobId, read);
        setJobs((prev) =>
          prev.map((j) =>
            String(j.id) === String(jobId)
              ? { ...j, unread_incoming_count: detail.unread_incoming_count }
              : j
          )
        );
        setTimeline((t) =>
          t && t.job && String(t.job.id) === String(jobId)
            ? { ...t, job: { ...t.job, unread_incoming_count: detail.unread_incoming_count } }
            : t
        );
      } catch (err) {
        alert(err.message || "Failed to update read state");
      }
    },
    []
  );

  const handleDismissNeedsReply = useCallback(async (jobId) => {
    try {
      const detail = await dismissNeedsReply(jobId);
      setJobs((prev) =>
        prev.map((j) =>
          String(j.id) === String(jobId)
            ? {
                ...j,
                next_action: detail.next_action,
                suggest_followup: detail.suggest_followup,
              }
            : j
        )
      );
      setTimeline((t) =>
        t && t.job && String(t.job.id) === String(jobId) ? { ...t, job: { ...t.job, ...detail } } : t
      );
    } catch (err) {
      alert(err.message || "Failed to update");
    }
  }, []);

  const handleReply = useCallback(async () => {
    if (!selectedJobId) return;
    setReplyDraft(null);
    try {
      const existing = await getDraftForJob(selectedJobId);
      if (existing) setReplyDraft(existing);
    } catch {
      // no existing draft
    }
    setReplyOpen(true);
  }, [selectedJobId]);

  const handleGenerateFollowUp = useCallback(async () => {
    if (!selectedJobId) return;
    setGeneratingFollowUp(true);
    try {
      const res = await generateFollowUpSuggestion(selectedJobId);
      if (res.draft) {
        setReplyDraft(res.draft);
        setReplyOpen(true);
      }
    } catch (err) {
      alert(err.message || "Failed to generate follow-up");
    } finally {
      setGeneratingFollowUp(false);
    }
  }, [selectedJobId]);

  const handleReplySent = useCallback(async () => {
    if (selectedJobId) {
      try {
        const tl = await fetchTimeline(selectedJobId);
        setTimeline(tl);
      } catch {
        // ignore
      }
    }
    setReplyDraft(null);
    await refreshJobList();
  }, [selectedJobId, refreshJobList]);

  const handleDeleteJob = useCallback(
    async (jobId) => {
      try {
        await deleteJob(jobId);
        setSelectedJobId(null);
        setTimeline(null);
        await refreshJobList();
      } catch (err) {
        alert(`Failed to delete job: ${err.message}`);
      }
    },
    [refreshJobList]
  );

  const toggleMergeSelection = useCallback((jobId) => {
    setMergeSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  }, []);

  const handleMergeConfirm = useCallback(
    async (targetId, sourceIds) => {
      if (sourceIds.length === 0) return;
      setMergeSubmitting(true);
      try {
        await mergeJobs(targetId, sourceIds);
        setShowMergeModal(false);
        setMergeSelectedIds(new Set());
        setMergeMode(false);
        setSelectedJobId(targetId);
        await refreshJobList();
        scrollJobListItemIntoView(targetId);
        const tl = await fetchTimeline(targetId);
        setTimeline(tl);
      } catch (err) {
        alert(`Merge failed: ${err.message}`);
      } finally {
        setMergeSubmitting(false);
      }
    },
    [refreshJobList]
  );

  // --- keyboard --------------------------------------------------------
  const moveSelection = useCallback(
    (delta) => {
      if (!visibleJobs.length) return;
      const idx = visibleJobs.findIndex((j) => j.id === selectedJobId);
      let nextIdx;
      if (idx === -1) {
        nextIdx = delta > 0 ? 0 : visibleJobs.length - 1;
      } else {
        nextIdx = Math.min(visibleJobs.length - 1, Math.max(0, idx + delta));
      }
      const next = visibleJobs[nextIdx];
      if (next) {
        setSelectedJobId(next.id);
        scrollJobListItemIntoView(next.id);
      }
    },
    [visibleJobs, selectedJobId]
  );

  useKeyboardShortcuts({
    enabled: !replyOpen && !deleteConfirmJob && !showMergeModal && !shortcutsOpen,
    onFocusSearch: () => searchInputRef.current?.focus(),
    onNext: () => moveSelection(1),
    onPrev: () => moveSelection(-1),
    onReply: () => {
      if (selectedJobId) void handleReply();
    },
    onToggleRead: () => {
      if (!selectedJobId || !timeline?.job) return;
      const isUnread = (timeline.job.unread_incoming_count ?? 0) > 0;
      void handleTimelineReadState(selectedJobId, isUnread);
    },
    onDismissNeedsReply: () => {
      if (!selectedJobId || !timeline?.job) return;
      const t = timeline.job.next_action?.type;
      if (t !== "needs_reply" && t !== "follow_up") return;
      void handleDismissNeedsReply(selectedJobId);
    },
    onShowShortcuts: () => setShortcutsOpen(true),
  });

  const toggleStageInFilter = useCallback((s) => {
    setStageFilter((prev) => {
      const set = new Set(prev);
      if (set.has(s)) set.delete(s);
      else set.add(s);
      return normalizeStageFilter(Array.from(set));
    });
  }, []);

  // --- render ----------------------------------------------------------
  const sourceMessage = useMemo(() => {
    const msgs = timeline?.messages;
    if (!msgs?.length) return null;
    const sorted = [...msgs].sort(
      (a, b) => new Date(b.date_header || b.id) - new Date(a.date_header || a.id)
    );
    return sorted[0] ?? null;
  }, [timeline?.messages]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <PipelineStrip
        jobs={jobs}
        activeStages={stageFilter}
        onToggleStage={toggleStageInFilter}
      />
      <Box sx={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {/* ----- List pane ----- */}
        <Box
          sx={{
            width: 360,
            minWidth: 300,
            borderRight: 1,
            borderColor: "divider",
            display: "flex",
            flexDirection: "column",
            bgcolor: "background.paper",
          }}
        >
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 1,
              px: 2,
              pt: 2,
            }}
          >
            <Typography variant="h6" fontWeight={600}>
              Jobs
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {loading
                ? "Loading…"
                : `${visibleJobs.length}${
                    visibleJobs.length !== total && !stageFilter.length && view === "all"
                      ? ` of ${total}`
                      : ""
                  }`}
            </Typography>
          </Box>

          {mergeMode ? (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 1,
                px: 2,
                py: 1,
                mt: 1,
                mx: 2,
                borderRadius: 1,
                bgcolor: "action.selected",
              }}
            >
              <Typography variant="body2">
                {mergeSelectedIds.size >= 2
                  ? `${mergeSelectedIds.size} selected`
                  : "Select 2+ jobs to merge"}
              </Typography>
              <Box sx={{ display: "flex", gap: 0.5 }}>
                {mergeSelectedIds.size >= 2 ? (
                  <Button size="small" variant="contained" onClick={() => setShowMergeModal(true)}>
                    Merge
                  </Button>
                ) : null}
                <Button
                  size="small"
                  onClick={() => {
                    setMergeMode(false);
                    setMergeSelectedIds(new Set());
                  }}
                >
                  Cancel
                </Button>
              </Box>
            </Box>
          ) : null}

          <JobListToolbar
            searchValue={searchQuery}
            onSearchChange={setSearchQuery}
            searchInputRef={searchInputRef}
            view={view}
            onViewChange={setView}
            unreadOnly={unreadFilter}
            onUnreadOnlyChange={setUnreadFilter}
            compact={compact}
            onCompactChange={setCompact}
            onEnterMergeMode={() => setMergeMode(true)}
            onShowShortcuts={() => setShortcutsOpen(true)}
          />

          {error ? (
            <Alert severity="error" sx={{ mx: 2, mt: 1 }}>
              {error}
            </Alert>
          ) : null}

          <Box sx={{ flex: 1, overflowY: "auto", pl: 1, pr: 0.25, py: 1, position: "relative" }}>
            {loading ? (
              <Box
                sx={{
                  position: "absolute",
                  inset: 0,
                  zIndex: 1,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  bgcolor: (theme) =>
                    theme.palette.mode === "dark"
                      ? "rgba(0,0,0,0.35)"
                      : "rgba(255,255,255,0.72)",
                  backdropFilter: "blur(2px)",
                }}
              >
                <CircularProgress size={28} aria-label="Loading jobs" />
              </Box>
            ) : null}
            {visibleJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                selected={job.id === selectedJobId}
                selectedForMerge={mergeSelectedIds.has(job.id)}
                mergeMode={mergeMode}
                onToggleMerge={toggleMergeSelection}
                onClick={() => setSelectedJobId(job.id)}
                compact={compact}
              />
            ))}
            {!loading && visibleJobs.length === 0 ? (
              <Box sx={{ py: 6, px: 3, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  No jobs match.
                </Typography>
                {stageFilter.length || view !== "all" || debouncedSearch || unreadFilter ? (
                  <Button
                    size="small"
                    sx={{ mt: 1 }}
                    onClick={() => {
                      setStageFilter([]);
                      setView("all");
                      setSearchQuery("");
                      setUnreadFilter(false);
                    }}
                  >
                    Clear filters
                  </Button>
                ) : null}
              </Box>
            ) : null}
          </Box>
        </Box>

        {/* ----- Timeline pane ----- */}
        <Box sx={{ flex: 1, overflowY: "auto", px: 3, pb: 3, bgcolor: "background.default" }}>
          {!selectedJobId ? (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                height: "100%",
                color: "text.secondary",
                gap: 2,
                flexDirection: "column",
              }}
            >
              <Typography>Select a job to view its timeline.</Typography>
              <Typography variant="caption">
                Tip: press <b>j/k</b> to navigate · <b>r</b> to reply · <b>d</b> no reply needed · <b>?</b> for
                shortcuts.
              </Typography>
            </Box>
          ) : timelineLoading ? (
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", gap: 1 }}>
              <CircularProgress size={22} />
              <Typography color="text.secondary">Loading timeline…</Typography>
            </Box>
          ) : timelineError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {timelineError}
            </Alert>
          ) : timeline ? (
            <>
              <JobHeader
                job={timeline.job}
                onStageChange={handleStageChange}
                onJobUpdate={handleJobUpdate}
                onRequestDelete={setDeleteConfirmJob}
                onMarkReadState={handleTimelineReadState}
                onDismissNeedsReply={handleDismissNeedsReply}
                onReply={handleReply}
                onGenerateFollowUp={handleGenerateFollowUp}
                followUpBusy={generatingFollowUp}
              />
              <Thread timeline={timeline} />
            </>
          ) : null}
        </Box>
      </Box>

      {showMergeModal ? (
        <MergeJobsDialog
          jobs={jobs}
          selectedIds={Array.from(mergeSelectedIds)}
          onClose={() => !mergeSubmitting && setShowMergeModal(false)}
          onConfirm={handleMergeConfirm}
        />
      ) : null}

      <ConfirmModal
        open={!!deleteConfirmJob}
        title="Delete job?"
        message={
          deleteConfirmJob
            ? `Delete "${deleteConfirmJob.company || "this job"} – ${deleteConfirmJob.role || "no role"}"? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        danger
        onConfirm={() => {
          if (deleteConfirmJob) handleDeleteJob(deleteConfirmJob.id);
          setDeleteConfirmJob(null);
        }}
        onCancel={() => setDeleteConfirmJob(null)}
      />

      <ReplyDrawer
        open={replyOpen}
        jobId={selectedJobId}
        draft={replyDraft}
        sourceMessageId={sourceMessage?.id ?? null}
        sourceMessageSubject={sourceMessage?.subject ?? null}
        onClose={() => setReplyOpen(false)}
        onSent={handleReplySent}
      />

      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </Box>
  );
}
