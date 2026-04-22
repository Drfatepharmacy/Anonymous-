# Deploying AnonVibe to Render

Follow these steps to deploy your professional anonymous chat honeypot.

### 1. Create a PostgreSQL Database on Render
1. Log in to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** and select **PostgreSQL**.
3. Name it `anonvibe-db` and choose a region close to you.
4. Select the **Free** tier (or higher for production).
5. Click **Create Database**.
6. Once created, copy the **Internal Database URL** (for Render services) or the **External Database URL** (for local testing).

### 2. Deploy the Web Service
1. Click **New +** and select **Web Service**.
2. Connect your GitHub repository.
3. **Settings:**
   - **Name:** `anonvibe-chat`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --worker-class eventlet -w 1 app:app` (This matches the `Procfile` already in the repo).
4. **Environment Variables:**
   Click **Advanced** and add the following variables:
   - `DATABASE_URL`: Paste your **Internal Database URL** from Step 1.
   - `SECRET_KEY`: Enter a long random string for session security.
   - `ADMIN_PASSWORD`: Enter the password you want to use for the `/admin` portal (default is `admin123` if not set).
   - `PYTHON_VERSION`: `3.12.13` (Optional, but recommended).
5. Click **Create Web Service**.

### 3. Final Verification
1. Render will build and deploy your app. Once the status is **Live**, click the URL provided (e.g., `https://anonvibe-chat.onrender.com`).
2. Visit `/admin` to verify you can log in with `admin` and your chosen password.
3. Enter the chat and verify that messages and data are being captured in the Control Center.

### Important Notes
- **Persistence:** Because Render's Free Tier spins down after 15 minutes of inactivity, the first load might be slow.
- **WebSocket Support:** This configuration uses `eventlet`, which is the standard for real-time Flask-SocketIO apps on Render.
