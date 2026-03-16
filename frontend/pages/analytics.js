import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Paper from "@mui/material/Paper";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import dynamic from "next/dynamic";
import {
  fetchAnalyticsSummary,
  fetchAnalyticsFunnel,
  fetchAnalyticsTimeseries,
  fetchAnalyticsFunnelFlow,
} from "../lib/api";

const SankeyChart = dynamic(
  () => import("../components/SankeyChart").then((m) => m.SankeyChart),
  { ssr: false, loading: () => null }
);

const STAGE_ORDER = [
  "SOURCED",
  "APPLIED",
  "SCREEN",
  "INTERVIEW",
  "TAKEHOME",
  "FINAL",
  "OFFER",
  "REJECTED",
  "WITHDRAWN",
];

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

function SummaryCard({ title, value, subtext }) {
  return (
    <Card variant="outlined" sx={{ height: "100%", bgcolor: "background.paper" }}>
      <CardContent sx={{ "&:last-child": { pb: 2 } }}>
        <Typography
          variant="body2"
          color="text.secondary"
          display="block"
          sx={{ fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em", fontSize: 11 }}
        >
          {title}
        </Typography>
        <Typography variant="h4" fontWeight={700} sx={{ mt: 0.5 }}>
          {value}
        </Typography>
        {subtext != null && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            {subtext}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

function FunnelBar({ label, count, color, widthPercent }) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
        <Typography variant="body2" fontWeight={500}>
          {label}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {count}
        </Typography>
      </Box>
      <Box
        sx={{
          height: 28,
          borderRadius: 1,
          bgcolor: "action.hover",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            height: "100%",
            width: `${Math.max(widthPercent, 2)}%`,
            bgcolor: color,
            borderRadius: 1,
            minWidth: count > 0 ? 24 : 0,
          }}
        />
      </Box>
    </Box>
  );
}

function TrendChart({ title, data, color }) {
  const maxCount = Math.max(1, ...data.map((d) => d.count));
  return (
    <Paper variant="outlined" sx={{ p: 2, bgcolor: "background.paper" }}>
      <Typography variant="overline" color="text.secondary" display="block" gutterBottom>
        {title}
      </Typography>
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 0.5, minHeight: 120 }}>
        {data.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No data in this window
          </Typography>
        ) : (
          data.map((d) => (
            <Box
              key={d.date}
              sx={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
              }}
            >
              <Box
                sx={{
                  width: "100%",
                  height: Math.max(4, (d.count / maxCount) * 100),
                  bgcolor: color,
                  borderRadius: 0.5,
                  minHeight: 4,
                }}
                title={`${d.date}: ${d.count}`}
              />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, fontSize: 10 }}>
                {d.date ? d.date.slice(5) : ""}
              </Typography>
            </Box>
          ))
        )}
      </Box>
    </Paper>
  );
}

export default function AnalyticsPage() {
  const [summary, setSummary] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [funnelFlow, setFunnelFlow] = useState(null);
  const [timeseries, setTimeseries] = useState(null);
  const [window, setWindow] = useState("30d");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, f, flow, t] = await Promise.all([
        fetchAnalyticsSummary(),
        fetchAnalyticsFunnel(),
        fetchAnalyticsFunnelFlow(),
        fetchAnalyticsTimeseries(window),
      ]);
      setSummary(s);
      setFunnel(f);
      setFunnelFlow(flow);
      setTimeseries(t);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [window]);

  useEffect(() => {
    load();
  }, [load]);

  const maxMilestone = funnel?.milestones
    ? Math.max(
        funnel.milestones.applied || 0,
        funnel.milestones.interview || 0,
        funnel.milestones.offer || 0,
        funnel.milestones.rejected || 0,
        1
      )
    : 1;

  return (
    <Box
      sx={{
        width: "100%",
        maxWidth: 1200,
        mx: "auto",
        px: 3,
        pt: 3,
        pb: 4,
        minHeight: "100%",
      }}
    >
      <Typography variant="h5" fontWeight={700} sx={{ mb: 3 }}>
        Analytics
      </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {loading ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, py: 4 }}>
            <CircularProgress size={28} />
            <Typography color="text.secondary">Loading analytics…</Typography>
          </Box>
        ) : (
          <>
            {/* Summary cards: horizontal spread, 5 columns on md+ */}
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: {
                  xs: "repeat(2, 1fr)",
                  sm: "repeat(3, 1fr)",
                  md: "repeat(5, 1fr)",
                },
                gap: 2,
                mb: 4,
              }}
            >
              <SummaryCard title="Total jobs" value={summary?.total_jobs ?? 0} />
              <SummaryCard
                title="Applications"
                value={summary?.applications_received ?? 0}
              />
              <SummaryCard
                title="Interviews"
                value={summary?.interviews_detected ?? 0}
              />
              <SummaryCard title="Offers" value={summary?.offers ?? 0} />
              <SummaryCard title="Rejections" value={summary?.rejections ?? 0} />
              <SummaryCard
                title="App → Interview"
                value={
                  summary?.conversion_application_to_interview != null
                    ? `${(summary.conversion_application_to_interview * 100).toFixed(1)}%`
                    : "—"
                }
              />
              <SummaryCard
                title="Interview → Offer"
                value={
                  summary?.conversion_interview_to_offer != null
                    ? `${(summary.conversion_interview_to_offer * 100).toFixed(1)}%`
                    : "—"
                }
              />
              <SummaryCard
                title="Avg days to first interview"
                value={
                  summary?.avg_days_applied_to_first_interview != null
                    ? summary.avg_days_applied_to_first_interview.toFixed(1)
                    : "—"
                }
                subtext="days from application"
              />
              <SummaryCard
                title="Activity (7d)"
                value={summary?.recent_activity_7d ?? 0}
              />
              <SummaryCard
                title="Activity (30d)"
                value={summary?.recent_activity_30d ?? 0}
              />
            </Box>

            {/* Funnel: milestone = "ever reached" */}
            <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
              Funnel
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
              Jobs that have ever reached each step (from events)
            </Typography>
            <Paper variant="outlined" sx={{ p: 2, mb: 4, bgcolor: "background.paper" }}>
              {funnel && (
                <>
                  <FunnelBar
                    label="Applied"
                    count={funnel.milestones?.applied ?? 0}
                    color={STAGE_COLORS.APPLIED}
                    widthPercent={((funnel.milestones?.applied ?? 0) / maxMilestone) * 100}
                  />
                  <FunnelBar
                    label="Interview"
                    count={funnel.milestones?.interview ?? 0}
                    color={STAGE_COLORS.INTERVIEW}
                    widthPercent={((funnel.milestones?.interview ?? 0) / maxMilestone) * 100}
                  />
                  <FunnelBar
                    label="Offer"
                    count={funnel.milestones?.offer ?? 0}
                    color={STAGE_COLORS.OFFER}
                    widthPercent={((funnel.milestones?.offer ?? 0) / maxMilestone) * 100}
                  />
                  <FunnelBar
                    label="Rejected"
                    count={funnel.milestones?.rejected ?? 0}
                    color={STAGE_COLORS.REJECTED}
                    widthPercent={((funnel.milestones?.rejected ?? 0) / maxMilestone) * 100}
                  />
                </>
              )}
            </Paper>

            {/* Sankey: stage-to-stage flow */}
            <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
              Funnel flow (Sankey)
            </Typography>
            <Paper variant="outlined" sx={{ p: 2, mb: 4, bgcolor: "background.paper", overflow: "hidden" }}>
              {!mounted ? (
                <Box sx={{ width: "100%", height: 340, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <Typography variant="body2" color="text.secondary">Loading chart…</Typography>
                </Box>
              ) : (
                <SankeyChart flows={funnelFlow?.flows} />
              )}
            </Paper>

            {/* By stage: current state only */}
            {funnel?.by_stage && Object.keys(funnel.by_stage).length > 0 && (
              <>
                <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                  Jobs by current stage
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  Where each job is right now (one stage per job)
                </Typography>
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 4 }}>
                  {STAGE_ORDER.filter((s) => funnel.by_stage[s]).map((stage) => (
                    <Box
                      key={stage}
                      sx={{
                        px: 1.5,
                        py: 0.75,
                        borderRadius: 1,
                        bgcolor: STAGE_COLORS[stage] || "#6b7280",
                        color: "#fff",
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                    >
                      {stage}: {funnel.by_stage[stage]}
                    </Box>
                  ))}
                </Box>
              </>
            )}

            {/* Trend: jobs created + activity */}
            <Typography variant="overline" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
              Trends
            </Typography>
            <Box sx={{ display: "flex", gap: 2, mb: 2 }}>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Window</InputLabel>
                <Select
                  value={window}
                  label="Window"
                  onChange={(e) => setWindow(e.target.value)}
                >
                  <MenuItem value="7d">7 days</MenuItem>
                  <MenuItem value="30d">30 days</MenuItem>
                  <MenuItem value="90d">90 days</MenuItem>
                </Select>
              </FormControl>
            </Box>
            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
              <TrendChart
                title="Jobs created over time"
                data={timeseries?.jobs_created ?? []}
                color="primary.main"
              />
              <TrendChart
                title="Activity (events) over time"
                data={timeseries?.activity ?? []}
                color="#f59e0b"
              />
            </Box>
          </>
        )}
    </Box>
  );
}
