# Deploying the Salary Budget App with Docker

This deployment runs `app.py` as the only public entry point. Users must sign in with Google, and their email must be in the allowlist before the Streamlit pages are shown.

## 1. Create Google OAuth credentials

In Google Cloud Console, create an OAuth client for a web application.

Add the production redirect URI:

```text
https://YOUR_DOMAIN/oauth2callback
```

For local testing, also add:

```text
http://localhost:8501/oauth2callback
```

Copy the Google client ID and client secret.

## 2. Create Streamlit secrets

Copy the example file:

```bash
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`:

- `redirect_uri` must exactly match the Google Cloud authorized redirect URI.
- `cookie_secret` must be a long random string.
- `client_id` and `client_secret` come from Google Cloud.
- `allowed_emails` is the whitelist of accounts that may use the app.

You can also set the whitelist with an environment variable:

```bash
ALLOWED_EMAILS="person1@gmail.com,person2@buu.ac.th"
```

The app combines both sources.

## 3. Provide the confidential data

The container expects these files in `/app/data`:

- `new_salary_table.parquet`
- `salary_all_checked_posid.parquet`

With Docker Compose, point `SALARY_DATA_DIR` to the server directory that contains those files.

## 4. Start the app

From `budget_analysis/`:

```bash
SALARY_DATA_DIR=/srv/buu-salary-data \
STREAMLIT_SECRETS_FILE=/srv/buu-salary-secrets/secrets.toml \
STREAMLIT_PORT=8501 \
docker compose up -d --build
```

The app listens on port `8501` by default.

## 5. Reverse proxy

Put Nginx, Caddy, Traefik, or another TLS reverse proxy in front of the container. The public app URL must match the `redirect_uri` base exactly, including scheme and host.

Example:

```text
https://salary.example.edu/oauth2callback
```

## 6. Operational notes

- Do not commit `.streamlit/secrets.toml`.
- Do not bake payroll parquet files into the image.
- To change the allowlist, edit the secrets file or `ALLOWED_EMAILS`, then restart the container.
- If Google returns a redirect mismatch error, the `redirect_uri` in Streamlit secrets does not exactly match the Google Cloud authorized redirect URI.
