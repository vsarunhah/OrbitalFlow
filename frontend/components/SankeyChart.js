"use client";

import { useMemo } from "react";
import { ResponsiveSankey } from "@nivo/sankey";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

const ENTRY_NODE = "Sourced + Applied";

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
  [ENTRY_NODE]: "#5b6b7c",
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

const STAGE_DEPTH = {};
STAGE_ORDER.forEach((s, i) => {
  STAGE_DEPTH[s] = i;
});

function normalizeStage(stage) {
  return stage === "SOURCED" || stage === "APPLIED" ? ENTRY_NODE : stage;
}

function formatStageLabel(id) {
  if (id === ENTRY_NODE) return id;
  if (!id || typeof id !== "string") return id;
  return id.charAt(0).toUpperCase() + id.slice(1).toLowerCase();
}

function buildSankeyData(flows) {
  if (!flows || flows.length === 0) {
    return { nodes: [], links: [] };
  }
  const depth = (name) => {
    if (name === ENTRY_NODE) return -1;
    return name in STAGE_DEPTH ? STAGE_DEPTH[name] : 999;
  };
  const isTerminal = (name) => name === "REJECTED" || name === "WITHDRAWN";
  const acyclicFlows = flows.filter((f) => {
    if (isTerminal(f.to_stage)) return true;
    return depth(f.to_stage) > depth(f.from_stage);
  });
  if (acyclicFlows.length === 0) {
    return { nodes: [], links: [] };
  }
  const linkKey = (a, b) => `${a}\t${b}`;
  const aggregated = new Map();
  acyclicFlows.forEach((f) => {
    const from = normalizeStage(f.from_stage);
    const to = normalizeStage(f.to_stage);
    const key = linkKey(from, to);
    aggregated.set(key, (aggregated.get(key) || 0) + (f.value ?? 0));
  });
  const nodeSet = new Set();
  aggregated.forEach((_, key) => {
    const [from, to] = key.split("\t");
    nodeSet.add(from);
    nodeSet.add(to);
  });
  const orderWithoutEntry = STAGE_ORDER.filter((s) => s !== "SOURCED" && s !== "APPLIED");
  const ordered = nodeSet.has(ENTRY_NODE)
    ? [ENTRY_NODE, ...orderWithoutEntry.filter((s) => nodeSet.has(s))]
    : orderWithoutEntry.filter((s) => nodeSet.has(s));
  nodeSet.forEach((n) => {
    if (!ordered.includes(n)) ordered.push(n);
  });
  const nodes = ordered.map((name) => ({ id: name }));
  const nodeIndex = Object.fromEntries(ordered.map((name, i) => [name, i]));
  const links = [];
  aggregated.forEach((value, key) => {
    const numValue = Number(value) || 0;
    if (numValue <= 0) return;
    const [from, to] = key.split("\t");
    const iFrom = nodeIndex[from] ?? -1;
    const iTo = nodeIndex[to] ?? -1;
    if (iFrom >= iTo) return;
    links.push({ source: from, target: to, value: numValue });
  });
  return { nodes, links };
}

export function SankeyChart({ flows }) {
  const data = useMemo(() => buildSankeyData(flows), [flows]);

  if (!flows?.length || !data.nodes.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
        No stage transitions yet. Flow appears when jobs move between stages.
      </Typography>
    );
  }

  return (
    <Box sx={{ width: "100%", minWidth: 400, height: 340 }}>
      <ResponsiveSankey
        data={data}
        margin={{ top: 16, right: 140, bottom: 16, left: 140 }}
        align="justify"
        colors={(node) => STAGE_COLORS[node.id] || "#6b7280"}
        nodeOpacity={0.9}
        nodeThickness={14}
        nodeSpacing={16}
        nodeBorderWidth={0}
        nodeBorderRadius={2}
        linkOpacity={0.5}
        linkContract={0}
        enableLinkGradient={false}
        enableLabels={true}
        label={(node) => formatStageLabel(node.id)}
        labelPosition="outside"
        labelPadding={8}
        labelTextColor="#e4e6ed"
        theme={{
          text: { fill: "#e4e6ed", fontSize: 12 },
        }}
      />
    </Box>
  );
}
