# Feature: Analytics Funnel

## Overview

Provide a dashboard showing application/job search metrics derived from existing jobs, job_events, job_stage_history, and messages. All calculations are deterministic and based on tenant-scoped data. No new domain concepts; we only aggregate and expose metrics already implied by the current schema.

**Source of truth:** `jobs`, `job_events`, `job_stage_history` (and optionally `messages` for response-time semantics if needed). No schema changes required for v1.

---

## Metrics Definitions

### Counts (distinct jobs unless noted)

| Metric | Definition | How computed |
|--------|------------|--------------|
| **Total active jobs** | All jobs for the tenant (tracked jobs). | `COUNT(*) FROM jobs WHERE tenant_id = ?` |
| **Count by current stage** | Number of jobs in each stage (SOURCED, APPLIED, …). | `GROUP BY current_stage` on `jobs` |
| **Applications received** | Number of jobs that have at least one APPLICATION_RECEIVED event. | Distinct `job_id` from `job_events` where `event_type = 'APPLICATION_RECEIVED'` |
| **Interviews detected** | Number of jobs that have at least one interview-type event. | Distinct `job_id` from `job_events` where `event_type IN ('INTERVIEW_REQUEST','INTERVIEW_SCHEDULED','INTERVIEW_RESCHEDULE')` |
| **Offers** | Number of jobs that have at least one OFFER event (or current_stage = OFFER). | Distinct `job_id` from `job_events` where `event_type = 'OFFER'`, union jobs with `current_stage = 'OFFER'` (in case only manual/history) |
| **Rejections** | Number of jobs in REJECTED stage. | `COUNT(*) FROM jobs WHERE tenant_id = ? AND current_stage = 'REJECTED'` (single source: current state) |

### Conversion rates

| Metric | Definition | Formula |
|--------|------------|---------|
| **Application → Interview** | Share of jobs that applied and later had an interview. | `(jobs with ≥1 INTERVIEW_* event) / (jobs with ≥1 APPLICATION_RECEIVED event)`, 0 if denominator 0. |
| **Interview → Offer** | Share of jobs that had an interview and later got an offer. | `(jobs with OFFER event or current_stage OFFER) / (jobs with ≥1 INTERVIEW_* event)`, 0 if denominator 0. |

### Response times

| Metric | Definition | How computed |
|--------|------------|--------------|
| **Avg days applied → first interview** | Average number of days from first APPLICATION_RECEIVED to first INTERVIEW_* event per job. | For each job with both: min(created_at) for APPLICATION_RECEIVED, min(created_at) for INTERVIEW_*; take diff in days; average. Exclude jobs missing either. |

### Time series and activity

| Metric | Definition | How computed |
|--------|------------|--------------|
| **Jobs created over time** | Count of jobs created per time bucket (e.g. per day). | `DATE(created_at)` (or truncate to day) GROUP BY day, COUNT(*). |
| **Recent activity (7d / 30d)** | Count of “activity” events in the last 7 and 30 days. | Count of `job_events` rows where `created_at` in last 7d and last 30d (two numbers). |

**Incomplete data:**  
- Conversion rates: only jobs that have the qualifying events are considered; no imputation.  
- Avg days applied→interview: only jobs that have both APPLICATION_RECEIVED and an INTERVIEW_* event; others excluded.  
- Rejections: we use current_stage only (no “ever rejected” from history) so that merged/reopened jobs are not double-counted.

**Double-counting avoidance:**  
- “Applications received” = distinct jobs with ≥1 APPLICATION_RECEIVED event (one count per job).  
- “Interviews detected” = distinct jobs with ≥1 INTERVIEW_* event.  
- “Offers” = distinct jobs with OFFER event or current_stage OFFER.  
- All time-series and activity counts use raw event counts (job_events rows) for “activity”; funnel counts use distinct jobs.

---

## Backend Aggregation Approach

- **Engine:** Postgres only; no caches or background materialized tables for v1.  
- **Scoping:** Every query filters by `tenant_id` from the authenticated user.  
- **Queries:**  
  - Summary: 1 query for total jobs; 1 for counts by stage; 1–2 for application/interview/offer/rejection counts (subqueries or CTEs for distinct job sets); 1 for conversion rates from those sets; 1 for avg days (filter jobs with both event types, compute per-job min timestamps, then average days).  
  - Funnel: Same distinct-job counts by “milestone” (applied, interview, offer, rejected) plus counts by current_stage.  
  - Timeseries: `DATE(created_at)` on `jobs` (and optionally `job_events` for activity) with `WHERE created_at >= ?` and `GROUP BY date`.  
- **Determinism:** Same inputs (same tenant data) always produce same outputs. No sampling or non-deterministic functions.

---

## API Design

Base path: `/analytics`. All endpoints require auth; tenant from JWT.

| Method | Path | Description |
|--------|------|--------------|
| GET | `/analytics/summary` | One-shot summary: total jobs, by stage, applications, interviews, offers, rejections, conversion rates, avg days applied→interview, recent activity 7d/30d. |
| GET | `/analytics/funnel` | Funnel breakdown: counts at each milestone (applied, interview, offer, rejected) and optionally by current_stage. |
| GET | `/analytics/timeseries?window=7d\|30d\|90d` | Time series: jobs created per day; optional: activity count per day. `window` defaults to 30d. |

Response shapes (conceptual):

**GET /analytics/summary**

```json
{
  "total_jobs": 42,
  "by_stage": { "SOURCED": 5, "APPLIED": 10, "INTERVIEW": 8, "OFFER": 2, "REJECTED": 17 },
  "applications_received": 35,
  "interviews_detected": 12,
  "offers": 2,
  "rejections": 17,
  "conversion_application_to_interview": 0.34,
  "conversion_interview_to_offer": 0.17,
  "avg_days_applied_to_first_interview": 5.2,
  "recent_activity_7d": 14,
  "recent_activity_30d": 48
}
```

**GET /analytics/funnel**

```json
{
  "milestones": {
    "applied": 35,
    "interview": 12,
    "offer": 2,
    "rejected": 17
  },
  "by_stage": { "SOURCED": 5, "APPLIED": 10, ... }
}
```

**GET /analytics/timeseries?window=30d**

```json
{
  "window": "30d",
  "jobs_created": [ { "date": "2026-03-01", "count": 3 }, ... ],
  "activity": [ { "date": "2026-03-01", "count": 7 }, ... ]
}
```

---

## Frontend Page Design

- **Route:** `/analytics` (new page).  
- **Layout:** Same app shell (AuthLayout + NavBar). Add “Analytics” to NavBar.  
- **Sections:**  
  1. **Summary cards:** Total jobs, applications received, interviews, offers, rejections, conversion rates (application→interview, interview→offer), avg days applied→first interview, recent activity 7d/30d.  
  2. **Funnel:** Horizontal or vertical breakdown (e.g. Applied → Interview → Offer, with Rejected shown separately). Use same stage colors as Jobs page where applicable.  
  3. **Trend chart:** At least one time series — e.g. “Jobs created over time” (and optionally “Activity over time”) for the selected window (7d/30d/90d). Minimal chart (e.g. bar or line).  
- **Design:** Clean, minimal, consistent with existing app (MUI, existing theme, no new dependencies if possible; use MUI or simple SVG/CSS for chart).  
- **Loading/errors:** Show loading state and error message like other pages.

---

## Assumptions and Caveats

- **Tenant isolation:** All metrics are per tenant; no cross-tenant data.  
- **No schema change:** v1 uses only existing tables.  
- **Current stage for rejections:** We use `jobs.current_stage = 'REJECTED'` for rejection count, not “ever had REJECTION event,” to avoid double-counting after merges or manual stage changes.  
- **First interview:** “First interview” = chronologically first INTERVIEW_* event (by `created_at`) for that job.  
- **Time zones:** Stored timestamps are UTC; date bucketing for timeseries is in UTC. Frontend may display in local time.  
- **Empty state:** If no jobs or no events, rates are 0; avg days is null or omitted; arrays are empty.

---

## Testing Plan

1. **Unit tests (backend)**  
   - Fixture: Create tenant, jobs, job_events (various event_types and created_at).  
   - Assert: total_jobs, by_stage, applications_received, interviews_detected, offers, rejections match definitions.  
   - Assert: conversion_application_to_interview and conversion_interview_to_offer for known denominators.  
   - Assert: avg_days_applied_to_first_interview for jobs with both APPLICATION_RECEIVED and INTERVIEW_* events.  
   - Assert: recent_activity_7d / 30d from job_events in last 7/30 days.  
   - Assert: timeseries returns correct buckets and counts for jobs created and activity.  
   - Assert: tenant isolation (other tenant’s data not included).  

2. **API tests**  
   - GET /analytics/summary, /analytics/funnel, /analytics/timeseries return 200 and expected shape when authenticated.  
   - Unauthenticated or wrong tenant: 401/403 as per existing auth.  

3. **Frontend (manual or E2E)**  
   - Analytics page loads; summary cards and funnel render; trend chart shows for 7d/30d/90d.  
   - No console errors; design consistent with Jobs/Settings.

---

## Implementation Checklist

- [x] Backend: analytics schemas (Pydantic models for summary, funnel, timeseries).  
- [x] Backend: analytics router with GET /summary, GET /funnel, GET /timeseries.  
- [x] Backend: aggregation logic (deterministic, tenant-scoped).  
- [x] Frontend: API client for /analytics/*.  
- [x] Frontend: Analytics page (summary cards, funnel, one trend chart).  
- [x] Frontend: NavBar link to /analytics.  
- [x] Tests: metric calculation tests; API tests.  
- [x] No migrations (v1: none).

---

## Metric Definitions Implemented (v1)

| Metric | Definition (implemented) |
|--------|--------------------------|
| **Total active jobs** | `COUNT(*)` from `jobs` for tenant. |
| **Count by current stage** | `GROUP BY current_stage` on `jobs` for tenant. |
| **Applications received** | Distinct `job_id` count from `job_events` where `event_type = 'APPLICATION_RECEIVED'`. |
| **Interviews detected** | Distinct `job_id` count from `job_events` where `event_type IN ('INTERVIEW_REQUEST','INTERVIEW_SCHEDULED','INTERVIEW_RESCHEDULE')`. |
| **Offers** | Distinct jobs that have at least one `job_events` row with `event_type = 'OFFER'` **or** `jobs.current_stage = 'OFFER'`. |
| **Rejections** | `COUNT(*)` from `jobs` where `current_stage = 'REJECTED'`. |
| **Application → Interview conversion** | `interviews_detected / applications_received` (0 if no applications). |
| **Interview → Offer conversion** | `offers / interviews_detected` (0 if no interviews). |
| **Avg days applied → first interview** | Per job: min(created_at) for APPLICATION_RECEIVED, min(created_at) for INTERVIEW_*; days between; average over jobs that have both. Null if none. |
| **Recent activity 7d / 30d** | Count of `job_events` rows where `created_at` in last 7 and 30 days. |
| **Jobs created over time** | Jobs with `created_at >= window_start`, grouped by date (YYYY-MM-DD) in Python. |
| **Activity over time** | Job events with `created_at >= window_start`, grouped by date in Python. |
