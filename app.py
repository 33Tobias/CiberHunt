from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import logging
import csv
import os
import random
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
logging.basicConfig(filename='ciberhunt.log', level=logging.INFO, format='%(asctime)s - %(message)s')
app.secret_key = 'ciberhunt_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

# Modelos
class Attack(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(50))
    type = db.Column(db.String(100))
    classification = db.Column(db.String(100))
    risk = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class BlockedIP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(50), unique=True, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(128))
    role = db.Column(db.String(10))

intentos_por_ip = {}

def registrar_ataque(ip_real, tipo, ip_simulada=None):
    ip = ip_simulada if ip_simulada else ip_real

    if ip == '127.0.0.1':
        return  # nunca bloquees localhost

    # CONTADOR
    if ip not in intentos_por_ip:
        intentos_por_ip[ip] = 1
    else:
        intentos_por_ip[ip] += 1

    # LOG DE INTENTO
    logging.info(f"[INTENTO] IP {ip} - Tipo: {tipo} - Intentos: {intentos_por_ip[ip]}")


    # CLASIFICACIÓN
    if intentos_por_ip[ip] <= 3:
        clasificacion = "Normal"
        riesgo = "Bajo"
    elif intentos_por_ip[ip] <= 6:
        clasificacion = "Advertencia"
        riesgo = "Medio"
    else:
        clasificacion = "Atacante Persistente"
        riesgo = "Alto"
        if not BlockedIP.query.filter_by(ip=ip).first():
            db.session.add(BlockedIP(ip=ip))
            logging.info(f"[ALERTA] IP bloqueada: {ip} - {tipo}")

    ataque = Attack(ip=ip, type=tipo, classification=clasificacion, risk=riesgo)
    db.session.add(ataque)
    db.session.commit()
    logging.info(f"[DETECCION] {tipo} desde IP {ip} - Clasificacion: {clasificacion}")




@app.before_request
def check_ip():
    ip = request.remote_addr

    # 👇 Asegurate de cambiar esto a tu IP real si estás en red local o producción
    if ip == '127.0.0.1':
        return  # no bloquear localhost (tu máquina)

    if BlockedIP.query.filter_by(ip=ip).first() and request.endpoint not in ('ip_blocked', 'index'):
        return redirect(url_for("ip_blocked"))


@app.route("/ip_blocked")
def ip_blocked():
    return "Tu IP ha sido bloqueada.", 403

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/xss", methods=["GET", "POST"])
def xss():
    input_text = ""
    if request.method == "POST":
        input_text = request.form['input']
        if "<script>" in input_text:
            ip_fake = f"192.168.1.{random.randint(1, 255)}"
            registrar_ataque(request.remote_addr, "XSS Detectado", ip_simulada=ip_fake)
    return render_template("xss.html", input_text=input_text)

@app.route("/phishing", methods=["GET", "POST"])
def phishing():
    if request.method == "POST":
        ip_fake = f"192.168.1.{random.randint(1, 255)}"
        registrar_ataque(request.remote_addr, "Phishing detectado", ip_simulada=ip_fake)
    return render_template("phishing.html")

@app.route("/honeypot")
def honeypot():
    ip_fake = f"192.168.1.{random.randint(1, 255)}"
    registrar_ataque(request.remote_addr, "Honeypot Visitado", ip_simulada=ip_fake)
    return render_template("hidden.html")


@app.route("/fuerza_bruta", methods=["GET", "POST"])
def fuerza_bruta():
    if 'fuerza_bruta_intentos' not in session:
        session['fuerza_bruta_intentos'] = 0

    mensaje = ""
    if request.method == "POST":
        usuario = request.form['usuario']
        contrasena = request.form['contrasena']

        if usuario == "admin" and contrasena == "1234":
            mensaje = "Acceso concedido!"
            session['fuerza_bruta_intentos'] = 0
        else:
            session['fuerza_bruta_intentos'] += 1
            ip_fake = f"192.168.1.{random.randint(1, 255)}"
            if session['fuerza_bruta_intentos'] >= 7:
                registrar_ataque(request.remote_addr, "Fuerza Bruta detectada", ip_simulada=ip_fake)
                mensaje = "Tu IP ha sido bloqueada por intentos excesivos"
            elif session['fuerza_bruta_intentos'] >= 4:
                mensaje = "⚠️ Advertencia: Credenciales incorrectas"
            else:
                mensaje = "Credenciales incorrectas"

    return render_template("fuerza_bruta.html", mensaje=mensaje)

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session['admin'] = True
            return redirect(url_for("dashboard"))
        else:
            error = "Credenciales incorrectas"
    return render_template("admin_login.html", error=error)

@app.route("/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    ataques = Attack.query.order_by(Attack.timestamp.desc()).all()
    bloqueadas = BlockedIP.query.all()
    total = len(ataques)
    xss = sum(1 for a in ataques if 'XSS' in a.type)
    phish = sum(1 for a in ataques if 'Phishing' in a.type)
    fuerza = sum(1 for a in ataques if 'Fuerza Bruta' in a.type)
    honey = sum(1 for a in ataques if 'Honeypot' in a.type)
    ultimo = ataques[0] if ataques else None
    return render_template("dashboard.html", ataques=ataques, bloqueadas=bloqueadas, total=total, xss=xss, phish=phish, fuerza=fuerza, honey=honey, ultimo=ultimo)

@app.route("/unblock/<ip>")
def unblock(ip):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    BlockedIP.query.filter_by(ip=ip).delete()
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/api/attacks")
def api_attacks():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401
    ataques = Attack.query.order_by(Attack.timestamp.desc()).all()
    data = [{"ip": a.ip, "type": a.type, "classification": a.classification, "risk": a.risk, "timestamp": a.timestamp.strftime("%Y-%m-%d %H:%M:%S")} for a in ataques]
    return jsonify(data)

@app.route("/demo")
def demo_attack():
    tipos = ["XSS Detectado", "Phishing detectado", "Fuerza Bruta detectada", "Honeypot visitado"]
    ip_fake = f"192.168.1.{random.randint(1, 255)}"
    tipo = random.choice(tipos)
    registrar_ataque(request.remote_addr, tipo, ip_simulada=ip_fake)
    return redirect(url_for('dashboard'))


@app.route("/logs")
def ver_logs():
    try:
        with open("ciberhunt.log", "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-20:]  # Mostramos las últimas 20 líneas
    except FileNotFoundError:
        lines = ["No se encontró el archivo de logs."]
    
    return render_template("logs.html", lines=lines)



if __name__ == '__main__':
    if not os.path.exists("database.db"):
        with app.app_context():
            db.create_all()
            if not User.query.filter_by(username="admin").first():
                admin = User(username="admin", password=generate_password_hash("admin123"), role="admin")
                db.session.add(admin)
                db.session.commit()
    app.run(debug=True)
