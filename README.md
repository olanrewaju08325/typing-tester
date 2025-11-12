# TypingTester

A Flask web app for testing typing speed with user accounts, leaderboard, admin dashboard, and PDF reports.

## Quick start (local)
1. Create a virtualenv: `python -m venv venv`
2. Activate it:
   - macOS / Linux: `source venv/bin/activate`
   - Windows: `venv\Scripts\activate`
3. Install deps: `pip install -r requirements.txt`
4. Run: `python app.py`
5. Open http://127.0.0.1:5000

## Deployment
Ready for Render.com / Heroku. Push to GitHub, connect to Render, set build command `pip install -r requirements.txt` and start command `gunicorn app:app`

Default admin: username `admin`, password `admin123` (change after deploy)
