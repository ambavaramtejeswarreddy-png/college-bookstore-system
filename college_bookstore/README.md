# College Book Store and Semester Study Material System

A Flask + SQLite web application with a premium navy-and-gold design.

## Features
- Student registration and login
- Separate owner login (no public owner registration)
- Student dashboard, profile, books, materials and order history
- Owner dashboard, book management, material uploads, student list and order status management
- Password hashing and role-protected routes
- SQLite database created automatically

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in this folder.
3. Create and activate a virtual environment (recommended).
4. Install dependencies:
   `pip install -r requirements.txt`
5. Set a strong secret key and owner credentials before first run:
   - Windows PowerShell:
     `$env:SECRET_KEY="replace-with-a-long-random-secret"`
     `$env:OWNER_EMAIL="owner@example.com"`
     `$env:OWNER_PASSWORD="choose-a-strong-password"`
   - macOS/Linux:
     `export SECRET_KEY="replace-with-a-long-random-secret"`
     `export OWNER_EMAIL="owner@example.com"`
     `export OWNER_PASSWORD="choose-a-strong-password"`
6. Start the app:
   `python app.py`
7. Visit http://127.0.0.1:5000

## Initial owner account
If you do not set environment variables, the first database initialization creates:
- Email: `owner@campus.com`
- Password: `ChangeMe123!`

**Immediately replace these credentials before using the app.** For a fresh setup, set OWNER_EMAIL and OWNER_PASSWORD before the first run. If the database already exists, changing those variables does not automatically change the existing owner's password.

## Deployment notes
- Set `SECRET_KEY`, `OWNER_EMAIL`, and `OWNER_PASSWORD` as private environment variables in your hosting provider.
- Use a persistent disk for `college.db` and uploaded files. Ephemeral hosting filesystems can erase data on redeploy.
- Turn off Flask debug mode in production.
- Add CSRF protection, email verification, password reset, payment integration and database backups before public production use.
- The starter app records book order requests; it does not process online payments.
