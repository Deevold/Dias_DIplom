# Deploy on Render

## 1. Push the project to GitHub

The Render service will pull the repository from GitHub.

## 2. Create a Web Service

- Open Render
- Create `New +` -> `Blueprint`
- Select this repository
- Render will detect `render.yaml`

## 3. Set environment variables

You must provide:

- `DATABASE_URL`
- `GEMINI_API_KEY`

Optional:

- `GEMINI_MODEL=gemini-2.5-flash`

## 4. Important note about PostgreSQL

Your current local PostgreSQL database on your computer cannot be used directly from Render.
You need a cloud PostgreSQL database, for example:

- Render Postgres
- Neon
- Supabase

Then copy the cloud connection string into `DATABASE_URL`.

## 5. Start

Render will install dependencies and run:

```bash
gunicorn run:app
```

## 6. Local run

Local development still works with:

```bash
py run.py
```
