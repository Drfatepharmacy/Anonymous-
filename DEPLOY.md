# Deploying AnonVibe to Render

Follow these steps to deploy your professional anonymous chat honeypot.

### Option A: Automatic Deployment (Recommended)
1. Log in to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** and select **Blueprint**.
3. Connect your GitHub repository.
4. Render will automatically detect the `render.yaml` file and set up both the **PostgreSQL database** and the **Web Service** for you.
5. In the "Admin Password" field, enter the password you want for the `/admin` portal.
6. Click **Apply**.

### Option B: Manual Deployment
1. **Create a PostgreSQL Database:**
   - Click **New +** -> **PostgreSQL**. Name it `anonvibe-db`.
   - Once created, copy the **Internal Database URL**.
2. **Deploy the Web Service:**
   - Click **New +** -> **Web Service**. Connect your repo.
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --worker-class eventlet -w 1 app:app`
   - **Environment Variables:** Add `DATABASE_URL` (from Step 1), `SECRET_KEY` (random string), and `ADMIN_PASSWORD`.
3. Click **Create Web Service**.

### 3. Final Verification
1. Render will build and deploy your app. Once the status is **Live**, click the URL provided (e.g., `https://anonvibe-chat.onrender.com`).
2. Visit `/admin` to verify you can log in with `admin` and your chosen password.
3. Enter the chat and verify that messages and data are being captured in the Control Center.

### Important Notes
- **Persistence:** Because Render's Free Tier spins down after 15 minutes of inactivity, the first load might be slow.
- **WebSocket Support:** This configuration uses `eventlet`, which is the standard for real-time Flask-SocketIO apps on Render.
