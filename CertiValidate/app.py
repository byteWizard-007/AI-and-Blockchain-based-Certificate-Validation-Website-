import os
import hashlib
import uuid
import csv
import json
import logging
from io import StringIO
from datetime import datetime

from bson import ObjectId
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_file, jsonify, make_response)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from database import get_db
from blockchain import Blockchain
from ai_module import analyze_certificate
from utils import generate_qr_code, generate_pdf_report, generate_pdf_table

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s")
logger = logging.getLogger(__name__)

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "certivalidate_super_secret_2025")

# ── Mail Config ───────────────────────────────────────────────────────────────
app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 587
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = os.environ.get('MAIL_USER', 'your_email@gmail.com')
app.config['MAIL_PASSWORD']       = os.environ.get('MAIL_PASS', 'your_app_password')
app.config['MAIL_DEFAULT_SENDER'] = 'no-reply@certivalidate.com'
mail = Mail(app)

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# ── Upload directories ────────────────────────────────────────────────────────
UPLOAD_FOLDER  = 'static/uploads'
QR_FOLDER      = 'static/qrcodes'
REPORTS_FOLDER = 'static/reports'

for _folder in [UPLOAD_FOLDER, QR_FOLDER, REPORTS_FOLDER]:
    os.makedirs(_folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ── Blockchain (JSON-file based local ledger) ─────────────────────────────────
blockchain = Blockchain()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def hash_file(filepath: str) -> str:
    """SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _oid(doc_id) -> str:
    """Return string representation of a MongoDB _id."""
    return str(doc_id)


def _cert_to_dict(cert) -> dict:
    """Convert MongoDB certificate document to plain dict."""
    if cert is None:
        return {}
    d = dict(cert)
    d['id'] = _oid(d.pop('_id', ''))
    return d


def _send_async_email(app_ctx, msg_obj):
    """Send email in a background thread."""
    import threading
    def _send():
        with app_ctx.app_context():
            try:
                mail.send(msg_obj)
            except Exception as e:
                logger.error("Mail send error: %s", e)
    threading.Thread(target=_send, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Routes – Public
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


# ─────────────────────────────────────────────────────────────────────────────
# Auth routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name      = request.form['name'].strip()
        email     = request.form['email'].strip().lower()
        password  = request.form['password']
        role      = request.form.get('role', 'verifier')

        hashed_pw = generate_password_hash(password)
        token     = str(uuid.uuid4())

        db = get_db()
        try:
            db.users.insert_one({
                "name":               name,
                "email":              email,
                "password":           hashed_pw,
                "role":               role,
                "is_verified":        False,
                "verification_token": token,
                "created_at":         datetime.utcnow(),
            })
            # Confirmation email
            confirm_url = request.url_root.rstrip('/') + url_for('confirm_email', token=token)
            msg = Message("Confirm your CertiValidate Account", recipients=[email])
            msg.body = (f"Welcome {name}!\n\nClick the link below to activate your account:\n"
                        f"{confirm_url}\n\nThank you!")
            _send_async_email(app, msg)
            flash('Registered! Check your email to verify your account.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            logger.error("Registration error: %s", e)
            flash('Registration failed – email may already be in use.', 'error')

    return render_template('register.html')


@app.route('/confirm_email/<token>')
def confirm_email(token):
    db   = get_db()
    user = db.users.find_one({"verification_token": token})
    if user:
        if user.get('is_verified'):
            flash('Account already verified. Please login.', 'info')
        else:
            db.users.update_one({"_id": user["_id"]}, {"$set": {"is_verified": True}})
            flash('Email confirmed! You can now log in.', 'success')
    else:
        flash('The confirmation link is invalid or has expired.', 'error')
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']

        db   = get_db()
        user = db.users.find_one({"email": email})

        if user and check_password_hash(user['password'], password):
            if not user.get('is_verified'):
                flash('Email not verified yet (check your inbox).', 'warning')
            session['user_id']   = _oid(user['_id'])
            session['user_name'] = user['name']
            session['user_role'] = user['role']
            flash(f'Welcome back, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login to access the dashboard.', 'warning')
        return redirect(url_for('login'))

    db = get_db()

    users_count = db.users.count_documents({})
    certs_count = db.certificates.count_documents({})

    # Average authenticity score
    pipeline_avg = [{"$group": {"_id": None, "avg": {"$avg": "$authenticity_score"}}}]
    avg_result   = list(db.certificates.aggregate(pipeline_avg))
    avg_score    = round(avg_result[0]['avg'], 2) if avg_result else 0

    # Recent activity – last 5 verification logs
    recent_logs = list(db.verification_logs.find().sort("timestamp", -1).limit(5))
    for log in recent_logs:
        log['id'] = _oid(log.pop('_id', ''))

    # Chart: status breakdown
    chart_status = {'Genuine': 0, 'Suspicious': 0, 'Fake': 0}
    for row in db.certificates.aggregate([{"$group": {"_id": "$ai_status", "count": {"$sum": 1}}}]):
        if row['_id'] in chart_status:
            chart_status[row['_id']] = row['count']

    # Chart: monthly verification counts (last 6 months)
    month_pipeline = [
        {"$project": {"month": {"$dateToString": {"format": "%Y-%m", "date": "$timestamp"}}}},
        {"$group": {"_id": "$month", "count": {"$sum": 1}}},
        {"$sort": {"_id": -1}},
        {"$limit": 6},
    ]
    months_raw   = list(db.verification_logs.aggregate(month_pipeline))
    chart_months = {row['_id']: row['count'] for row in reversed(months_raw)}

    # Chart: score histogram
    bins = {'0-20': 0, '21-40': 0, '41-60': 0, '61-80': 0, '81-100': 0}
    for cert in db.certificates.find({}, {"authenticity_score": 1}):
        val = cert.get('authenticity_score')
        if val is None:
            continue
        if val <= 20:   bins['0-20']   += 1
        elif val <= 40: bins['21-40']  += 1
        elif val <= 60: bins['41-60']  += 1
        elif val <= 80: bins['61-80']  += 1
        else:           bins['81-100'] += 1

    blocks_count = len(blockchain.chain)

    return render_template(
        'dashboard.html',
        users_count=users_count,
        certs_count=certs_count,
        blocks_count=blocks_count,
        avg_score=avg_score,
        recent_activity=recent_logs,
        chart_status=chart_status,
        chart_months=chart_months,
        chart_bins=bins,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Upload (Admin only) – registers a genuine certificate into the system
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized Access. Admin role required.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        student_name    = request.form['student_name'].strip()
        register_number = request.form['register_number'].strip()
        course          = request.form['course'].strip()
        year            = request.form['year'].strip()
        university_name = request.form.get('university_name', '').strip()
        issue_date      = request.form.get('issue_date', '').strip()

        file = request.files.get('certificate')
        if not file or file.filename == '':
            flash('No certificate file provided.', 'error')
            return render_template('upload.html')

        filename  = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # ── AI Analysis ──────────────────────────────────────────────────────
        ai_result  = analyze_certificate(file_path, blockchain_obj=blockchain)
        score      = ai_result['final_score']
        ai_status  = ai_result['classification']

        # ── Document hash ─────────────────────────────────────────────────────
        cert_hash = hash_file(file_path)

        # ── Blockchain block ──────────────────────────────────────────────────
        block_data = {
            "student_name":    student_name,
            "register_number": register_number,
            "university_name": university_name,
            "course":          course,
            "year":            year,
            "issue_date":      issue_date,
            "certificate_hash": cert_hash,
        }
        new_block = blockchain.add_block(block_data)

        # ── Save to MongoDB ───────────────────────────────────────────────────
        db = get_db()
        try:
            doc = {
                "student_name":      student_name,
                "register_number":   register_number,
                "university_name":   university_name,
                "course":            course,
                "year":              year,
                "issue_date":        issue_date,
                "file_path":         file_path,
                "certificate_hash":  cert_hash,
                "blockchain_hash":   new_block.hash,
                "authenticity_score": score,
                "ai_status":         ai_status,
                "verdict":           ai_result.get('verdict', 'FAKE'),
                "confidence":        ai_result.get('confidence', score),
                "uploaded_by":       session['user_id'],
                "uploaded_at":       datetime.utcnow(),
                "ai_breakdown":      ai_result.get('breakdown', {}),
                "ai_entities":       ai_result.get('entities', {}),
                "fake_reasons":      ai_result.get('fake_reasons', []),
            }
            insert_result = db.certificates.insert_one(doc)
            cert_id_str   = str(insert_result.inserted_id)

            # QR Code
            qr_url  = request.url_root.rstrip('/') + url_for('result', cert_id=cert_id_str)
            qr_path = os.path.join(QR_FOLDER, f"{register_number}.png")
            generate_qr_code(qr_url, qr_path)

            # Embed QR onto certificate image
            try:
                from PIL import Image as PILImage
                base_img = PILImage.open(file_path).convert("RGBA")
                qr_img   = PILImage.open(qr_path).convert("RGBA")
                qr_size  = int(min(base_img.width, base_img.height) * 0.15)
                qr_img   = qr_img.resize((qr_size, qr_size))
                pos_x    = base_img.width  - qr_size - 20
                pos_y    = base_img.height - qr_size - 20
                base_img.paste(qr_img, (pos_x, pos_y), qr_img)
                base_img.convert("RGB").save(file_path)
            except Exception as e:
                logger.warning("QR embed error: %s", e)

            # Log the upload as a verification event
            db.verification_logs.insert_one({
                "certificate_id": cert_id_str,
                "register_number": register_number,
                "verified_by":    session.get('user_name', 'Admin'),
                "authenticity_score": score,
                "verdict":       ai_result.get('verdict', 'FAKE'),
                "result":        f"Uploaded – {ai_status}",
                "timestamp":     datetime.utcnow(),
            })

            if ai_status == 'Fake':
                flash('⚠ Fake certificate detected and logged!', 'danger')
            elif ai_status == 'Suspicious':
                flash('⚠ Certificate flagged as Suspicious.', 'warning')
            else:
                flash('Certificate uploaded and verified successfully.', 'success')

            return redirect(url_for('result', cert_id=cert_id_str))

        except Exception as e:
            logger.error("Upload DB error: %s", e)
            flash(f'Database error: {str(e)}', 'error')

    return render_template('upload.html')


# ─────────────────────────────────────────────────────────────────────────────
# Verify – public-facing certificate verification by register number or file
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    if request.method == 'POST':
        register_number = request.form.get('register_number', '').strip()
        uploaded_file   = request.files.get('certificate_file')

        db   = get_db()
        cert_doc = None

        if register_number:
            cert_doc = db.certificates.find_one({"register_number": register_number})

        # If a file was uploaded, run AI + DB/BC validation regardless
        if uploaded_file and uploaded_file.filename != '':
            filename  = secure_filename(uploaded_file.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], "verify_temp_" + filename)
            uploaded_file.save(temp_path)

            ai_result  = analyze_certificate(temp_path, blockchain_obj=blockchain)
            cert_hash  = ai_result.get('cert_hash', hash_file(temp_path))

            # Try locating by hash if reg_num didn't match
            if cert_doc is None:
                cert_doc = db.certificates.find_one({"certificate_hash": cert_hash})

            try:
                os.remove(temp_path)
            except Exception:
                pass

            # Determine final verdict
            if cert_doc:
                stored_bc_hash = cert_doc.get('blockchain_hash', '')
                bc_hash_ok     = any(
                    b.hash == stored_bc_hash for b in blockchain.chain
                    if isinstance(b.data, dict)
                )
                chain_valid    = blockchain.is_chain_valid()

                if bc_hash_ok and chain_valid:
                    final_verdict = "ORIGINAL"
                    final_status  = "Genuine"
                else:
                    final_verdict = "FAKE"
                    final_status  = "Suspicious"
            else:
                final_verdict = "FAKE"
                final_status  = ai_result['classification']

            # Log the verification
            cert_id_log = str(cert_doc['_id']) if cert_doc else "unknown"
            db.verification_logs.insert_one({
                "certificate_id":     cert_id_log,
                "register_number":    register_number or ai_result['entities'].get('certificate_id', 'N/A'),
                "verified_by":        session.get('user_name', 'Guest'),
                "authenticity_score": ai_result['final_score'],
                "verdict":            final_verdict,
                "result":             f"{final_status} – AI score {ai_result['final_score']}%",
                "timestamp":          datetime.utcnow(),
                "ai_entities":        ai_result.get('entities', {}),
                "fake_reasons":       ai_result.get('fake_reasons', []),
            })

            if cert_doc:
                flash('Verification complete.', 'success')
                return redirect(url_for('result', cert_id=str(cert_doc['_id'])))
            else:
                # No matching record → render a fake-result page from AI data
                flash('Certificate NOT found in the ledger.', 'error')
                return render_template('result_unregistered.html',
                                       ai_result=ai_result,
                                       final_verdict=final_verdict)

        elif cert_doc:
            # Register-number lookup only
            bc_valid = blockchain.is_chain_valid()
            verifier = session.get('user_name', 'Guest')
            db.verification_logs.insert_one({
                "certificate_id":     str(cert_doc['_id']),
                "register_number":    register_number,
                "verified_by":        verifier,
                "authenticity_score": cert_doc.get('authenticity_score', 0),
                "verdict":            cert_doc.get('verdict', 'UNKNOWN'),
                "result":             'Verified' if bc_valid else 'Blockchain Invalid',
                "timestamp":          datetime.utcnow(),
            })
            flash('Verification completed successfully.', 'success')
            return redirect(url_for('result', cert_id=str(cert_doc['_id'])))
        else:
            flash('Certificate not found in the Ledger.', 'error')

    return render_template('verify.html')


# ─────────────────────────────────────────────────────────────────────────────
# AI Analysis (standalone demo page)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/ai_analysis', methods=['GET', 'POST'])
def ai_analysis_page():
    if request.method == 'POST':
        file = request.files.get('certificate_file')
        if file and file.filename != '':
            filename  = secure_filename(file.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], "ai_temp_" + filename)
            file.save(temp_path)

            ai_result = analyze_certificate(temp_path, blockchain_obj=blockchain)

            try:
                os.remove(temp_path)
            except Exception:
                pass

            return jsonify(ai_result)
    return render_template('ai_analysis.html')


# ─────────────────────────────────────────────────────────────────────────────
# Result page
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/result/<cert_id>')
def result(cert_id):
    db = get_db()
    try:
        cert_doc = db.certificates.find_one({"_id": ObjectId(cert_id)})
    except Exception:
        cert_doc = None

    if not cert_doc:
        return render_template('404.html'), 404

    cert = _cert_to_dict(cert_doc)

    # QR path
    qr_filename = f"{cert.get('register_number', cert_id)}.png"
    qr_path     = url_for('static', filename=f'qrcodes/{qr_filename}')

    bc_valid    = blockchain.is_chain_valid()

    # Verify block-level hash match
    stored_bc_hash = cert.get('blockchain_hash', '')
    hash_match = any(
        b.hash == stored_bc_hash
        for b in blockchain.chain
        if isinstance(b.data, dict)
    )

    ai_breakdown = cert.get('ai_breakdown', {})
    ai_entities  = cert.get('ai_entities', {})
    fake_reasons = cert.get('fake_reasons', [])

    return render_template(
        'result.html',
        cert=cert,
        qr_path=qr_path,
        bc_valid=bc_valid,
        hash_match=hash_match,
        ai_breakdown=ai_breakdown,
        ai_entities=ai_entities,
        fake_reasons=fake_reasons,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Download PDF Report
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/download_report/<cert_id>')
def download_report(cert_id):
    db = get_db()
    try:
        cert_doc = db.certificates.find_one({"_id": ObjectId(cert_id)})
    except Exception:
        cert_doc = None

    if not cert_doc:
        return "Not found", 404

    cert = _cert_to_dict(cert_doc)
    report_path = os.path.join(REPORTS_FOLDER, f"Report_{cert.get('register_number', cert_id)}.pdf")
    generate_pdf_report(cert, report_path)
    return send_file(report_path, as_attachment=True)


# ─────────────────────────────────────────────────────────────────────────────
# Blockchain Explorer
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/explorer')
def explorer():
    blocks = blockchain.get_all_blocks()
    return render_template('explorer.html', blocks=blocks, bc_valid=blockchain.is_chain_valid())


# ─────────────────────────────────────────────────────────────────────────────
# Search (Admin only)
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/search', methods=['GET'])
def search():
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized Access.', 'error')
        return redirect(url_for('dashboard'))

    query = request.args.get('q', '').strip()
    db    = get_db()

    if query:
        regex = {"$regex": query, "$options": "i"}
        raw_certs = list(db.certificates.find({
            "$or": [
                {"student_name":    regex},
                {"register_number": regex},
                {"course":          regex},
                {"university_name": regex},
                {"certificate_hash": regex},
            ]
        }).limit(50))
    else:
        raw_certs = list(db.certificates.find().sort("uploaded_at", -1).limit(50))

    certs = [_cert_to_dict(c) for c in raw_certs]
    return render_template('search.html', certs=certs, query=query)


# ─────────────────────────────────────────────────────────────────────────────
# Verification History
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/history')
def history():
    if 'user_id' not in session:
        flash('Please login to view history.', 'warning')
        return redirect(url_for('login'))

    db   = get_db()
    raw  = list(db.verification_logs.find().sort("timestamp", -1))
    logs = []
    for log in raw:
        log['id'] = _oid(log.pop('_id', ''))
        logs.append(log)

    return render_template('history.html', logs=logs)


# ─────────────────────────────────────────────────────────────────────────────
# Export endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.route('/export/<data_type>')
def export_data(data_type):
    if 'user_id' not in session or session.get('user_role') != 'admin':
        flash('Unauthorized Access.', 'error')
        return redirect(url_for('dashboard'))

    export_format = request.args.get('format', 'csv').lower()
    db            = get_db()

    if data_type == 'users':
        raw   = list(db.users.find({}, {"password": 0, "verification_token": 0}))
        rows  = [[str(u.get('_id','')), u.get('name',''), u.get('email',''),
                  u.get('role',''), u.get('is_verified',''), str(u.get('created_at',''))] for u in raw]
        headers       = ['ID', 'Name', 'Email', 'Role', 'Is Verified', 'Created At']
        filename_base = "users_export"
        title         = "Users Data Export"

    elif data_type == 'certificates':
        raw  = list(db.certificates.find({}, {
            "_id":1,"student_name":1,"register_number":1,"course":1,
            "year":1,"authenticity_score":1,"ai_status":1,"verdict":1
        }))
        rows  = [[str(c.get('_id','')), c.get('student_name',''), c.get('register_number',''),
                  c.get('course',''), c.get('year',''), c.get('authenticity_score',''),
                  c.get('ai_status',''), c.get('verdict','')] for c in raw]
        headers       = ['ID', 'Student Name', 'Reg Number', 'Course', 'Year', 'AI Score', 'AI Status', 'Verdict']
        filename_base = "certificates_export"
        title         = "Certificates Data Export"

    elif data_type == 'logs':
        raw  = list(db.verification_logs.find())
        rows = [[str(l.get('_id','')), l.get('certificate_id',''), l.get('verified_by',''),
                 l.get('authenticity_score',''), l.get('verdict',''),
                 l.get('result',''), str(l.get('timestamp',''))] for l in raw]
        headers       = ['ID', 'Cert ID', 'Verified By', 'AI Score', 'Verdict', 'Result', 'Timestamp']
        filename_base = "verification_logs_export"
        title         = "Verification Logs Export"

    else:
        return "Invalid export type", 400

    if export_format == 'pdf':
        report_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{filename_base}.pdf")
        generate_pdf_table(title, headers, rows, report_path)
        return send_file(report_path, as_attachment=True, download_name=f"{filename_base}.pdf")
    else:
        si = StringIO()
        cw = csv.writer(si)
        cw.writerow(headers)
        cw.writerows(rows)
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename={filename_base}.csv"
        output.headers["Content-type"] = "text/csv"
        return output


# ─────────────────────────────────────────────────────────────────────────────
# Error handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(429)
def ratelimit_handler(e):
    flash("Too many login attempts. Please try again in 1 minute.", "error")
    return redirect(url_for('login'))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=5000)
