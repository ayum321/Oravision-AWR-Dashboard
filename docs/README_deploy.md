# OraVision AWR Pro — Deployment Guide

This guide covers deploying the Streamlit app to a **private GitHub repo + Streamlit Community Cloud** so testers access it via browser URL — no source code exposure.

---

## Project Layout

```
awr-dashboard/
├── app.py                          ← Streamlit entry point (this is what gets deployed)
├── requirements.txt                ← Streamlit-only dependencies
├── README_deploy.md
├── .streamlit/
│   ├── config.toml                 ← Dark theme + server settings
│   └── secrets.toml.template       ← Copy → secrets.toml (never commit)
└── backend/
    ├── services/
    │   ├── html_parser.py
    │   ├── comparator.py
    │   ├── rca_engine.py
    │   ├── health_scorer.py
    │   └── ...
    └── models/
        ├── snapshot.py
        ├── comparison.py
        └── ...
```

`app.py` auto-adds `backend/` to the Python path at runtime — no changes to existing service files needed.

---

## Step 1 — Set Up Credentials (Locally First)

```bash
# From awr-dashboard/ directory
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml`. Generate password hashes:

```python
import hashlib
print(hashlib.sha256("YourStrongPassword".encode()).hexdigest())
```

Paste each hash next to the username. Example:

```toml
[credentials.users]
admin   = "abc123...64-char-hash..."
tester1 = "def456...64-char-hash..."
```

**Never commit `secrets.toml` to git.**

---

## Step 2 — Test Locally

```bash
cd awr-dashboard
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501` — log in with a username/password from your secrets file.

---

## Step 3 — Push to a Private GitHub Repository

```bash
# Initialise git in awr-dashboard/ (if not already a repo)
cd awr-dashboard
git init
git remote add origin https://github.com/YOUR_ORG/awr-pro-private.git

# Add a .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
*.pyo
.env
.streamlit/secrets.toml
backend/__pycache__/
backend/**/__pycache__/
*.egg-info/
dist/
build/
EOF

git add .
git commit -m "Initial Streamlit deployment"
git push -u origin main
```

Verify that `.streamlit/secrets.toml` is NOT included (`git status` should not show it).

---

## Step 4 — Deploy on Streamlit Community Cloud

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **"New app"**.
3. Choose:
   - Repository: `YOUR_ORG/awr-pro-private`
   - Branch: `main`
   - Main file path: `app.py`
4. Click **"Advanced settings"** → **"Secrets"** tab.
5. Paste the entire contents of your `secrets.toml` (not the template) into the secrets box:
   ```toml
   [credentials.users]
   admin   = "your-64-char-sha256-hash"
   tester1 = "their-64-char-sha256-hash"
   ```
6. Click **"Deploy"**.

Streamlit Community Cloud will install `requirements.txt` and start the app. Build takes ~2 minutes.

---

## Step 5 — Share the URL With Testers

Once deployed, Streamlit gives you a URL like:

```
https://your-org-awr-pro-private-app-xxxx.streamlit.app
```

Share this URL with testers along with their username and password. They access the full dashboard in the browser — no source code, no installation.

**Each tester gets their own username/password.** To add or revoke access, update the secrets in the Streamlit Cloud dashboard and the app reloads automatically.

---

## Alternative Hosting Options

| Option | Cost | Notes |
|--------|------|-------|
| **Streamlit Community Cloud** | Free | Best for quick sharing. 1 private app on free tier. |
| **Railway.app** | ~$5/mo | `railway up` from repo root. Set env var `ORAVISION_USERS=admin:hash,tester1:hash`. |
| **Render.com** | Free/paid | Add `Procfile`: `web: streamlit run app.py --server.port $PORT`. |
| **AWS EC2 / VM** | Varies | `streamlit run app.py --server.address 0.0.0.0 --server.port 8501` behind nginx. |

### Environment Variable Auth (no secrets.toml)

For Railway/Render/EC2, set the env var instead of secrets.toml:

```
ORAVISION_USERS=admin:8c6976e5...hash...,tester1:2bb80d...hash...
```

Format: `username:sha256hash` pairs separated by commas.

---

## Managing Testers

### Add a tester
1. Generate hash: `python -c "import hashlib; print(hashlib.sha256('NewPass123'.encode()).hexdigest())"`
2. Add to Streamlit Cloud secrets: `newtester = "hash"`
3. Save — app reloads within 30 seconds.

### Remove a tester
Delete their line from secrets, save.

### Change a password
Replace the hash value in secrets.

---

## AWR File Upload Limits

By default Streamlit allows up to 200 MB per file (configured in `.streamlit/config.toml`). Oracle AWR HTML files are typically 1–15 MB so this is well within limits.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: services` | Ensure `backend/` folder is committed and `app.py` is run from `awr-dashboard/` |
| Login always fails | Check that secrets are saved in Streamlit Cloud settings (not just the template file) |
| Charts not rendering | `plotly` must be in `requirements.txt` — it is by default |
| Parse error on upload | Ensure AWR was generated as HTML (not text). Oracle 11g–21c formats are supported |
| App crashes on compare | Both files must be from the same Oracle version ideally; mixed 11g/19c may work but metrics may differ |
