import os
import sqlite3
from functools import wraps
from datetime import date
from flask import Flask, request, redirect, url_for, session, flash, render_template_string, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key-before-launch")
DB_PATH = os.environ.get("ATTENDANCE_DB", os.path.join(os.path.dirname(__file__), "attendance.db"))

# Change these before using the site publicly.
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe-2026!")

BASE_STYLE = """
:root{--navy:#142b4a;--blue:#2563eb;--pale:#eff6ff;--ink:#172033;--muted:#64748b;--line:#e5eaf2;--bg:#f5f7fb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Arial;color:var(--ink)}
a{text-decoration:none;color:inherit}.layout{display:flex;min-height:100vh}.side{width:245px;background:var(--navy);color:white;padding:26px 18px;flex-shrink:0}
.brand{font-size:20px;font-weight:800;padding:8px 10px 28px}.brand small{display:block;color:#b9c9df;font-size:12px;font-weight:500;margin-top:5px}
.nav a{display:block;padding:12px 14px;border-radius:10px;color:#d7e3f2;margin:5px 0}.nav a.active,.nav a:hover{background:#24466f;color:white}
.main{flex:1;min-width:0;padding:30px}.top{display:flex;justify-content:space-between;align-items:center;gap:15px;margin-bottom:24px}
h1{font-size:27px;margin:0 0 5px}.sub{color:var(--muted);font-size:14px}.user{color:var(--muted);font-size:13px}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin:20px 0}
.card,.panel{background:white;border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 5px 20px #1d35570a}
.kicker{font-size:13px;color:var(--muted)}.number{font-size:30px;font-weight:800;margin-top:8px}
.panel{margin-top:18px}.panelhead{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}
h2{font-size:18px;margin:0}input,select{width:100%;padding:11px 12px;border:1px solid #d8e0eb;border-radius:9px;background:white;font:inherit;min-width:0}
label{display:block;font-size:13px;color:#475569;margin:0 0 6px}.field{margin-bottom:13px}
button,.btn{border:0;border-radius:9px;padding:11px 15px;background:var(--blue);color:white;font:600 14px inherit;cursor:pointer;display:inline-block}
.btn.secondary,button.secondary{background:#eaf1fb;color:#1e3a5f}.btn.danger,button.danger{background:#fee2e2;color:#991b1b}
.actions{display:flex;gap:8px;flex-wrap:wrap}.gridform{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;align-items:end}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);font-size:14px}th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.pill{display:inline-block;padding:5px 9px;border-radius:20px;font-size:12px;background:#dcfce7;color:#166534}.pill.absent{background:#fee2e2;color:#991b1b}
.notice{padding:11px 14px;border-radius:10px;background:#eff6ff;color:#1e40af;margin:12px 0}.error{background:#fff1f2;color:#9f1239}
.loginwrap{min-height:100vh;display:grid;place-items:center;padding:20px}.login{width:min(420px,100%);background:white;border:1px solid var(--line);border-radius:18px;padding:30px;box-shadow:0 15px 45px #17203314}
@media(max-width:800px){.layout{display:block}.side{width:auto;padding:15px}.brand{padding:5px 8px 12px}.nav{display:flex;overflow:auto;gap:5px}.nav a{white-space:nowrap}.main{padding:18px}.cards{grid-template-columns:1fr 1fr}.gridform{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}
@media(max-width:480px){.cards{grid-template-columns:1fr}table{min-width:650px}.tablewrap{overflow:auto}}
"""

SHELL = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} · College Attendance</title><style>""" + BASE_STYLE + """</style></head><body><div class="layout"><aside class="side"><div class="brand">CampusTrack<small>Attendance management</small></div><nav class="nav">
<a class="{{ 'active' if active=='dashboard' else '' }}" href="{{ url_for('dashboard') }}">Dashboard</a>
<a class="{{ 'active' if active=='students' else '' }}" href="{{ url_for('students') }}">Students</a>
<a class="{{ 'active' if active=='attendance' else '' }}" href="{{ url_for('attendance') }}">Mark attendance</a>
<a class="{{ 'active' if active=='reports' else '' }}" href="{{ url_for('reports') }}">Reports & exports</a>
<a href="{{ url_for('logout') }}">Log out</a></nav></aside><main class="main"><div class="top"><div><h1>{{ title }}</h1><div class="sub">College attendance dashboard</div></div><div class="user">Signed in as <b>{{ session.get('admin_name') }}</b></div></div>
{% with messages=get_flashed_messages() %}{% if messages %}{% for m in messages %}<div class="notice">{{m}}</div>{% endfor %}{% endif %}{% endwith %}
{{ content|safe }}</main></div></body></html>"""

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def columns(con, table):
    return [r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]

def pick(existing, choices):
    return next((x for x in choices if x in existing), None)

def init_db():
    con = connect()
    con.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll TEXT, registration_no TEXT, name TEXT NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL, date TEXT NOT NULL, status TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES students(id)
    )""")
    # Add newer fields without deleting or replacing existing records.
    sc = columns(con, "students")
    for col, typ in [("roll", "TEXT"), ("registration_no", "TEXT"), ("name", "TEXT")]:
        if col not in sc:
            con.execute(f"ALTER TABLE students ADD COLUMN {col} {typ}")
    ac = columns(con, "attendance")
    if "date" not in ac and "day" in ac:
        con.execute("ALTER TABLE attendance RENAME COLUMN day TO date")
        ac = columns(con, "attendance")
    if "date" not in ac:
        con.execute("ALTER TABLE attendance ADD COLUMN date TEXT")
    if "status" not in ac:
        con.execute("ALTER TABLE attendance ADD COLUMN status TEXT")
    if "student_id" not in ac:
        con.execute("ALTER TABLE attendance ADD COLUMN student_id INTEGER")
    con.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date)")
    # Create/update the single configured admin account.
    con.execute("""CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )""")
    row = con.execute("SELECT id FROM admins WHERE username=?", (ADMIN_USERNAME,)).fetchone()
    if row:
        con.execute("UPDATE admins SET password_hash=? WHERE username=?",
                    (generate_password_hash(ADMIN_PASSWORD), ADMIN_USERNAME))
    else:
        con.execute("INSERT INTO admins(username,password_hash) VALUES(?,?)",
                    (ADMIN_USERNAME, generate_password_hash(ADMIN_PASSWORD)))
    con.commit()
    con.close()

def schema():
    con = connect()
    sc, ac = columns(con, "students"), columns(con, "attendance")
    result = {
        "sid": pick(sc, ["id", "student_id"]),
        "roll": pick(sc, ["roll", "roll_no", "roll_number"]),
        "reg": pick(sc, ["registration_no", "registration", "reg_no", "registration_number"]),
        "name": pick(sc, ["name", "student_name"]),
        "aid": pick(ac, ["id"]),
        "student_id": pick(ac, ["student_id"]),
        "date": pick(ac, ["date", "day"]),
        "status": pick(ac, ["status"])
    }
    con.close()
    if not all(result[k] for k in ["sid", "name", "student_id", "date", "status"]):
        raise RuntimeError("The existing database has an unexpected schema. Keep a backup and ask for a schema-specific app.py.")
    return result

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        con = connect()
        admin = con.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        con.close()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["username"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Incorrect admin ID or password.")
    return render_template_string("""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin login</title><style>""" + BASE_STYLE + """</style></head><body><div class="loginwrap"><form class="login" method="post"><div class="brand" style="color:#142b4a;padding:0 0 20px">CampusTrack<small style="color:#64748b">Admin access only</small></div><h1 style="font-size:24px">Welcome back</h1><p class="sub">Sign in to manage college attendance.</p>{% with messages=get_flashed_messages() %}{% for m in messages %}<div class="notice error">{{m}}</div>{% endfor %}{% endwith %}<div class="field"><label>Admin ID</label><input name="username" required autocomplete="username"></div><div class="field"><label>Password</label><input type="password" name="password" required autocomplete="current-password"></div><button style="width:100%">Sign in</button></form></div></body></html>""")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    s = schema()
    con = connect()
    total = con.execute(f"SELECT COUNT(*) n FROM students").fetchone()["n"]
    today = date.today().isoformat()
    present = con.execute(f"SELECT COUNT(*) n FROM attendance WHERE {s['date']}=? AND lower({s['status']})='present'", (today,)).fetchone()["n"]
    absent = con.execute(f"SELECT COUNT(*) n FROM attendance WHERE {s['date']}=? AND lower({s['status']})='absent'", (today,)).fetchone()["n"]
    recent = con.execute(f"""SELECT st.{s['name']} name, a.{s['status']} status
        FROM attendance a JOIN students st ON st.{s['sid']}=a.{s['student_id']}
        WHERE a.{s['date']}=? ORDER BY a.rowid DESC LIMIT 8""", (today,)).fetchall()
    con.close()
    content = render_template_string("""<div class="cards"><div class="card"><div class="kicker">Total students</div><div class="number">{{total}}</div></div><div class="card"><div class="kicker">Present today</div><div class="number">{{present}}</div></div><div class="card"><div class="kicker">Absent today</div><div class="number">{{absent}}</div></div></div><section class="panel"><div class="panelhead"><h2>Today's attendance · {{today}}</h2><a class="btn secondary" href="{{url_for('attendance')}}">Take attendance</a></div>{% if recent %}<div class="tablewrap"><table><tr><th>Student</th><th>Status</th></tr>{% for r in recent %}<tr><td>{{r.name}}</td><td><span class="pill {{'absent' if r.status|lower=='absent' else ''}}">{{r.status}}</span></td></tr>{% endfor %}</table></div>{% else %}<p class="sub">No attendance has been recorded today.</p>{% endif %}</section>""", total=total, present=present, absent=absent, today=today, recent=recent)
    return render_template_string(SHELL, title="Dashboard", active="dashboard", content=content)

@app.route("/students", methods=["GET", "POST"])
@login_required
def students():
    s = schema()
    con = connect()
    if request.method == "POST":
        roll, reg, name = request.form.get("roll", "").strip(), request.form.get("registration_no", "").strip(), request.form.get("name", "").strip()
        if not name:
            flash("Student name is required.")
        else:
            fields, values = [], []
            for key, val in [(s["roll"], roll), (s["reg"], reg), (s["name"], name)]:
                if key:
                    fields.append(key); values.append(val)
            con.execute(f"INSERT INTO students ({','.join(fields)}) VALUES ({','.join('?' for _ in values)})", values)
            con.commit()
            flash("Student added.")
            con.close()
            return redirect(url_for("students"))
    rows = con.execute(f"SELECT * FROM students ORDER BY {s['roll'] or s['sid']}").fetchall()
    con.close()
    content = render_template_string("""<section class="panel"><h2>Add a student</h2><form method="post" class="gridform" style="margin-top:16px"><div class="field"><label>Roll number</label><input name="roll"></div><div class="field"><label>Registration number</label><input name="registration_no"></div><div class="field"><label>Full name *</label><input name="name" required></div><button>Add student</button></form></section><section class="panel"><div class="panelhead"><h2>Student directory</h2><span class="sub">{{rows|length}} students</span></div><div class="tablewrap"><table><tr><th>Roll</th><th>Registration no.</th><th>Name</th></tr>{% for r in rows %}<tr><td>{{r[roll] if roll else '—'}}</td><td>{{r[reg] if reg else '—'}}</td><td>{{r[name]}}</td></tr>{% endfor %}</table></div></section>""", rows=rows, roll=s["roll"], reg=s["reg"], name=s["name"])
    return render_template_string(SHELL, title="Students", active="students", content=content)

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    s = schema()
    con = connect()
    day = request.values.get("date", date.today().isoformat())
    if request.method == "POST":
        for student in con.execute("SELECT * FROM students").fetchall():
            value = request.form.get("status_" + str(student[s["sid"]]), "Absent")
            value = "Present" if value == "Present" else "Absent"
            old = con.execute(f"SELECT {s['aid'] or 'rowid'} FROM attendance WHERE {s['student_id']}=? AND {s['date']}=?",
                              (student[s["sid"]], day)).fetchone()
            if old:
                con.execute(f"UPDATE attendance SET {s['status']}=? WHERE {s['student_id']}=? AND {s['date']}=?",
                            (value, student[s["sid"]], day))
            else:
                con.execute(f"INSERT INTO attendance ({s['student_id']},{s['date']},{s['status']}) VALUES (?,?,?)",
                            (student[s["sid"]], day, value))
        con.commit()
        flash("Attendance saved.")
    students_rows = con.execute(f"""SELECT st.*,
        (SELECT a.{s['status']} FROM attendance a WHERE a.{s['student_id']}=st.{s['sid']}
         AND a.{s['date']}=? ORDER BY a.rowid DESC LIMIT 1) AS today_status
        FROM students st ORDER BY st.{s['roll'] or s['sid']}""", (day,)).fetchall()
    con.close()
    content = render_template_string("""<section class="panel"><form method="get" class="gridform"><div class="field"><label>Attendance date</label><input type="date" name="date" value="{{day}}"></div><div></div><button>Load date</button></form></section><section class="panel"><div class="panelhead"><h2>Mark students</h2><span class="sub">{{students|length}} students</span></div>{% if students %}<form method="post"><input type="hidden" name="date" value="{{day}}"><div class="tablewrap"><table><tr><th>Roll</th><th>Registration no.</th><th>Name</th><th>Status</th></tr>{% for st in students %}<tr><td>{{st[roll] if roll else '—'}}</td><td>{{st[reg] if reg else '—'}}</td><td>{{st[name]}}</td><td><select name="status_{{st[sid]}}"><option value="Present" {{'selected' if st.today_status=='Present' else ''}}>Present</option><option value="Absent" {{'selected' if st.today_status!='Present' else ''}}>Absent</option></select></td></tr>{% endfor %}</table></div><p><button>Save attendance</button></p></form>{% else %}<p class="sub">Add students first.</p>{% endif %}</section>""", day=day, students=students_rows, roll=s["roll"], reg=s["reg"], name=s["name"], sid=s["sid"])
    return render_template_string(SHELL, title="Mark attendance", active="attendance", content=content)

@app.route("/reports")
@login_required
def reports():
    content = """<section class="panel"><h2>Download attendance records</h2><p class="sub">Export the saved student and attendance records.</p><div class="actions"><a class="btn" href="/export/excel">Download Excel (.xlsx)</a><a class="btn secondary" href="/export/pdf">Download PDF</a></div></section>"""
    return render_template_string(SHELL, title="Reports & exports", active="reports", content=content)

@app.route("/export/excel")
@login_required
def export_excel():
    try:
        from openpyxl import Workbook
    except ImportError:
        return "Install openpyxl: pip install openpyxl", 500
    s = schema(); con = connect()
    rows = con.execute(f"""SELECT st.{s['roll'] or s['sid']}, {('st.'+s['reg']) if s['reg'] else "''"}, st.{s['name']},
        a.{s['date']}, a.{s['status']} FROM students st LEFT JOIN attendance a
        ON st.{s['sid']}=a.{s['student_id']} ORDER BY st.{s['roll'] or s['sid']}, a.{s['date']}""").fetchall()
    con.close()
    wb = Workbook(); ws = wb.active; ws.title = "Attendance"
    ws.append(["Roll", "Registration No.", "Name", "Date", "Status"])
    for r in rows: ws.append(list(r))
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = min(max(max(len(str(c.value or "")) for c in col)+2, 12), 32)
    out = BytesIO(); wb.save(out); out.seek(0)
    return send_file(out, as_attachment=True, download_name="attendance.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/export/pdf")
@login_required
def export_pdf():
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
    except ImportError:
        return "Install reportlab: pip install reportlab", 500
    s = schema(); con = connect()
    rows = con.execute(f"""SELECT st.{s['roll'] or s['sid']}, {('st.'+s['reg']) if s['reg'] else "''"}, st.{s['name']},
        a.{s['date']}, a.{s['status']} FROM students st LEFT JOIN attendance a
        ON st.{s['sid']}=a.{s['student_id']} ORDER BY st.{s['roll'] or s['sid']}, a.{s['date']}""").fetchall()
    con.close()
    out = BytesIO(); doc = SimpleDocTemplate(out, pagesize=landscape(A4))
    data = [["Roll", "Registration No.", "Name", "Date", "Status"]] + [list(map(lambda x: str(x or ""), r)) for r in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#142b4a")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#d8e0eb")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f6fc")]),("PADDING",(0,0),(-1,-1),7)]))
    styles = getSampleStyleSheet()
    doc.build([Paragraph("College Attendance Report", styles["Title"]), Spacer(1,14), table])
    out.seek(0)
    return send_file(out, as_attachment=True, download_name="attendance.pdf", mimetype="application/pdf")

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=False)
