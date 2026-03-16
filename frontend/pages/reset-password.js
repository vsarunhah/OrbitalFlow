import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import { resetPassword } from "../lib/api";
import AuthLayout from "../components/AuthLayout";

export default function ResetPasswordPage() {
  const router = useRouter();
  const { token } = router.query;
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (router.isReady) setReady(true);
  }, [router.isReady]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      return;
    }
    setSubmitting(true);
    try {
      await resetPassword(token, password);
      setSuccess(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (!ready) {
    return (
      <AuthLayout>
        <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", py: 4 }}>
          <CircularProgress size={24} sx={{ mr: 1 }} />
          <Typography color="text.secondary">Loading...</Typography>
        </Box>
      </AuthLayout>
    );
  }

  if (!token) {
    return (
      <AuthLayout
        title="Invalid link"
        subtitle="This reset link is invalid or missing. Request a new one from the sign-in page."
      >
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          <Link
            href="/forgot-password"
            style={{ color: "var(--mui-palette-primary-main)", textDecoration: "none", marginRight: 8 }}
          >
            Forgot password
          </Link>
          {" · "}
          <Link
            href="/login"
            style={{ color: "var(--mui-palette-primary-main)", textDecoration: "none" }}
          >
            Sign in
          </Link>
        </Typography>
      </AuthLayout>
    );
  }

  if (success) {
    return (
      <AuthLayout
        title="Password updated"
        subtitle="Your password has been reset. You can now sign in with your new password."
      >
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          <Link
            href="/login"
            style={{ color: "var(--mui-palette-primary-main)", textDecoration: "none" }}
          >
            Sign in
          </Link>
        </Typography>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Set new password"
      subtitle="Enter your new password below. It must be at least 6 characters."
    >
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", flexDirection: "column", gap: 2.25 }}>
        <TextField
          id="password"
          label="New password"
          type="password"
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={6}
          autoComplete="new-password"
          fullWidth
          size="small"
          variant="outlined"
        />
        <TextField
          id="confirm"
          label="Confirm password"
          type="password"
          placeholder="••••••••"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
          minLength={6}
          autoComplete="new-password"
          fullWidth
          size="small"
          variant="outlined"
        />
        <Button
          type="submit"
          variant="contained"
          fullWidth
          disabled={submitting}
          sx={{ py: 1.5, fontWeight: 600, fontSize: 14 }}
        >
          {submitting ? "Updating..." : "Update password"}
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mt: 2.5, textAlign: "center" }}>
        <Link
          href="/login"
          style={{ color: "var(--mui-palette-primary-main)", textDecoration: "none" }}
        >
          Back to sign in
        </Link>
      </Typography>
    </AuthLayout>
  );
}
