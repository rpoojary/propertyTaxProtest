# Deploy to GoDaddy cPanel

## Prerequisites
- GoDaddy hosting plan with **cPanel** and **Python support** (Business or higher)
- SSH access or File Manager access

## Option A: cPanel Python App (Recommended)

### 1. Create Python App in cPanel
- Log into cPanel → **Setup Python App**
- Python version: **3.11** (or latest available)
- Application root: `protest`
- Application URL: `yourdomain.com/protest` (or a subdomain)
- Application startup file: `passenger_wsgi.py`
- Click **Create**

### 2. Upload Files
Upload these files to `/home/YOUR_USER/protest/`:
```
protest/
├── app.py
├── passenger_wsgi.py
├── requirements.txt
├── dcad_lite.db          (333 MB — use SFTP, not File Manager)
└── static/
    └── index.html
```

**Important:** Upload `dcad_lite.db` via **SFTP** (FileZilla, Cyberduck). 
File Manager has upload size limits.

### 3. Install Dependencies
In cPanel Python App panel, click **Run pip install** or SSH in:
```bash
source /home/YOUR_USER/virtualenv/protest/3.11/bin/activate
pip install flask
```

### 4. Restart
Click **Restart** in the Python App panel.

### 5. Test
Visit `https://yourdomain.com/protest/`

---

## Option B: If No Python Support

If your GoDaddy plan doesn't support Python apps, deploy on **Render.com** instead (free tier):

1. Push `webapp/` to a GitHub repo
2. Go to render.com → New Web Service → Connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Upload `dcad_lite.db` via Render's persistent disk

---

## Files Summary

| File | Purpose |
|---|---|
| `app.py` | Flask application (API + static serving) |
| `passenger_wsgi.py` | WSGI entry point for cPanel/Passenger |
| `requirements.txt` | Python dependencies |
| `dcad_lite.db` | Trimmed DCAD database (333 MB) |
| `static/index.html` | Frontend (single page app) |
| `.htaccess` | Apache/Passenger config (edit paths first!) |

## SFTP Credentials
- Host: your GoDaddy server IP or hostname
- Username: your cPanel username
- Password: your cPanel password
- Port: 22
