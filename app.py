import os
import sqlite3
from functools import wraps
from datetime import date
from flask import (
    Flask, request, redirect, url_for,
    session, flash, render_template_string,
    send_file
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

DB = os.environ.get("DATABASE_PATH", "attendance.db")


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def setup():
    con = db()

    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            student_id INTEGER
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll TEXT,
            registration_no TEXT,
            name TEXT NOT NULL
        )
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            UNIQUE(student_id, date)
        )
    """)

    con.commit()
    con.close()


setup()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                return "Access denied", 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CampusTrack</title>
<style>
body {
    font-family: Arial, sans-serif;
    background: #f1f5f9;
    margin: 0;
    color: #172554;
}
header {
    background: #142b4a;
    color: white;
    padding: 20px;
}
main {
    max-width: 850px;
    margin: 25px auto;
    padding: 20px;
}
.card {
    background: white;
    padding: 22px;
    border-radius: 14px;
    margin-bottom: 18px;
    box-shadow: 0 3px 15px #0001;
}
input, select, button {
    padding: 12px;
    margin: 7px 0;
    width: 100%;
    box-sizing: border-box;
}
button {
    background: #2563eb;
    color: white;
    border: 0;
    border-radius: 7px;
}
a { color: #2563eb; }
table {
    width: 100%;
    border-collapse: collapse;
}
td, th {
    padding: 10px;
    border-bottom: 1px solid #ddd;
    text-align: left;
}
</style>
</head>
<body>
<header>
<h2>CampusTrack</h2>
College Attendance Management
</header>
<main>
{{ content|safe }}
</main>
</body>
</html>
"""
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        con = db()
        user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()
        con.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["student_id"] = user["student_id"]
            return redirect(url_for("dashboard"))

        flash("Invalid username or password")

    return render_template_string(PAGE, content="""
        <div class="card">
        <h2>Login</h2>
        {% with messages = get_flashed_messages() %}
          {% for message in messages %}
            <p>{{ message }}</p>
          {% endfor %}
        {% endwith %}
        <form method="post">
            <input name="username" placeholder="User ID" required>
            <input name="password" type="password"
                   placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        </div>
    """)


@app.route("/")
@login_required
def dashboard():
    role = session["role"]

    content = f"""
    <div class="card">
    <h2>Welcome, {session['username']}</h2>
    <p>Role: {role.title()}</p>
    """

    if role == "admin":
        content += """
        <p><a href="/create-user">Create teacher/student account</a></p>
        <p><a href="/students">Manage students</a></p>
        <p><a href="/reports">Attendance reports</a></p>
        """

    elif role == "teacher":
        content += """
        <p><a href="/attendance">Mark attendance</a></p>
        <p><a href="/students">View students</a></p>
        <p><a href="/reports">Attendance reports</a></p>
        """

    elif role == "student":
        content += """
        <p><a href="/my-attendance">My attendance</a></p>
        """

    content += '<p><a href="/logout">Log out</a></p></div>'

    return render_template_string(PAGE, content=content)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
    @app.route("/setup-admin", methods=["GET", "POST"])
def setup_admin():
    con = db()
    count = con.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    if count > 0:
        con.close()
        return "Admin setup is already completed."

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or len(password) < 8:
            con.close()
            return "Username is required and password must be at least 8 characters."

        con.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), "admin")
        )
        con.commit()
        con.close()
        return redirect(url_for("login"))

    con.close()

    return render_template_string(PAGE, content="""
    <div class="card">
        <h2>Create First Admin</h2>
        <form method="post">
            <input name="username" placeholder="Admin ID" required>
            <input name="password" type="password"
                   placeholder="Password (minimum 8 characters)" required>
            <button type="submit">Create Admin</button>
        </form>
    </div>
    """)


@app.route("/create-user", methods=["GET", "POST"])
@role_required("admin")
def create_user():
    con = db()
    students = con.execute(
        "SELECT * FROM students ORDER BY roll"
    ).fetchall()

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]
        student_id = request.form.get("student_id") or None

        if role not in ("teacher", "student"):
            con.close()
            return "Invalid role", 400

        if not username or len(password) < 8:
            con.close()
            return "Username required; password must be at least 8 characters."

        if role == "student" and not student_id:
            con.close()
            return "Select a student record first."

        try:
            con.execute("""
                INSERT INTO users (username, password, role, student_id)
                VALUES (?, ?, ?, ?)
            """, (
                username,
                generate_password_hash(password),
                role,
                student_id if role == "student" else None
            ))
            con.commit()
            flash("Account created successfully.")
        except sqlite3.IntegrityError:
            flash("That username already exists.")

        con.close()
        return redirect(url_for("create_user"))

    con.close()

    return render_template_string(PAGE, content="""
    <div class="card">
        <h2>Create Account</h2>
        {% with messages = get_flashed_messages() %}
          {% for message in messages %}<p>{{ message }}</p>{% endfor %}
        {% endwith %}
        <form method="post">
            <input name="username" placeholder="New User ID" required>
            <input name="password" type="password"
                   placeholder="Password (minimum 8 characters)" required>

            <select name="role" required>
                <option value="teacher">Teacher</option>
                <option value="student">Student</option>
            </select>

            <label>Student record (required for student accounts)</label>
            <select name="student_id">
                <option value="">Select student</option>
                {% for s in students %}
                <option value="{{ s.id }}">
                    {{ s.roll }} - {{ s.name }}
                </option>
                {% endfor %}
            </select>

            <button type="submit">Create Account</button>
        </form>
        <p><a href="/">Back to Dashboard</a></p>
    </div>
    """, students=students)
    @app.route("/students", methods=["GET", "POST"])
@role_required("admin", "teacher")
def students_page():
    con = db()

    if request.method == "POST":
        if session["role"] != "admin":
            con.close()
            return "Access denied", 403

        roll = request.form["roll"].strip()
        registration_no = request.form["registration_no"].strip()
        name = request.form["name"].strip()

        if name:
            con.execute("""
                INSERT INTO students (roll, registration_no, name)
                VALUES (?, ?, ?)
            """, (roll, registration_no, name))
            con.commit()

        con.close()
        return redirect(url_for("students_page"))

    students = con.execute(
        "SELECT * FROM students ORDER BY roll"
    ).fetchall()

    con.close()

    return render_template_string(PAGE, content="""
    <div class="card">
        <h2>Student Records</h2>

        {% if role == "admin" %}
        <form method="post">
            <input name="roll" placeholder="Roll Number" required>
            <input name="registration_no"
                   placeholder="Registration Number">
            <input name="name" placeholder="Student Name" required>
            <button type="submit">Add Student</button>
        </form>
        {% endif %}

        <h3>Student List</h3>
        <table>
            <tr>
                <th>Roll</th>
                <th>Registration</th>
                <th>Name</th>
            </tr>
            {% for s in students %}
            <tr>
                <td>{{ s.roll }}</td>
                <td>{{ s.registration_no }}</td>
                <td>{{ s.name }}</td>
            </tr>
            {% endfor %}
        </table>

        <p><a href="/">Back to Dashboard</a></p>
    </div>
    """, students=students, role=session["role"])
    @app.route("/attendance", methods=["GET", "POST"])
@role_required("teacher")
def attendance_page():
    con = db()

    if request.method == "POST":
        attendance_date = request.form["date"]

        for key, value in request.form.items():
            if key.startswith("status_"):
                student_id = key.replace("status_", "")

                if value not in ("Present", "Absent"):
                    continue

                con.execute("""
                    INSERT INTO attendance (student_id, date, status)
                    VALUES (?, ?, ?)
                    ON CONFLICT(student_id, date)
                    DO UPDATE SET status=excluded.status
                """, (student_id, attendance_date, value))

        con.commit()
        con.close()
        flash("Attendance saved successfully.")
        return redirect(url_for("attendance_page"))

    students = con.execute(
        "SELECT * FROM students ORDER BY roll"
    ).fetchall()

    con.close()

    return render_template_string(PAGE, content="""
    <div class="card">
        <h2>Mark Attendance</h2>

        {% with messages = get_flashed_messages() %}
          {% for message in messages %}<p>{{ message }}</p>{% endfor %}
        {% endwith %}

        <form method="post">
            <label>Attendance Date</label>
            <input type="date" name="date" value="{{ today }}" required>

            <table>
                <tr>
                    <th>Roll</th>
                    <th>Name</th>
                    <th>Status</th>
                </tr>

                {% for s in students %}
                <tr>
                    <td>{{ s.roll }}</td>
                    <td>{{ s.name }}</td>
                    <td>
                        <select name="status_{{ s.id }}">
                            <option value="Present">Present</option>
                            <option value="Absent">Absent</option>
                        </select>
                    </td>
                </tr>
                {% endfor %}
            </table>

            <button type="submit">Save Attendance</button>
        </form>

        <p><a href="/">Back to Dashboard</a></p>
    </div>
    """, students=students, today=date.today().isoformat())


@app.route("/my-attendance")
@role_required("student")
def my_attendance():
    con = db()

    records = con.execute("""
        SELECT date, status
        FROM attendance
        WHERE student_id = ?
        ORDER BY date DESC
    """, (session["student_id"],)).fetchall()

    con.close()

    return render_template_string(PAGE, content="""
    <div class="card">
        <h2>My Attendance</h2>

        <table>
            <tr>
                <th>Date</th>
                <th>Status</th>
            </tr>
            {% for r in records %}
            <tr>
                <td>{{ r.date }}</td>
                <td>{{ r.status }}</td>
            </tr>
            {% endfor %}
        </table>

        <p>Total classes: {{ records|length }}</p>
        <p><a href="/">Back to Dashboard</a></p>
    </div>
    """, records=records)
