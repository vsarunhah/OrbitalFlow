import { useState } from "react";
import Link from "next/link";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import { requestForgotPassword } from "../lib/api";
import AuthLayout from "../components/AuthLayout";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    setSent(false);

    try {
      await requestForgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <AuthLayout
        title="Check your email"
        subtitle={
          <>
            If an account exists for <strong>{email}</strong>, we&apos;ve sent a
            link to reset your password. The link expires in 60 minutes.
          </>
        }
      >
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
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

  return (
    <AuthLayout
      title="Forgot password"
      subtitle="Enter your email and we'll send you a link to reset your password."
    >
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box component="form" onSubmit={handleSubmit} sx={{ display: "flex", flexDirection: "column", gap: 2.25 }}>
        <TextField
          id="email"
          label="Email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
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
          {submitting ? "Sending..." : "Send reset link"}
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
