# sm64.sql web playground

A static, zero-backend web UI for exploring the parsed database. The whole
SQLite file is loaded into your browser via [sql.js](https://sql.js.org)
(SQLite compiled to WebAssembly), so queries run entirely client-side — there is
no server, and nothing you type leaves the page.

## Run it locally

The database is **not** committed (it is generated, and `*.db` is gitignored).
Build it from a decomp checkout, then serve the folder:

```sh
# 1. Generate the database into this directory
sm64-sql -r /path/to/sm64 -d web/sm64.db -o

# 2. Serve it (any static server works; fetch() needs http, not file://)
cd web
python3 -m http.server 8000
# open http://localhost:8000
```

## Deployment

`.github/workflows/deploy.yml` rebuilds `sm64.db` from a fresh
`n64decomp/sm64` checkout and publishes this directory to GitHub Pages on every
push to `master`. Enable it once via **Settings → Pages → Source: GitHub
Actions**.

## Files

- `index.html` — page shell and tab layout
- `app.js` — loads sql.js + the database, runs queries, renders results/schema
- `examples.js` — the curated example queries shown in the sidebar
- `style.css` — styling
- `sm64.db` — the generated database (gitignored)
