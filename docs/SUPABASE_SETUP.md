# Supabase settings for JobTracker backend

Use these when running the backend (and worker) against a Supabase Postgres database.

## Where to get values in Supabase

1. **Dashboard**: [app.supabase.com](https://app.supabase.com) → your project.
2. **Project Settings** (gear) → **Database**.

## Database connection

| Setting | Where to get it | Notes |
|--------|------------------|--------|
| **Connection string** | Database → **Connection string** → **URI** | Copy the URI. |

- **Use "Direct" (Session) connection** for this app: the FastAPI server and RQ worker are long-lived, so the direct connection on port **5432** is appropriate.
- **SSL**: Supabase requires SSL. If the URI does not already include `?sslmode=require`, append it:
  - Example: `...postgres?sslmode=require`
- **Transaction pooler** (port 6543) is for serverless; you can use it with `?pgbouncer=true` in the URI if you later run the backend in a serverless environment.

## Backend environment variables (Supabase)

Set these in your backend environment (e.g. Render, Railway, or local `.env` when pointing at Supabase):

```bash
# From Supabase: Project Settings → Database → Connection string → URI (Direct).
# Add ?sslmode=require if not present.
DATABASE_URL=postgresql://postgres.[project-ref]:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:5432/postgres?sslmode=require

# Other backend vars (Redis, secrets, Google OAuth, etc.) — see backend/.env.example
REDIS_URL=redis://...
SECRET_KEY=...
APP_ENCRYPTION_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://your-backend-domain/email-accounts/gmail/oauth-callback
```

## After setting DATABASE_URL

1. Run migrations against the Supabase DB:
   ```bash
   cd backend
   source .venv/bin/activate   # or your env
   alembic upgrade head
   ```
2. Start the API and worker; they will use the same `DATABASE_URL`.

## Optional: Supabase connection pooling (Session mode)

If Supabase shows a **Session mode** pooler URL (port 5432), use that for both the web service and the worker. No extra settings are required beyond a valid `DATABASE_URL` with SSL.
