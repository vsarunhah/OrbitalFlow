import { useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import { login, register, setToken, fetchMe } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const auth = useAuth();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      let data;
      if (mode === "login") {
        data = await login(email, password);
      } else {
        const autoTenant = email.split("@")[0] + "'s Job Search";
        data = await register(autoTenant, email, password);
      }

      setToken(data.access_token);
      const user = await fetchMe();
      if (auth) auth.setUser(user);
      router.replace("/jobs");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  const isLogin = mode === "login";

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        bgcolor: "background.default",
        p: 3,
      }}
    >
      <Paper
        elevation={0}
        sx={{
          width: "100%",
          maxWidth: 420,
          p: "40px 36px 32px",
          borderRadius: 2,
          border: 1,
          borderColor: "divider",
          bgcolor: "background.paper",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, mb: 3.5 }}>
          <Box
            component="svg"
            width={36}
            height={36}
            viewBox="0 0 36 36"
            fill="none"
            sx={{ flexShrink: 0 }}
          >
            <rect width="36" height="36" rx="8" fill="#6366f1" />
            <path
              d="M10 18l5 5 11-11"
              stroke="#fff"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </Box>
          <Typography variant="h6" fontWeight={700} letterSpacing="-0.3px">
            JobTracker
          </Typography>
        </Box>

        <Typography variant="h5" fontWeight={700} gutterBottom>
          {isLogin ? "Welcome back" : "Create your account"}
        </Typography>
        <Typography color="text.secondary" sx={{ mb: 3 }}>
          {isLogin
            ? "Sign in to your JobTracker account"
            : "Get started tracking your job applications"}
        </Typography>

        <Tabs
          value={mode}
          onChange={(_, v) => {
            setMode(v);
            setError(null);
          }}
          variant="fullWidth"
          sx={{
            mb: 3,
            borderRadius: 1,
            border: 1,
            borderColor: "divider",
            overflow: "hidden",
            "& .MuiTabs-indicator": { display: "none" },
            "& .MuiTabs-flexContainer": { gap: 0 },
          }}
        >
          <Tab
            label="Sign In"
            value="login"
            sx={{
              flex: 1,
              py: 1.25,
              fontSize: 13,
              fontWeight: 500,
              textTransform: "none",
              bgcolor: isLogin ? "primary.main" : "background.default",
              color: isLogin ? "white" : "text.secondary",
              "&.Mui-selected": { color: "white", bgcolor: "primary.main" },
            }}
          />
          <Tab
            label="Register"
            value="register"
            sx={{
              flex: 1,
              py: 1.25,
              fontSize: 13,
              fontWeight: 500,
              textTransform: "none",
              bgcolor: !isLogin ? "primary.main" : "background.default",
              color: !isLogin ? "white" : "text.secondary",
              "&.Mui-selected": { color: "white", bgcolor: "primary.main" },
            }}
          />
        </Tabs>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

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

          <Box>
            <TextField
              id="password"
              label="Password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              autoComplete={isLogin ? "current-password" : "new-password"}
              fullWidth
              size="small"
              variant="outlined"
            />
            {isLogin && (
              <Typography variant="body2" sx={{ mt: 0.75 }}>
                <Link
                  href="/forgot-password"
                  style={{ color: "var(--mui-palette-primary-main)", textDecoration: "none" }}
                >
                  Forgot password?
                </Link>
              </Typography>
            )}
          </Box>

          <Button
            type="submit"
            variant="contained"
            fullWidth
            disabled={submitting}
            sx={{ py: 1.5, mt: 0.5, fontWeight: 600, fontSize: 14 }}
          >
            {submitting
              ? "Please wait..."
              : isLogin
                ? "Sign In"
                : "Create Account"}
          </Button>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 2.5, textAlign: "center" }}>
          {isLogin ? "Don't have an account? " : "Already have an account? "}
          <Button
            component="button"
            variant="text"
            size="small"
            onClick={() => {
              setMode(isLogin ? "register" : "login");
              setError(null);
            }}
            sx={{
              color: "primary.main",
              fontSize: 13,
              textTransform: "none",
              textDecoration: "underline",
              p: 0,
              minWidth: "auto",
              "&:hover": { bgcolor: "transparent", textDecoration: "underline" },
            }}
          >
            {isLogin ? "Register" : "Sign in"}
          </Button>
        </Typography>
      </Paper>
    </Box>
  );
}
