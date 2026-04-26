from flask import Flask, render_template, request, jsonify
import sqlite3, re, os

app = Flask(__name__)
DB = "mahasiswa.db"

PRODIS = [
    ("Teknik Informatika",        "Teknik"),
    ("Sistem Informasi",           "Teknik"),
    ("Teknik Elektro",             "Teknik"),
    ("Teknik Industri",            "Teknik"),
    ("Manajemen",                  "Ekonomi & Bisnis"),
    ("Akuntansi",                  "Ekonomi & Bisnis"),
    ("Ilmu Hukum",                 "Hukum"),
    ("Psikologi",                  "Psikologi"),
    ("Pendidikan Matematika",      "Keguruan & Ilmu Pendidikan"),
    ("Pendidikan Bahasa Inggris",  "Keguruan & Ilmu Pendidikan"),
]
PRODI_MAP = {p: f for p, f in PRODIS}


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mahasiswa (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nim         TEXT UNIQUE NOT NULL,
            nama        TEXT NOT NULL,
            prodi       TEXT NOT NULL,
            fakultas    TEXT NOT NULL,
            angkatan    INTEGER NOT NULL,
            semester    INTEGER NOT NULL,
            ipk         REAL NOT NULL DEFAULT 0.0,
            status      TEXT NOT NULL DEFAULT 'Aktif',
            email       TEXT UNIQUE NOT NULL,
            no_hp       TEXT NOT NULL,
            tgl_daftar  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.commit()
    conn.close()


# ── pages ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", prodis=PRODIS)


@app.route("/daftar")
def daftar():
    return render_template("daftar.html", prodis=PRODIS)


# ── API: register ─────────────────────────────────────────────────────────────
@app.route("/api/daftar", methods=["POST"])
def api_daftar():
    d = request.get_json(force=True)

    # --- validation ---
    errors = {}
    nim   = (d.get("nim") or "").strip()
    nama  = (d.get("nama") or "").strip()
    prodi = (d.get("prodi") or "").strip()
    angkatan = d.get("angkatan")
    semester  = d.get("semester")
    email  = (d.get("email") or "").strip().lower()
    no_hp  = (d.get("no_hp") or "").strip()
    status = (d.get("status") or "Aktif").strip()

    if not nim or not re.match(r"^\d{10}$", nim):
        errors["nim"] = "NIM harus 10 digit angka"
    if not nama or len(nama) < 3:
        errors["nama"] = "Nama minimal 3 karakter"
    if prodi not in PRODI_MAP:
        errors["prodi"] = "Program studi tidak valid"
    try:
        angkatan = int(angkatan)
        if angkatan < 2000 or angkatan > 2030:
            errors["angkatan"] = "Angkatan tidak valid"
    except (TypeError, ValueError):
        errors["angkatan"] = "Angkatan harus berupa tahun"
    try:
        semester = int(semester)
        if semester < 1 or semester > 14:
            errors["semester"] = "Semester antara 1–14"
    except (TypeError, ValueError):
        errors["semester"] = "Semester tidak valid"
    if not email or not re.match(r"^[\w.+-]+@[\w-]+\.[a-z]{2,}$", email):
        errors["email"] = "Format email tidak valid"
    if not no_hp or not re.match(r"^08\d{8,11}$", no_hp):
        errors["no_hp"] = "No HP harus dimulai 08, 10–13 digit"
    if status not in ("Aktif", "Cuti"):
        errors["status"] = "Status tidak valid"

    if errors:
        return jsonify({"ok": False, "errors": errors}), 422

    fakultas = PRODI_MAP[prodi]
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO mahasiswa (nim,nama,prodi,fakultas,angkatan,semester,email,no_hp,status) VALUES (?,?,?,?,?,?,?,?,?)",
            (nim, nama, prodi, fakultas, angkatan, semester, email, no_hp, status)
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError as e:
        msg = str(e)
        if "nim" in msg:
            return jsonify({"ok": False, "errors": {"nim": "NIM sudah terdaftar"}}), 409
        if "email" in msg:
            return jsonify({"ok": False, "errors": {"email": "Email sudah terdaftar"}}), 409
        return jsonify({"ok": False, "errors": {"_": "Data duplikat"}}), 409

    return jsonify({"ok": True, "message": f"Selamat datang, {nama}! Data berhasil didaftarkan."})


# ── API: search ───────────────────────────────────────────────────────────────
@app.route("/api/search")
def api_search():
    q        = request.args.get("q", "").strip()
    prodi    = request.args.get("prodi", "")
    fakultas = request.args.get("fakultas", "")
    status   = request.args.get("status", "")
    angkatan = request.args.get("angkatan", "")
    page     = max(1, int(request.args.get("page", 1)))
    per_page = 10

    where, params = [], []
    if q:
        where.append("(nama LIKE ? OR nim LIKE ? OR email LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if prodi:    where.append("prodi=?");    params.append(prodi)
    if fakultas: where.append("fakultas=?"); params.append(fakultas)
    if status:   where.append("status=?");   params.append(status)
    if angkatan: where.append("angkatan=?"); params.append(int(angkatan))

    base = "FROM mahasiswa" + (" WHERE " + " AND ".join(where) if where else "")
    conn = get_db()
    total  = conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    rows   = conn.execute(f"SELECT * {base} ORDER BY tgl_daftar DESC LIMIT ? OFFSET ?",
                          params + [per_page, (page-1)*per_page]).fetchall()
    conn.close()

    return jsonify({
        "total": total, "page": page, "per_page": per_page,
        "results": [dict(r) for r in rows],
    })


# ── API: filters & stats ──────────────────────────────────────────────────────
@app.route("/api/filters")
def api_filters():
    conn = get_db()
    c = conn.cursor()
    prodis    = [r[0] for r in c.execute("SELECT DISTINCT prodi    FROM mahasiswa ORDER BY prodi")]
    fakultas  = [r[0] for r in c.execute("SELECT DISTINCT fakultas FROM mahasiswa ORDER BY fakultas")]
    statuses  = [r[0] for r in c.execute("SELECT DISTINCT status   FROM mahasiswa ORDER BY status")]
    angkatans = [r[0] for r in c.execute("SELECT DISTINCT angkatan FROM mahasiswa ORDER BY angkatan DESC")]
    conn.close()
    return jsonify({"prodis": prodis, "fakultas": fakultas, "statuses": statuses, "angkatans": angkatans})


@app.route("/api/stats")
def api_stats():
    conn = get_db()
    c = conn.cursor()
    total       = c.execute("SELECT COUNT(*) FROM mahasiswa").fetchone()[0]
    aktif       = c.execute("SELECT COUNT(*) FROM mahasiswa WHERE status='Aktif'").fetchone()[0]
    avg_ipk     = c.execute("SELECT ROUND(AVG(ipk),2) FROM mahasiswa").fetchone()[0] or 0
    total_prodi = c.execute("SELECT COUNT(DISTINCT prodi) FROM mahasiswa").fetchone()[0]
    conn.close()
    return jsonify({"total": total, "aktif": aktif, "avg_ipk": avg_ipk, "total_prodi": total_prodi})

init_db()
if __name__ == "__main__":
    app.run(debug=True, port=5000)
