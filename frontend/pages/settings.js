import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import TextField from "@mui/material/TextField";
import FormControl from "@mui/material/FormControl";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import {
  startGmailOAuth,
  listEmailAccounts,
  disconnectEmailAccount,
  triggerSync,
  deleteAccountMessages,
  checkLlmKey,
  setLlmKey,
} from "../lib/api";
import ConfirmModal from "../components/ConfirmModal";

const SYNC_PERIODS = [
  { label: "Last 1 day", days: 1 },
  { label: "Last 3 days", days: 3 },
  { label: "Last 7 days", days: 7 },
  { label: "Last 14 days", days: 14 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
  { label: "Last 180 days", days: 180 },
  { label: "Last 365 days", days: 365 },
];

function GmailIcon() {
  return (
    <Box component="svg" width={32} height={32} viewBox="0 0 32 32" fill="none">
      <rect width="32" height="32" rx="6" fill="#ea4335" opacity="0.12" />
      <path d="M8 12l8 5 8-5v10H8V12z" fill="#ea4335" opacity="0.5" />
      <path d="M8 10l8 5 8-5" stroke="#ea4335" strokeWidth="1.5" strokeLinejoin="round" />
    </Box>
  );
}

function KeyIcon() {
  return (
    <Box component="svg" width={32} height={32} viewBox="0 0 32 32" fill="none">
      <rect width="32" height="32" rx="6" fill="#6366f1" opacity="0.12" />
      <path
        d="M20 14a4 4 0 11-8 0 4 4 0 018 0zM16 18v5m-2-2h4"
        stroke="#6366f1"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Box>
  );
}

function AccountCard({ account, onRequestDisconnect }) {
  const [syncing, setSyncing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [lookbackDays, setLookbackDays] = useState(7);
  const [syncResult, setSyncResult] = useState(null);
  const [showDeleteMessagesConfirm, setShowDeleteMessagesConfirm] = useState(false);

  async function handleForceSync() {
    setSyncing(true);
    setSyncResult(null);
    try {
      await triggerSync(account.id, lookbackDays);
      setSyncResult(
        `Sync queued — scanning last ${lookbackDays} day${lookbackDays > 1 ? "s" : ""}. Check the Jobs page shortly.`
      );
    } catch (err) {
      setSyncResult(`Sync failed: ${err.message}`);
    } finally {
      setSyncing(false);
    }
  }

  async function doDeleteMessages() {
    setDeleting(true);
    setSyncResult(null);
    try {
      const res = await deleteAccountMessages(account.id);
      setSyncResult(
        `Deleted ${res.deleted_messages} message${res.deleted_messages !== 1 ? "s" : ""}, ` +
        `${res.deleted_extractions} extraction${res.deleted_extractions !== 1 ? "s" : ""}, ` +
        `${res.deleted_jobs} job${res.deleted_jobs !== 1 ? "s" : ""}, ` +
        `${res.deleted_contacts} contact${res.deleted_contacts !== 1 ? "s" : ""}. Use Force Sync to re-ingest.`
      );
    } catch (err) {
      setSyncResult(`Delete failed: ${err.message}`);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Paper variant="outlined" sx={{ overflow: "hidden", mb: 1.5 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          p: 1.5,
          borderBottom: 1,
          borderColor: "divider",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              bgcolor: "success.main",
            }}
          />
          <Typography fontWeight={500} fontSize={14}>
            {account.email_address}
          </Typography>
          <Typography variant="caption" color="success.main">
            Connected
          </Typography>
        </Box>
        <Button
          size="small"
          color="error"
          variant="outlined"
          onClick={onRequestDisconnect}
        >
          Disconnect
        </Button>
      </Box>
      <Box sx={{ p: 1.5, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 1 }}>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>Sync period</InputLabel>
          <Select
            value={lookbackDays}
            label="Sync period"
            onChange={(e) => setLookbackDays(Number(e.target.value))}
          >
            {SYNC_PERIODS.map((p) => (
              <MenuItem key={p.days} value={p.days}>{p.label}</MenuItem>
            ))}
          </Select>
        </FormControl>
        <Button
          variant="contained"
          size="small"
          disabled={syncing || deleting}
          onClick={handleForceSync}
        >
          {syncing ? "Syncing..." : "Force Sync"}
        </Button>
        <Button
          size="small"
          color="error"
          variant="outlined"
          disabled={deleting || syncing}
          onClick={() => setShowDeleteMessagesConfirm(true)}
        >
          {deleting ? "Deleting..." : "Delete All Emails"}
        </Button>
        {syncResult && (
          <Typography variant="caption" color="text.secondary" sx={{ width: "100%", mt: 1 }}>
            {syncResult}
          </Typography>
        )}
      </Box>
      <ConfirmModal
        open={showDeleteMessagesConfirm}
        title="Delete all account data?"
        message="Delete ALL ingested emails, extractions, jobs, and contacts for this account? This cannot be undone. You can re-sync afterwards to re-ingest."
        confirmLabel="Delete all"
        danger={true}
        onConfirm={() => {
          setShowDeleteMessagesConfirm(false);
          doDeleteMessages();
        }}
        onCancel={() => setShowDeleteMessagesConfirm(false)}
      />
    </Paper>
  );
}

function GmailSection() {
  const router = useRouter();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [disconnectConfirmAccount, setDisconnectConfirmAccount] = useState(null);

  useEffect(() => {
    if (router.query.gmail === "connected") {
      setSuccess("Gmail account connected successfully!");
      router.replace("/settings", undefined, { shallow: true });
    }
  }, [router.query.gmail]);

  async function loadAccounts() {
    try {
      const data = await listEmailAccounts();
      setAccounts(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAccounts();
  }, []);

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const { auth_url } = await startGmailOAuth();
      window.location.href = auth_url;
    } catch (err) {
      setError(err.message);
      setConnecting(false);
    }
  }

  async function handleDisconnect(accountId) {
    try {
      await disconnectEmailAccount(accountId);
      await loadAccounts();
    } catch (err) {
      setError(err.message);
    }
  }

  const activeAccounts = accounts.filter((a) => a.status === "active");

  return (
    <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
        <Box>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            Gmail Connection
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480 }}>
            Connect your Gmail account to automatically sync and classify job-related emails.
          </Typography>
        </Box>
        <GmailIcon />
      </Box>

      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {loading ? (
        <Typography color="text.secondary">Loading accounts...</Typography>
      ) : activeAccounts.length > 0 ? (
        <Box>
          {activeAccounts.map((acc) => (
            <AccountCard
              key={acc.id}
              account={acc}
              onRequestDisconnect={() => setDisconnectConfirmAccount(acc)}
            />
          ))}
          <ConfirmModal
            open={!!disconnectConfirmAccount}
            title="Disconnect Gmail?"
            message="Disconnect this Gmail account?"
            confirmLabel="Disconnect"
            danger={true}
            onConfirm={() => {
              if (disconnectConfirmAccount) {
                handleDisconnect(disconnectConfirmAccount.id);
                setDisconnectConfirmAccount(null);
              }
            }}
            onCancel={() => setDisconnectConfirmAccount(null)}
          />
          <Button variant="outlined" onClick={handleConnect} disabled={connecting} sx={{ mt: 1 }}>
            {connecting ? "Redirecting..." : "Connect Another Account"}
          </Button>
        </Box>
      ) : (
        <Button
          variant="contained"
          size="large"
          onClick={handleConnect}
          disabled={connecting}
        >
          {connecting ? "Redirecting to Google..." : "Connect Gmail Account"}
        </Button>
      )}
    </Paper>
  );
}

function LlmKeySection() {
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    checkLlmKey()
      .then((data) => setConfigured(data.configured))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    if (!apiKey.trim()) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await setLlmKey(apiKey.trim());
      setConfigured(true);
      setApiKey("");
      setSuccess("API key saved successfully!");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
        <Box>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            OpenAI API Key
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 480 }}>
            Required for classifying emails. Your key is encrypted and never exposed via the API.
          </Typography>
        </Box>
        <KeyIcon />
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      {loading ? (
        <Typography color="text.secondary">Checking...</Typography>
      ) : (
        <Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                bgcolor: configured ? "success.main" : "grey.500",
              }}
            />
            <Typography variant="body2">
              {configured ? "API key is configured" : "No API key configured"}
            </Typography>
          </Box>
          <Box sx={{ display: "flex", gap: 1.25, flexWrap: "wrap", alignItems: "center" }}>
            <TextField
              type="password"
              placeholder={configured ? "Enter new key to replace..." : "sk-..."}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              size="small"
              sx={{ flex: 1, minWidth: 200, maxWidth: 400 }}
            />
            <Button
              variant="contained"
              onClick={handleSave}
              disabled={!apiKey.trim() || saving}
            >
              {saving ? "Saving..." : configured ? "Update Key" : "Save Key"}
            </Button>
          </Box>
        </Box>
      )}
    </Paper>
  );
}

function HowItWorksSection() {
  const steps = [
    { num: 1, title: "Connect Gmail", desc: "Authorize read access so the app can scan your inbox." },
    { num: 2, title: "Add OpenAI Key", desc: "Used to classify emails into categories (status updates, recruiter outreach, alerts)." },
    { num: 3, title: "Automatic Sync", desc: "Every 5 minutes, new emails are fetched, classified, and matched to jobs." },
    { num: 4, title: "Track Jobs", desc: "View your job pipeline on the Jobs page with full email timelines." },
  ];
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 3,
        borderStyle: "dashed",
        bgcolor: "transparent",
      }}
    >
      <Typography variant="h6" fontWeight={600} gutterBottom>
        How It Works
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {steps.map((s) => (
          <Box key={s.num} sx={{ display: "flex", alignItems: "flex-start", gap: 2 }}>
            <Box
              sx={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                bgcolor: "primary.main",
                color: "white",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 13,
                fontWeight: 600,
                flexShrink: 0,
              }}
            >
              {s.num}
            </Box>
            <Box>
              <Typography fontWeight={600} fontSize={14}>
                {s.title}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {s.desc}
              </Typography>
            </Box>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

export default function SettingsPage() {
  return (
    <Box sx={{ maxWidth: 900, mx: "auto", p: 3, minHeight: "100vh" }}>
      <Box sx={{ pb: 2, mb: 2, borderBottom: 1, borderColor: "divider" }}>
        <Typography variant="h5" fontWeight={700}>
          Settings
        </Typography>
      </Box>
      <GmailSection />
      <LlmKeySection />
      <HowItWorksSection />
    </Box>
  );
}
