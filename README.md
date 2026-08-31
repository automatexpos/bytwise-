# Bytwise (Python and FastAPI rewrite)

"Bytwise" is a cozy cafe and hidden gem discovery app: browse a map of coffee
shops and cafes, save and visit spots, vote on vibe tags, leave reviews,
claim a business, and moderate content as an admin.

This project is a Python (FastAPI plus Jinja2) rewrite of the original
TypeScript and React project (`dripmap`). It uses the same Supabase schema
as the original app (see `database/*.sql` for the table definitions), the
same Cloudinary account for image storage, and the same Gemini API for
AI generated shop descriptions. There is no build step, no React, and no
client side framework: pages are rendered server side with Jinja2
templates, and a small amount of vanilla JavaScript (`app/static/js/app.js`)
handles the Leaflet map, toasts, and AJAX calls for interactive actions
like saving a shop or voting on a vibe.

## Setup

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   On Windows, activate with `venv\Scripts\activate` instead.

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` and set:

   - `SUPABASE_URL` and `SUPABASE_ANON_KEY` (from your Supabase project
     settings, API section). The `VITE_SUPABASE_URL` and
     `VITE_SUPABASE_ANON_KEY` names from the original `.env` file are also
     accepted, if you already have one from the TypeScript project.
   - `GEMINI_API_KEY` (optional, used for the "Generate with AI" shop
     description button on the Add Spot and Edit Shop pages). Without it,
     the app falls back to a simple templated description.
   - `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and
     `CLOUDINARY_API_SECRET` (from your Cloudinary dashboard, used for
     signed server side image uploads and admin deletes).

4. Make sure your Supabase project has the schema this app expects. The
   SQL files under `database/` (starting with `Supabase_project.sql`, then
   the numbered follow up migrations) define the `profiles`, `shops`,
   `shop_images`, `vibe_votes`, `reviews`, `saved_shops`, `visited_shops`,
   `user_follows`, and `claim_requests` tables, along with their Row Level
   Security policies. Run these against your Supabase project if you have
   not already.

5. Run the development server:

   ```bash
   uvicorn app.main:app --reload
   ```

   Then open `http://127.0.0.1:8000/` in your browser.

## Deploying on Vercel

This repo is set up to deploy on Vercel as is.

1. In the Vercel dashboard, choose Import Project and select this repo
   (`bytwise`). Vercel now has zero configuration support for FastAPI: it
   reads `requirements.txt`, finds the `FastAPI` instance named `app` in
   `app/main.py`, and routes every request (`/`, `/shop/{id}`,
   `/static/...`, and so on) straight to it. No `vercel.json` and no
   `api/` folder are needed, so this repo does not ship either.
2. Before the first deploy, add these environment variables in the
   project's Settings, Environment Variables (same values as your local
   `.env`): `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `GEMINI_API_KEY`,
   `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`.
   The chatbot backend's URL is not an environment variable, see
   "Restaurant chatbot widget" below.
3. Deploy. The app has no local file writes and no background jobs, so it
   fits Vercel's read only, request scoped serverless model without
   changes. Image uploads go straight to Cloudinary, and all state lives
   in Supabase, not on disk.
4. If you use Supabase Auth's email redirect links, add your Vercel
   deployment URL to the Supabase project's Auth, URL Configuration,
   Redirect URLs list, the same way you would for any other host.

Note: this app renders full HTML pages and only serves plain JSON from a
small set of `/api/*` endpoints for interactive actions (vibe voting,
save and visit toggles, and so on). It is not a Next.js API project, so
there is no separate frontend to deploy, the same Python app serves both
the pages and those JSON endpoints.

## Restaurant chatbot widget

The bottom right chat launcher on every page comes from a separate
service: a Flask app that talks to a local Ollama model, running on the
developer's own machine and exposed through a Cloudflare Tunnel (see the
`restaurant-ai` backend project). This repo only needs to know where that
service currently is, and that address changes every time the tunnel
restarts, so it is not read from a fixed environment variable anymore.

- The tunnel URL is written into a single Supabase table,
  `cloudflare_url` (columns: `id`, `url`, `created_at`), whenever the
  Cloudflare tunnel starts. That part is handled outside this repo.
- `app/chatbot_config.py` reads the most recent row from that table with
  the anonymous Supabase client, cached for 30 seconds so a normal page
  view does not cost a Supabase round trip. On any read error it falls
  back to the last URL it fetched successfully instead of hiding the
  widget over a brief hiccup.
- `app/routers/pages.py` exposes `get_chatbot_api_url` to every template
  as a Jinja2 global, so no individual route needs to pass it along.
- `app/templates/base.html` calls that function once per render and only
  renders the launcher, chat panel, and `app/static/js/chatbot.js` when
  it returns a non empty URL, so the widget stays hidden until the table
  has a row.
- `app/static/js/chatbot.js` calls `{that URL}/chat` and `{that URL}/reset`
  on the Flask backend, matching the request and response shapes
  documented in that repo.

**Row Level Security:** the `cloudflare_url` table needs a policy that
allows `SELECT` for the `anon` role, since page renders happen for
logged out visitors too. Without it every read fails silently and the
widget just stays hidden.

**Local development and production both work the same way:** run Ollama,
then the Flask backend, then start
`cloudflared tunnel --url http://localhost:8000` and write the quick
tunnel URL it prints into a new row in the `cloudflare_url` table (the
tooling that does this already exists outside this repo). Also set
`CORS_ORIGINS` in the Flask backend's own `.env` to the origin this app is
served from (e.g. `http://localhost:8000` locally, or your Vercel domain
in production) so the browser is allowed to call it. No Vercel
environment variable or redeploy is needed when the tunnel restarts,
since the next page view just reads the new row.

## Project layout

- `app/config.py`, `app/models.py`, `app/constants.py`, `app/database.py`,
  `app/security.py`, `app/services/` : the backend core (Supabase client,
  Pydantic models, authentication, and the database/storage/Gemini service
  functions). These were ported first and are documented in
  `BACKEND_CORE_NOTES.md`.
- `app/routers/pages.py` : server rendered HTML page routes (home, shop
  detail, add spot, edit shop, auth, profile, claim shop, admin dashboard).
- `app/routers/api.py` : small JSON endpoints used by page JavaScript for
  actions that should not reload the page (vibe voting, save and visit
  toggles, follow, admin moderation, and the shop list feeding the map).
- `app/templates/` : Jinja2 templates, one per page, plus a shared
  `base.html` layout and small reusable includes under
  `app/templates/components/`.
- `app/static/css/style.css` : the stylesheet (a warm, cozy cafe aesthetic
  with a single accent color and rounded cards).
- `app/static/js/app.js` : vanilla JavaScript for the Leaflet map, toast
  notifications, AJAX calls to the JSON endpoints, and client side form
  validation. No build step and no framework.
- `app/main.py` : creates the FastAPI application, mounts the static
  files, configures Jinja2 templates, includes both routers, and warns
  (without crashing) on startup if Supabase, Cloudinary, or Gemini
  environment variables are missing.

## Notes on the rewrite

- The original project used React Router with hash based routing
  (`HashRouter`). This rewrite uses standard FastAPI path routing instead
  (for example `/shop/{shop_id}` instead of `/#/shop/:id`).
  Business logic that lived in `context/AppContext.tsx` in the original
  project (fetching shops, computing vibe ratings, generating deterministic
  fake community members, computing drip score and badges) has been moved
  to the route handlers in `app/routers/pages.py`, since there is no
  client side context in a server rendered app.
- Image uploads are handled server side with a signed Cloudinary upload
  (see `app/services/storage_service.py`), rather than the original's
  browser side unsigned upload preset. This means the Cloudinary API
  secret only ever lives on the server.
- Every database call runs through a request scoped, user authenticated
  Supabase client (the anon key plus the user's access token from the
  `sb_access_token` httponly cookie), so Row Level Security policies apply
  exactly as they did in the original browser based app. A service role
  key is never used.
#   b y t w i s e - 
 
 