import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

const Logo = () => (
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
);

export default function AuthLayout({ children, title, subtitle }) {
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
        <Logo />
        {title && (
          <Typography variant="h5" fontWeight={700} gutterBottom>
            {title}
          </Typography>
        )}
        {subtitle && (
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            {subtitle}
          </Typography>
        )}
        {children}
      </Paper>
    </Box>
  );
}

export { Logo };
