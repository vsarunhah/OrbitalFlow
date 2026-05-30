import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import TextField from "@mui/material/TextField";
import Autocomplete from "@mui/material/Autocomplete";
import FormControl from "@mui/material/FormControl";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import {
  startGmailOAuth,
  listEmailAccounts,
  checkGmailTokenHealth,
  disconnectEmailAccount,
  triggerSync,
  deleteAccountMessages,
  checkLlmKey,
  setLlmKey,
  getUserProfile,
  updateUserProfile,
} from "../lib/api";
import ConfirmModal from "../components/ConfirmModal";
import {
  browserTimezone,
  formatTimezoneLabel,
  getTimezoneOptions,
} from "../lib/timezones";

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

function AccountCard({
  account,
  onRequestDisconnect,
  tokenHealth,
  onReconnect,
  oauthBusy,
}) {
  const [syncing, setSyncing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [lookbackDays, setLookbackDays] = useState(7);
  const [syncResult, setSyncResult] = useState(null);
  const [showDeleteMessagesConfirm, setShowDeleteMessagesConfirm] = useState(false);
  const tokenOk = tokenHealth?.ok !== false;
  const tokenDetail = tokenHealth?.detail;

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
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, flexWrap: "wrap" }}>
          <Box
            sx={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              bgcolor: tokenOk ? "success.main" : "error.main",
            }}
          />
          <Typography fontWeight={500} fontSize={14}>
            {account.email_address}
          </Typography>
          <Typography variant="caption" color={tokenOk ? "success.main" : "error.main"}>
            {tokenOk ? "Connected" : "Reconnect required"}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, alignItems: "center" }}>
          <Button
            size="small"
            variant="outlined"
            onClick={onReconnect}
            disabled={oauthBusy || syncing || deleting}
          >
            {oauthBusy ? "Redirecting..." : "Reconnect"}
          </Button>
          <Button
            size="small"
            color="error"
            variant="outlined"
            onClick={onRequestDisconnect}
            disabled={oauthBusy}
          >
            Disconnect
          </Button>
        </Box>
      </Box>
      {!tokenOk && tokenDetail && (
        <Box sx={{ px: 1.5, pb: 1 }}>
          <Alert severity="error">{tokenDetail}</Alert>
        </Box>
      )}
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
          disabled={syncing || deleting || !tokenOk}
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
  const [tokenHealthById, setTokenHealthById] = useState({});
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [disconnectConfirmAccount, setDisconnectConfirmAccount] = useState(null);

  const loadAccounts = useCallback(async () => {
    try {
      const data = await listEmailAccounts();
      setAccounts(data);
      const gmailActive = data.filter((a) => a.status === "active" && a.provider === "gmail");
      if (gmailActive.length > 0) {
        try {
          const h = await checkGmailTokenHealth();
          const map = {};
          for (const row of h.accounts) {
            map[row.id] = { ok: row.ok, detail: row.detail };
          }
          setTokenHealthById(map);
        } catch (healthErr) {
          setError(healthErr.message);
          const map = {};
          for (const a of gmailActive) {
            map[a.id] = {
              ok: false,
              detail:
                "Could not verify Gmail connection. Try again or check your network.",
            };
          }
          setTokenHealthById(map);
        }
      } else {
        setTokenHealthById({});
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (router.query.gmail !== "connected") return;
    setSuccess("Gmail authorization updated successfully.");
    loadAccounts();
    router.replace("/settings", undefined, { shallow: true });
  }, [router.query.gmail, loadAccounts, router]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  async function startGmailOAuthFlow() {
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
              tokenHealth={tokenHealthById[acc.id]}
              onReconnect={startGmailOAuthFlow}
              oauthBusy={connecting}
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
          <Button variant="outlined" onClick={startGmailOAuthFlow} disabled={connecting} sx={{ mt: 1 }}>
            {connecting ? "Redirecting..." : "Connect Another Account"}
          </Button>
        </Box>
      ) : (
        <Button
          variant="contained"
          size="large"
          onClick={startGmailOAuthFlow}
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

const COMPANY_SIZE_OPTIONS = [
  { id: "startup", label: "Startup (1–50)" },
  { id: "small", label: "Small (51–200)" },
  { id: "mid", label: "Mid (201–1k)" },
  { id: "large", label: "Large (1k–10k)" },
  { id: "enterprise", label: "Enterprise (10k+)" },
];

const WORK_ARRANGEMENT_OPTIONS = [
  { id: "remote", label: "Remote" },
  { id: "hybrid", label: "Hybrid" },
  { id: "onsite", label: "On-site" },
  { id: "flexible", label: "Flexible" },
];

const TIMEZONE_NOT_SPECIFIED = { value: "", label: "Not specified" };

function ProfileMultiSelect({ label, options, selectedIds, onChange, placeholder }) {
  const selectedOptions = useMemo(
    () => options.filter((option) => selectedIds.includes(option.id)),
    [options, selectedIds]
  );

  return (
    <Autocomplete
      multiple
      size="small"
      options={options}
      value={selectedOptions}
      onChange={(_, next) => onChange(next.map((option) => option.id))}
      getOptionLabel={(option) => option.label}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      disableCloseOnSelect
      renderInput={(params) => (
        <TextField {...params} label={label} placeholder={placeholder} />
      )}
      sx={{ maxWidth: 480 }}
    />
  );
}

function JobSeekerProfileSection() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [displayName, setDisplayName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [locationPreferences, setLocationPreferences] = useState("");
  const [workArrangements, setWorkArrangements] = useState([]);
  const [compensation, setCompensation] = useState("");
  const [companySizes, setCompanySizes] = useState([]);
  const [availabilityNotes, setAvailabilityNotes] = useState("");

  useEffect(() => {
    getUserProfile()
      .then((p) => {
        setDisplayName(p.display_name || "");
        setTimezone(p.timezone || "");
        setLocationPreferences(p.location_preferences || "");
        setWorkArrangements(p.work_arrangements || []);
        setCompensation(p.compensation_expectations || "");
        setCompanySizes(p.preferred_company_sizes || []);
        setAvailabilityNotes(p.availability_notes || "");
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await updateUserProfile({
        display_name: displayName.trim() || null,
        timezone: timezone.trim() || null,
        location_preferences: locationPreferences.trim() || null,
        work_arrangements: workArrangements,
        compensation_expectations: compensation.trim() || null,
        preferred_company_sizes: companySizes,
        availability_notes: availabilityNotes.trim() || null,
      });
      setSuccess("Profile saved. AI drafts will use these preferences.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const defaultTz = browserTimezone();
  const timezoneOptions = useMemo(() => getTimezoneOptions(), []);

  const timezoneSelectOptions = useMemo(() => {
    const options = [TIMEZONE_NOT_SPECIFIED, ...timezoneOptions];
    if (timezone && !options.some((o) => o.value === timezone)) {
      options.push({
        value: timezone,
        label: formatTimezoneLabel(timezone),
        offsetMinutes: 0,
      });
      options.sort(
        (a, b) =>
          a.offsetMinutes - b.offsetMinutes || a.value.localeCompare(b.value)
      );
    }
    return options;
  }, [timezone, timezoneOptions]);

  const selectedTimezoneOption = useMemo(
    () =>
      timezoneSelectOptions.find((o) => o.value === timezone) ??
      TIMEZONE_NOT_SPECIFIED,
    [timezone, timezoneSelectOptions]
  );

  return (
    <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
      <Typography variant="h6" fontWeight={600} gutterBottom>
        Job seeker profile
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 520 }}>
        Used when generating reply drafts: location and compensation preferences, company size,
        and calendar availability (when Google Calendar is connected).
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      {loading ? (
        <Typography color="text.secondary">Loading profile...</Typography>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <TextField
            label="Display name"
            size="small"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="How you sign emails"
          />
          <Autocomplete
            size="small"
            options={timezoneSelectOptions}
            value={selectedTimezoneOption}
            onChange={(_, option) => setTimezone(option?.value ?? "")}
            getOptionLabel={(option) => option.label}
            isOptionEqualToValue={(a, b) => a.value === b.value}
            autoHighlight
            filterOptions={(options, { inputValue }) => {
              const query = inputValue.trim().toLowerCase();
              if (!query) return options;
              return options.filter(
                (option) =>
                  !option.value ||
                  option.label.toLowerCase().includes(query) ||
                  option.value.toLowerCase().includes(query.replace(/\s/g, "_"))
              );
            }}
            renderOption={(props, option) => (
              <li {...props} key={option.value || "none"}>
                {option.value ? option.label : <em>{option.label}</em>}
              </li>
            )}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Timezone"
                placeholder={formatTimezoneLabel(defaultTz)}
              />
            )}
            ListboxProps={{ style: { maxHeight: 320 } }}
            sx={{ maxWidth: 480 }}
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
            Used for scheduling. Browser default: {formatTimezoneLabel(defaultTz)}
          </Typography>
          <TextField
            label="Location preferences"
            size="small"
            multiline
            minRows={2}
            value={locationPreferences}
            onChange={(e) => setLocationPreferences(e.target.value)}
            placeholder="Remote US; open to SF hybrid 2×/month"
          />
          <ProfileMultiSelect
            label="Work arrangements"
            options={WORK_ARRANGEMENT_OPTIONS}
            selectedIds={workArrangements}
            onChange={setWorkArrangements}
            placeholder="Select arrangements"
          />
          <TextField
            label="Compensation expectations"
            size="small"
            value={compensation}
            onChange={(e) => setCompensation(e.target.value)}
            placeholder="$180k+ base, open to equity"
          />
          <ProfileMultiSelect
            label="Preferred company sizes"
            options={COMPANY_SIZE_OPTIONS}
            selectedIds={companySizes}
            onChange={setCompanySizes}
            placeholder="Select company sizes"
          />
          <TextField
            label="Availability notes"
            size="small"
            multiline
            minRows={2}
            value={availabilityNotes}
            onChange={(e) => setAvailabilityNotes(e.target.value)}
            placeholder="Prefer mornings; not available Fridays"
            helperText="Fallback when Calendar is not connected"
          />
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save profile"}
          </Button>
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
      <JobSeekerProfileSection />
      <HowItWorksSection />
    </Box>
  );
}
