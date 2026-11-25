# CampusConnect web application

This repository is Render-ready as a single Flask deployment: it serves the
CampusConnect frontend from `frontend/` at `/` and its API from `/api/*`.

## Local development

Run the service with:

```powershell
.\venv\Scripts\python.exe app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000). No separate frontend
server is required.

For the backend to access private tables, add the server-only project secret to
your local `.env` (do not expose or commit it):

```env
SUPABASE_SECRET_KEY=your_secret_key
```

`SUPABASE_SERVICE_ROLE_KEY` is also accepted for legacy projects. The existing
publishable key is used only as a fallback for tables deliberately exposed to
the anonymous Data API role.

## Deploy to Render

This repository includes a `render.yaml` blueprint. Create a new Render
Blueprint from the repository, then set these service environment variables in
Render:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=your_server_only_secret
```

Render installs the packages from `requirements.txt`, starts the service with
Gunicorn, and checks `GET /health` for service health. Do not add the Supabase
secret to source control.

The API is unauthenticated for now. Routes that need to know who is calling use
the temporary `X-User-Id` UUID header. The registration endpoint accepts the
same UUID as `user_id` in its JSON body. Replace both with verified identity
from real authentication before deploying.

The browser client is included in `frontend/` and calls relative API routes, so
it works unchanged locally and on Render. The API also allows cross-origin
requests for optional independent frontend development; in production set
`FRONTEND_ORIGIN` to an exact origin if you expose the API separately.

## Routes

| Method | Route | Request details |
| --- | --- | --- |
| GET | `/api/events` | Browse events. |
| GET | `/api/events/{id}` | Event details. |
| POST | `/api/registrations` | JSON: `{"event_id":"uuid","user_id":"uuid"}`. Returns `201` or `409`. |
| GET | `/api/me/registrations` | Requires `X-User-Id`. |
| GET | `/api/events/{id}/registrations` | Requires the organizer's `X-User-Id`. |

## Required database safeguards

This API checks for duplicate registrations and capacity, but concurrent
requests need database enforcement too. Add a unique constraint on
`registrations(event_id, user_id)` and move the capacity check plus insert into
a single transactional database function before serving concurrent traffic.
