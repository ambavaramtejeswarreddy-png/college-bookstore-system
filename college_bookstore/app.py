import os
import sqlite3
from functools import wraps
from pathlib import Path
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, g, send_from_directory, abort)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "college.db"
UPLOAD_ROOT = BASE_DIR / "static" / "uploads"
BOOK_UPLOADS = UPLOAD_ROOT / "books"
MATERIAL_UPLOADS = UPLOAD_ROOT / "materials"
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "png", "jpg", "jpeg", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-development-secret")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_ROOT)

for folder in (BOOK_UPLOADS, MATERIAL_UPLOADS):
    folder.mkdir(parents=True, exist_ok=True)

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        department TEXT DEFAULT '',
        semester TEXT DEFAULT '',
        role TEXT NOT NULL DEFAULT 'student',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT DEFAULT '',
        subject TEXT DEFAULT '',
        semester TEXT DEFAULT '',
        price REAL NOT NULL DEFAULT 0,
        description TEXT DEFAULT '',
        cover TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        subject TEXT DEFAULT '',
        semester TEXT DEFAULT '',
        department TEXT DEFAULT '',
        material_type TEXT DEFAULT 'Notes',
        filename TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        book_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        total REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(book_id) REFERENCES books(id)
    );
    """)
    # A private owner account is created from environment variables.
    owner_email = os.environ.get("OWNER_EMAIL", "owner@campus.com").strip().lower()
    owner_password = os.environ.get("OWNER_PASSWORD", "ChangeMe123!")
    owner = db.execute("SELECT id FROM users WHERE email=?", (owner_email,)).fetchone()
    if not owner:
        db.execute(
            "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            ("Store Owner", owner_email, generate_password_hash(owner_password),
             "owner", datetime.now().isoformat(timespec="seconds"))
        )
    db.commit()
    db.close()

init_db()

def current_user():
    if "user_id" not in session:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

@app.context_processor
def inject_user():
    return {"current_user": current_user()}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def student_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        user = current_user()
        if user["role"] != "student":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def owner_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        user = current_user()
        if user["role"] != "owner":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload(file, folder):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError("Unsupported file type. Use PDF, DOC, DOCX, PPT, PPTX or an image.")
    safe = secure_filename(file.filename)
    if not safe:
        raise ValueError("Invalid filename.")
    # Avoid overwriting an existing file.
    stem, suffix = os.path.splitext(safe)
    candidate, counter = safe, 1
    while (folder / candidate).exists():
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    file.save(folder / candidate)
    return candidate

@app.route("/")
def index():
    db = get_db()
    books = db.execute("SELECT * FROM books ORDER BY id DESC LIMIT 6").fetchall()
    materials = db.execute("SELECT * FROM materials ORDER BY id DESC LIMIT 4").fetchall()
    return render_template("index.html", books=books, materials=materials)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        department = request.form.get("department", "").strip()
        semester = request.form.get("semester", "").strip()
        if not name or not email or len(password) < 8:
            flash("Enter your name and email, and use a password of at least 8 characters.", "danger")
            return render_template("register.html")
        try:
            db = get_db()
            db.execute("""INSERT INTO users(name,email,password_hash,department,semester,role,created_at)
                          VALUES(?,?,?,?,?,'student',?)""",
                       (name, email, generate_password_hash(password), department, semester,
                        datetime.now().isoformat(timespec="seconds")))
            db.commit()
            flash("Your student account has been created. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=? AND role='student'", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid student email or password.", "danger")
    return render_template("login.html")

@app.route("/owner-login", methods=["GET", "POST"])
def owner_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=? AND role='owner'", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Owner access granted.", "success")
            return redirect(url_for("admin"))
        flash("Invalid owner credentials.", "danger")
    return render_template("owner_login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))

@app.route("/dashboard")
@student_required
def dashboard():
    db = get_db()
    user = current_user()
    books = db.execute("SELECT * FROM books ORDER BY id DESC LIMIT 4").fetchall()
    materials = db.execute("SELECT * FROM materials ORDER BY id DESC LIMIT 4").fetchall()
    order_count = db.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (user["id"],)).fetchone()[0]
    return render_template("dashboard.html", books=books, materials=materials, order_count=order_count)

@app.route("/books")
@login_required
def books():
    rows = get_db().execute("SELECT * FROM books ORDER BY title").fetchall()
    return render_template("books.html", books=rows)

@app.route("/materials")
@login_required
def materials():
    rows = get_db().execute("SELECT * FROM materials ORDER BY semester, title").fetchall()
    return render_template("materials.html", materials=rows)

@app.route("/profile", methods=["GET", "POST"])
@student_required
def profile():
    user = current_user()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        department = request.form.get("department", "").strip()
        semester = request.form.get("semester", "").strip()
        if not name:
            flash("Name cannot be empty.", "danger")
        else:
            get_db().execute("UPDATE users SET name=?, department=?, semester=? WHERE id=?",
                             (name, department, semester, user["id"]))
            get_db().commit()
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html", user=current_user())

@app.route("/orders")
@student_required
def orders():
    rows = get_db().execute("""
        SELECT orders.*, books.title AS book_title
        FROM orders JOIN books ON books.id=orders.book_id
        WHERE orders.user_id=? ORDER BY orders.id DESC
    """, (current_user()["id"],)).fetchall()
    return render_template("orders.html", orders=rows)

@app.route("/order/<int:book_id>", methods=["POST"])
@student_required
def order_book(book_id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
    if not book:
        abort(404)
    try:
        quantity = max(1, min(10, int(request.form.get("quantity", "1"))))
    except ValueError:
        quantity = 1
    db.execute("INSERT INTO orders(user_id,book_id,quantity,total,status,created_at) VALUES(?,?,?,?,?,?)",
               (current_user()["id"], book_id, quantity, book["price"] * quantity,
                "Pending", datetime.now().isoformat(timespec="seconds")))
    db.commit()
    flash("Your order request has been placed.", "success")
    return redirect(url_for("orders"))

@app.route("/download/material/<int:material_id>")
@login_required
def download_material(material_id):
    material = get_db().execute("SELECT filename FROM materials WHERE id=?", (material_id,)).fetchone()
    if not material:
        abort(404)
    return send_from_directory(MATERIAL_UPLOADS, material["filename"], as_attachment=True)

@app.route("/admin")
@owner_required
def admin():
    db = get_db()
    counts = {
        "books": db.execute("SELECT COUNT(*) FROM books").fetchone()[0],
        "materials": db.execute("SELECT COUNT(*) FROM materials").fetchone()[0],
        "students": db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
    }
    recent_orders = db.execute("""
        SELECT orders.*, users.name AS student_name, books.title AS book_title
        FROM orders JOIN users ON users.id=orders.user_id
        JOIN books ON books.id=orders.book_id ORDER BY orders.id DESC LIMIT 8
    """).fetchall()
    return render_template("admin.html", counts=counts, orders=recent_orders)

@app.route("/admin/books", methods=["GET", "POST"])
@owner_required
def manage_books():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Book title is required.", "danger")
        else:
            try:
                cover = save_upload(request.files.get("cover"), BOOK_UPLOADS) or ""
                price = max(0, float(request.form.get("price", "0") or 0))
                db.execute("""INSERT INTO books(title,author,subject,semester,price,description,cover,created_at)
                              VALUES(?,?,?,?,?,?,?,?)""",
                           (title, request.form.get("author","").strip(),
                            request.form.get("subject","").strip(), request.form.get("semester","").strip(),
                            price, request.form.get("description","").strip(), cover,
                            datetime.now().isoformat(timespec="seconds")))
                db.commit()
                flash("Book added successfully.", "success")
                return redirect(url_for("manage_books"))
            except (ValueError, TypeError) as exc:
                flash(str(exc) or "Enter a valid price.", "danger")
    rows = db.execute("SELECT * FROM books ORDER BY id DESC").fetchall()
    return render_template("manage_books.html", books=rows)

@app.route("/admin/books/delete/<int:book_id>", methods=["POST"])
@owner_required
def delete_book(book_id):
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM orders WHERE book_id=?", (book_id,)).fetchone()[0]:
        flash("This book has order history and cannot be deleted.", "warning")
    else:
        db.execute("DELETE FROM books WHERE id=?", (book_id,))
        db.commit()
        flash("Book deleted.", "success")
    return redirect(url_for("manage_books"))

@app.route("/admin/materials", methods=["GET", "POST"])
@owner_required
def manage_materials():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        upload = request.files.get("file")
        if not title or not upload or not upload.filename:
            flash("Enter a title and select a material file.", "danger")
        else:
            try:
                filename = save_upload(upload, MATERIAL_UPLOADS)
                db.execute("""INSERT INTO materials(title,subject,semester,department,material_type,filename,description,created_at)
                              VALUES(?,?,?,?,?,?,?,?)""",
                           (title, request.form.get("subject","").strip(),
                            request.form.get("semester","").strip(), request.form.get("department","").strip(),
                            request.form.get("material_type","Notes").strip(), filename,
                            request.form.get("description","").strip(),
                            datetime.now().isoformat(timespec="seconds")))
                db.commit()
                flash("Study material uploaded.", "success")
                return redirect(url_for("manage_materials"))
            except ValueError as exc:
                flash(str(exc), "danger")
    rows = db.execute("SELECT * FROM materials ORDER BY id DESC").fetchall()
    return render_template("manage_materials.html", materials=rows)

@app.route("/admin/materials/delete/<int:material_id>", methods=["POST"])
@owner_required
def delete_material(material_id):
    db = get_db()
    row = db.execute("SELECT filename FROM materials WHERE id=?", (material_id,)).fetchone()
    if row:
        try:
            (MATERIAL_UPLOADS / row["filename"]).unlink(missing_ok=True)
        except OSError:
            pass
        db.execute("DELETE FROM materials WHERE id=?", (material_id,))
        db.commit()
        flash("Study material deleted.", "success")
    return redirect(url_for("manage_materials"))

@app.route("/admin/students")
@owner_required
def manage_students():
    students = get_db().execute(
        "SELECT id,name,email,department,semester,created_at FROM users WHERE role='student' ORDER BY id DESC"
    ).fetchall()
    return render_template("manage_students.html", students=students)

@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@owner_required
def update_order_status(order_id):
    status = request.form.get("status", "Pending")
    if status not in {"Pending", "Approved", "Completed", "Cancelled"}:
        abort(400)
    get_db().execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    get_db().commit()
    flash("Order status updated.", "success")
    return redirect(url_for("admin"))

@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The page or item you requested was not found."), 404

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
