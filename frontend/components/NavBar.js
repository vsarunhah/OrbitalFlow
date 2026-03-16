import Link from "next/link";
import { useRouter } from "next/router";
import AppBar from "@mui/material/AppBar";
import Toolbar from "@mui/material/Toolbar";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";

const NAV_ITEMS = [
  { href: "/jobs", label: "Jobs" },
  { href: "/resumes", label: "Resumes" },
  { href: "/analytics", label: "Analytics" },
  { href: "/alerts", label: "Alerts" },
  { href: "/recruiters", label: "Recruiters" },
  { href: "/settings", label: "Settings" },
];

export default function NavBar() {
  const router = useRouter();

  return (
    <AppBar
      position="static"
      elevation={0}
      sx={{
        backgroundColor: "background.paper",
        borderBottom: 1,
        borderColor: "divider",
        flexShrink: 0,
      }}
    >
      <Toolbar
        variant="dense"
        sx={{
          maxWidth: 1200,
          margin: "0 auto",
          width: "100%",
          minHeight: { xs: 48 },
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          {NAV_ITEMS.map(({ href, label }) => {
            const isActive = router.pathname === href;
            return (
              <Button
                key={href}
                component={Link}
                href={href}
                variant={isActive ? "contained" : "text"}
                color="primary"
                size="small"
                sx={{
                  textTransform: "none",
                  fontWeight: 500,
                  fontSize: 14,
                  ...(isActive
                    ? {
                        backgroundColor: "rgba(99, 102, 241, 0.2)",
                        color: "primary.main",
                        "&:hover": {
                          backgroundColor: "rgba(99, 102, 241, 0.25)",
                        },
                      }
                    : {
                        color: "text.secondary",
                        "&:hover": {
                          color: "text.primary",
                          backgroundColor: "action.hover",
                        },
                      }),
                }}
              >
                {label}
              </Button>
            );
          })}
        </Box>
      </Toolbar>
    </AppBar>
  );
}
