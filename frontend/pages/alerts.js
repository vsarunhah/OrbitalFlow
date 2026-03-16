import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import { fetchAlerts, deleteAlert } from "../lib/api";
import ConfirmModal from "../components/ConfirmModal";

function AlertCard({ alert, onRequestDelete }) {
  return (
    <Card
      variant="outlined"
      sx={{
        mb: 1,
        "&:hover": { borderColor: "primary.main" },
        transition: "border-color 0.15s",
      }}
    >
      <CardContent>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
          <Typography fontWeight={600} fontSize={14}>
            {alert.subject || "(no subject)"}
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            {alert.provider_msg_id && (
              <Link
                href={`https://mail.google.com/mail/u/0/#all/${alert.provider_msg_id}`}
                target="_blank"
                rel="noopener noreferrer"
                color="text.secondary"
                fontSize={14}
                sx={{ opacity: 0.7, "&:hover": { opacity: 1 } }}
                title="Open in Gmail"
              >
                ↗
              </Link>
            )}
            <Button
              size="small"
              color="error"
              variant="outlined"
              onClick={(e) => {
                e.stopPropagation();
                onRequestDelete(alert);
              }}
              title="Delete alert"
            >
              Delete
            </Button>
            <Chip label="ALERT" size="small" sx={{ bgcolor: "#f59e0b", color: "#fff", fontWeight: 600, fontSize: 10 }} />
          </Box>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {alert.from_address || "Unknown"}
        </Typography>
        {alert.jobs && alert.jobs.length > 0 ? (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75, mt: 1 }}>
            {alert.jobs.map((job, i) => (
              <Box
                key={i}
                sx={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  p: 0.75,
                  bgcolor: "action.hover",
                  borderRadius: 1,
                  fontSize: 13,
                }}
              >
                <Box>
                  <Typography fontWeight={600} fontSize={13}>
                    {job.role}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {job.company}
                  </Typography>
                </Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
                  {job.location && (
                    <Typography variant="caption" color="text.secondary">
                      {job.location}
                    </Typography>
                  )}
                  {job.url && (
                    <Link href={job.url} target="_blank" rel="noopener noreferrer" fontSize={12}>
                      View →
                    </Link>
                  )}
                </Box>
              </Box>
            ))}
          </Box>
        ) : (
          alert.body_snippet && (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ lineHeight: 1.4, maxHeight: 60, overflow: "hidden", whiteSpace: "pre-wrap" }}
            >
              {alert.body_snippet}
            </Typography>
          )
        )}
        {alert.date_header && (
          <Typography component="time" variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
            {new Date(alert.date_header).toLocaleString()}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);
  const [deleteConfirmAlert, setDeleteConfirmAlert] = useState(null);
  const limit = 50;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAlerts({ limit, offset });
      setAlerts(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDeleteAlert(alertId) {
    try {
      await deleteAlert(alertId);
      await load();
    } catch (err) {
      alert(`Failed to delete alert: ${err.message}`);
    }
  }

  const hasNext = offset + limit < total;
  const hasPrev = offset > 0;

  return (
    <Box sx={{ maxWidth: 900, mx: "auto", p: 3, minHeight: "100vh" }}>
      <Box sx={{ pb: 2, mb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Typography variant="h5" fontWeight={700}>
          Job Alerts
        </Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {loading ? "Loading..." : `${total} alert${total !== 1 ? "s" : ""}`}
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {alerts.map((a) => (
          <AlertCard key={a.id} alert={a} onRequestDelete={setDeleteConfirmAlert} />
        ))}
        {!loading && alerts.length === 0 && (
          <Typography color="text.secondary" fontStyle="italic" sx={{ py: 4, textAlign: "center" }}>
            No alerts found
          </Typography>
        )}
      </Box>

      <ConfirmModal
        open={!!deleteConfirmAlert}
        title="Delete alert?"
        message="Delete this alert? This cannot be undone."
        confirmLabel="Delete"
        danger={true}
        onConfirm={() => {
          if (deleteConfirmAlert) handleDeleteAlert(deleteConfirmAlert.id);
          setDeleteConfirmAlert(null);
        }}
        onCancel={() => setDeleteConfirmAlert(null)}
      />

      {(hasPrev || hasNext) && (
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, mt: 2.5 }}>
          <Button
            variant="contained"
            disabled={!hasPrev}
            onClick={() => setOffset((o) => Math.max(0, o - limit))}
          >
            Previous
          </Button>
          <Typography variant="body2" color="text.secondary">
            {offset + 1}–{Math.min(offset + limit, total)} of {total}
          </Typography>
          <Button
            variant="contained"
            disabled={!hasNext}
            onClick={() => setOffset((o) => o + limit)}
          >
            Next
          </Button>
        </Box>
      )}
    </Box>
  );
}
