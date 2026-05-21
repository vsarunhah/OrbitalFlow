import { useState } from "react";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import IconButton from "@mui/material/IconButton";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemText from "@mui/material/ListItemText";
import FormControlLabel from "@mui/material/FormControlLabel";
import Checkbox from "@mui/material/Checkbox";
import Typography from "@mui/material/Typography";
import SearchIcon from "@mui/icons-material/Search";
import CloseIcon from "@mui/icons-material/Close";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import MergeTypeIcon from "@mui/icons-material/MergeType";
import TipsAndUpdatesIcon from "@mui/icons-material/TipsAndUpdates";
import KeyboardIcon from "@mui/icons-material/Keyboard";
import ViewAgendaIcon from "@mui/icons-material/ViewAgenda";
import ViewDayIcon from "@mui/icons-material/ViewDay";

/**
 * Single-line toolbar: search input + view toggle + overflow.
 *
 * `view` is a tri-state: "needs" | "awaiting" | "all" (inbox-style segments).
 * `unreadOnly` toggles the server `unread_only` list: jobs with new inbound
 * email since the last time you opened that job's timeline.
 */
export default function JobListToolbar({
  searchValue,
  onSearchChange,
  searchInputRef,
  view,
  onViewChange,
  unreadOnly,
  onUnreadOnlyChange,
  compact,
  onCompactChange,
  onEnterMergeMode,
  onSuggestMerges,
  onShowShortcuts,
}) {
  const [menuAnchor, setMenuAnchor] = useState(null);
  const open = Boolean(menuAnchor);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1, px: 2, pt: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <TextField
          inputRef={searchInputRef}
          size="small"
          fullWidth
          placeholder="Search jobs, emails…   ( / )"
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" sx={{ color: "text.secondary" }} />
              </InputAdornment>
            ),
            endAdornment: searchValue ? (
              <InputAdornment position="end">
                <IconButton
                  size="small"
                  aria-label="Clear search"
                  onClick={() => onSearchChange("")}
                  edge="end"
                >
                  <CloseIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ) : null,
          }}
        />
        <IconButton
          size="small"
          aria-label="More options"
          onClick={(e) => setMenuAnchor(e.currentTarget)}
        >
          <MoreVertIcon fontSize="small" />
        </IconButton>
        <Menu
          anchorEl={menuAnchor}
          open={open}
          onClose={() => setMenuAnchor(null)}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          transformOrigin={{ vertical: "top", horizontal: "right" }}
        >
          <MenuItem
            onClick={() => {
              onCompactChange(!compact);
            }}
          >
            <Checkbox checked={compact} size="small" sx={{ mr: 1, p: 0 }} />
            {compact ? <ViewDayIcon fontSize="small" sx={{ mr: 1 }} /> : <ViewAgendaIcon fontSize="small" sx={{ mr: 1 }} />}
            <ListItemText primary="Compact list" />
          </MenuItem>
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onSuggestMerges?.();
            }}
          >
            <TipsAndUpdatesIcon fontSize="small" sx={{ mr: 1 }} />
            <ListItemText primary="Suggest merges…" />
          </MenuItem>
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onEnterMergeMode?.();
            }}
          >
            <MergeTypeIcon fontSize="small" sx={{ mr: 1 }} />
            <ListItemText primary="Merge duplicates…" />
          </MenuItem>
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onShowShortcuts?.();
            }}
          >
            <KeyboardIcon fontSize="small" sx={{ mr: 1 }} />
            <ListItemText primary="Keyboard shortcuts" />
            <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>
              ?
            </Typography>
          </MenuItem>
        </Menu>
      </Box>
      <ToggleButtonGroup
        exclusive
        size="small"
        value={view}
        onChange={(_, v) => v && onViewChange(v)}
        sx={{
          "& .MuiToggleButton-root": {
            textTransform: "none",
            fontSize: 12,
            fontWeight: 600,
            border: 0,
            px: 1.25,
            py: 0.25,
            color: "text.secondary",
            "&.Mui-selected": {
              bgcolor: "action.selected",
              color: "text.primary",
            },
          },
        }}
      >
        <ToggleButton value="needs">Needs reply</ToggleButton>
        <ToggleButton value="awaiting">Awaiting</ToggleButton>
        <ToggleButton value="all">All</ToggleButton>
      </ToggleButtonGroup>
      <FormControlLabel
        control={
          <Checkbox
            size="small"
            checked={!!unreadOnly}
            onChange={(e) => onUnreadOnlyChange?.(e.target.checked)}
          />
        }
        label="New / unread only"
        sx={{
          m: 0,
          pl: 0.25,
          userSelect: "none",
          "& .MuiFormControlLabel-label": { fontSize: 12, fontWeight: 500 },
        }}
      />
    </Box>
  );
}
