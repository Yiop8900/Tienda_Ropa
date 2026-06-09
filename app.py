import os
import json
import sqlite3
import functools
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ─────────────────────────────────────────
#  App config
# ─────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "TR$2024#SecretKey!Flask"

# ─────────────────────────────────────────
#  MercadoPago — pega aquí tu Access Token
#  Obtenlo en: mercadopago.cl/developers/panel/app
# ─────────────────────────────────────────
MP_ACCESS_TOKEN = "APP_USR-878370283886681-060909-7a6fe56e83b2212623aedc67f2c0dbc7-3459079431"

# URL pública de tu sitio (solo necesaria si lo subes a un servidor).
# Déjala vacía para uso local: MercadoPago igual procesa el pago
# pero redirige a su propia página de confirmación en vez de la tuya.
# También se puede setear con la variable de entorno MP_BASE_URL
MP_BASE_URL = "https://tienda-ropa-29re.onrender.com/"

BASE_DIR      = os.path.abspath(os.path.dirname(__file__))
DATABASE      = os.path.join(BASE_DIR, "tienda.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXT   = {"png", "jpg", "jpeg", "gif", "webp"}

app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

# Credenciales admin  (cambia la contraseña antes de usar en producción)
ADMIN_USER = "admin"
ADMIN_HASH = generate_password_hash("admin123")

# ─────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────
def allowed_file(name: str) -> bool:
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Crea tablas y carga datos de ejemplo si la BD está vacía."""
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn = get_db()
    cur  = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS categorias (
            id     INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT    NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS productos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre       TEXT    NOT NULL,
            descripcion  TEXT,
            precio       REAL    NOT NULL DEFAULT 0,
            imagen       TEXT,
            categoria_id INTEGER REFERENCES categorias(id),
            stock        INTEGER NOT NULL DEFAULT 0,
            activo       INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS ordenes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre       TEXT    NOT NULL,
            telefono     TEXT    NOT NULL,
            direccion    TEXT,
            items        TEXT    NOT NULL,
            total        REAL    NOT NULL,
            estado       TEXT    NOT NULL DEFAULT 'pendiente',
            metodo_pago  TEXT    NOT NULL DEFAULT 'contra_entrega',
            fecha        DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    if cur.execute("SELECT COUNT(*) FROM categorias").fetchone()[0] == 0:
        for cat in ("Poleras", "Pantalones", "Vestidos", "Chaquetas", "Accesorios"):
            cur.execute("INSERT INTO categorias (nombre) VALUES (?)", (cat,))

    if cur.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        seed = [
            ("Polera Básica",      "Polera de algodón 100%, cómoda y versátil.",             9990,  1, 50),
            ("Polera Estampada",   "Estampado moderno, diseño exclusivo.",                   14990, 1, 30),
            ("Jeans Clásico",      "Mezclilla corte recto, durable y con estilo.",           24990, 2, 40),
            ("Pantalón Jogger",    "Corte jogger premium, perfecto para el día a día.",      19990, 2, 25),
            ("Vestido Floral",     "Tela liviana con estampado floral, ideal para verano.",  29990, 3, 20),
            ("Vestido Casual",     "Elegante y cómodo para cualquier ocasión.",              34990, 3, 15),
            ("Chaqueta Denim",     "Mezclilla resistente con un toque urbano.",              39990, 4, 20),
            ("Parka Impermeable",  "Impermeable y abrigadora para días de lluvia.",          49990, 4, 10),
            ("Cinturón de Cuero",  "Cuero legítimo, varios talles disponibles.",              9990, 5, 60),
            ("Gorro Beanie",       "Tejido abrigador con estilo urbano.",                     7990, 5, 80),
        ]
        for nombre, desc, precio, cat_id, stock in seed:
            cur.execute(
                "INSERT INTO productos (nombre, descripcion, precio, categoria_id, stock) VALUES (?,?,?,?,?)",
                (nombre, desc, precio, cat_id, stock),
            )

    conn.commit()

    # Migración: agregar metodo_pago si la tabla ya existía sin esa columna
    try:
        cur.execute("ALTER TABLE ordenes ADD COLUMN metodo_pago TEXT NOT NULL DEFAULT 'contra_entrega'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # columna ya existe

    conn.close()


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_cart_count():
    carrito = session.get("carrito", {})
    return {"cart_count": sum(v["cantidad"] for v in carrito.values())}


@app.template_filter("precio_cl")
def precio_cl(val):
    """Formatea un número como peso chileno: $9.990"""
    try:
        return f"${int(val):,}".replace(",", ".")
    except (TypeError, ValueError):
        return f"${val}"


# ─────────────────────────────────────────
#  Rutas públicas
# ─────────────────────────────────────────
@app.route("/")
def index():
    conn     = get_db()
    cat_id   = request.args.get("categoria", type=int)
    busqueda = request.args.get("busqueda", "").strip()

    query  = """
        SELECT p.*, c.nombre AS cat_nombre
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        WHERE p.activo = 1
    """
    params = []
    if cat_id:
        query  += " AND p.categoria_id = ?"
        params += [cat_id]
    if busqueda:
        query  += " AND (p.nombre LIKE ? OR p.descripcion LIKE ?)"
        params += [f"%{busqueda}%", f"%{busqueda}%"]
    query += " ORDER BY p.id"

    productos  = conn.execute(query, params).fetchall()
    categorias = conn.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()
    conn.close()

    return render_template(
        "index.html",
        productos=productos,
        categorias=categorias,
        cat_actual=cat_id,
        busqueda=busqueda,
    )


@app.route("/agregar/<int:pid>")
def agregar_carrito(pid):
    """Versión clásica (fallback sin JS)."""
    conn = get_db()
    p    = conn.execute(
        "SELECT * FROM productos WHERE id=? AND activo=1", (pid,)
    ).fetchone()
    conn.close()

    if not p:
        flash("Producto no encontrado.", "error")
        return redirect(url_for("index"))

    _add_to_cart(p)
    flash(f'"{p["nombre"]}" agregado al carrito ✓', "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/agregar-ajax/<int:pid>", methods=["POST"])
def agregar_carrito_ajax(pid):
    """Endpoint AJAX — devuelve JSON con el nuevo conteo del carrito."""
    from flask import jsonify
    conn = get_db()
    p    = conn.execute(
        "SELECT * FROM productos WHERE id=? AND activo=1", (pid,)
    ).fetchone()
    conn.close()

    if not p:
        from flask import jsonify
        return jsonify({"ok": False, "msg": "Producto no encontrado"}), 404

    _add_to_cart(p)
    cart_count = sum(v["cantidad"] for v in session.get("carrito", {}).values())
    return jsonify({"ok": True, "nombre": p["nombre"], "cart_count": cart_count})


def _add_to_cart(p) -> None:
    """Agrega o incrementa un producto en el carrito de la sesión."""
    carrito = session.get("carrito", {})
    key     = str(p["id"])
    if key in carrito:
        carrito[key]["cantidad"] += 1
    else:
        carrito[key] = {
            "id":       p["id"],
            "nombre":   p["nombre"],
            "precio":   p["precio"],
            "imagen":   p["imagen"],
            "cantidad": 1,
        }
    session["carrito"] = carrito


@app.route("/carrito")
def ver_carrito():
    carrito = session.get("carrito", {})
    total   = sum(v["precio"] * v["cantidad"] for v in carrito.values())
    return render_template("carrito.html", carrito=carrito, total=total)


@app.route("/carrito/actualizar", methods=["POST"])
def actualizar_carrito():
    pid    = request.form.get("pid")
    accion = request.form.get("accion")
    carrito = session.get("carrito", {})

    if pid in carrito:
        if accion == "mas":
            carrito[pid]["cantidad"] += 1
        elif accion == "menos":
            carrito[pid]["cantidad"] -= 1
            if carrito[pid]["cantidad"] <= 0:
                del carrito[pid]
        elif accion == "quitar":
            del carrito[pid]

    session["carrito"] = carrito
    return redirect(url_for("ver_carrito"))


@app.route("/carrito/vaciar")
def vaciar_carrito():
    session.pop("carrito", None)
    return redirect(url_for("ver_carrito"))


@app.route("/pedido", methods=["POST"])
def hacer_pedido():
    carrito = session.get("carrito", {})
    if not carrito:
        flash("Tu carrito está vacío.", "error")
        return redirect(url_for("ver_carrito"))

    nombre      = request.form.get("nombre",      "").strip()
    telefono    = request.form.get("telefono",    "").strip()
    direccion   = request.form.get("direccion",   "").strip()
    metodo_pago = request.form.get("metodo_pago", "contra_entrega")

    if not nombre or not telefono:
        flash("Nombre y teléfono son obligatorios.", "error")
        return redirect(url_for("ver_carrito"))

    items = list(carrito.values())
    total = sum(v["precio"] * v["cantidad"] for v in items)

    # ── Contra entrega: guardar inmediatamente ──────────
    if metodo_pago == "contra_entrega":
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO ordenes (nombre, telefono, direccion, items, total, metodo_pago) VALUES (?,?,?,?,?,?)",
            (nombre, telefono, direccion, json.dumps(items), total, metodo_pago),
        )
        conn.commit()
        order_id = cur.lastrowid
        conn.close()

        session.pop("carrito", None)
        return render_template(
            "pedido.html",
            nombre=nombre,
            telefono=telefono,
            direccion=direccion,
            items=items,
            total=total,
            metodo_pago="contra_entrega",
            order_id=order_id,
        )

    # ── MercadoPago: guardar en sesión, persistir solo al confirmar pago ──
    if MP_ACCESS_TOKEN == "TU_ACCESS_TOKEN_AQUI":
        flash("MercadoPago aún no está configurado. Configura el Access Token en app.py.", "error")
        return redirect(url_for("ver_carrito"))

    # Almacenar datos del pedido en sesión (no en BD todavía)
    session["pending_order"] = {
        "nombre":    nombre,
        "telefono":  telefono,
        "direccion": direccion,
        "items":     items,
        "total":     total,
    }

    try:
        import mercadopago
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

        mp_items = [
            {
                "title":       v["nombre"],
                "quantity":    v["cantidad"],
                "unit_price":  float(v["precio"]),
                "currency_id": "CLP",
            }
            for v in items
        ]

        preference_data = {
            "items": mp_items,
            "payer": {
                "name":  nombre,
                "phone": {"area_code": "", "number": telefono},
            },
            "statement_descriptor": "Tienda Ropa",
        }

        # back_urls solo funcionan con una URL pública (no localhost).
        if MP_BASE_URL:
            base = MP_BASE_URL.strip().rstrip("/")
            # Validar que sea una URL http/https bien formada antes de enviarla
            if not (base.startswith("http://") or base.startswith("https://")):
                raise RuntimeError(f"MP_BASE_URL inválida: '{base}'. Debe empezar con https://")
            preference_data["back_urls"] = {
                "success": f"{base}/pago/exitoso",
                "failure": f"{base}/pago/fallido",
                "pending": f"{base}/pago/pendiente",
            }
            preference_data["auto_return"] = "approved"
            print(f"[MP] back_urls → success: {base}/pago/exitoso")

        result   = sdk.preference().create(preference_data)
        response = result["response"]

        if result["status"] not in (200, 201):
            raise RuntimeError(response.get("message", "Error al crear preferencia"))

        # Limpiar carrito y redirigir a MercadoPago
        session.pop("carrito", None)
        return redirect(response["init_point"])

    except ImportError:
        flash("El SDK de MercadoPago no está instalado. Ejecuta: pip install mercadopago", "error")
        return redirect(url_for("ver_carrito"))
    except Exception as e:
        flash(f"Error al conectar con MercadoPago: {e}", "error")
        return redirect(url_for("ver_carrito"))


# ── Callbacks de MercadoPago ────────────────────────────
@app.route("/pago/exitoso")
def pago_exitoso():
    payment_id   = request.args.get("payment_id", "")
    pending      = session.pop("pending_order", None)

    if pending:
        # Recién aquí guardamos el pedido en la BD (pago confirmado)
        conn = get_db()
        cur  = conn.cursor()
        cur.execute(
            "INSERT INTO ordenes (nombre, telefono, direccion, items, total, metodo_pago, estado)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                pending["nombre"],
                pending["telefono"],
                pending["direccion"],
                json.dumps(pending["items"]),
                pending["total"],
                "mercadopago",
                "confirmado",
            ),
        )
        conn.commit()
        order_id = cur.lastrowid
        conn.close()

        session.pop("carrito", None)
        return render_template(
            "pedido.html",
            nombre=pending["nombre"],
            telefono=pending["telefono"],
            direccion=pending["direccion"] or "",
            items=pending["items"],
            total=pending["total"],
            metodo_pago="mercadopago",
            order_id=order_id,
            payment_id=payment_id,
        )

    flash("Pago recibido correctamente. ¡Gracias por tu compra!", "success")
    return redirect(url_for("index"))


@app.route("/pago/pendiente")
def pago_pendiente():
    # Pago pendiente: guardamos con estado pendiente para no perder la orden
    pending = session.pop("pending_order", None)
    if pending:
        conn = get_db()
        conn.execute(
            "INSERT INTO ordenes (nombre, telefono, direccion, items, total, metodo_pago, estado)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                pending["nombre"],
                pending["telefono"],
                pending["direccion"],
                json.dumps(pending["items"]),
                pending["total"],
                "mercadopago",
                "pendiente",
            ),
        )
        conn.commit()
        conn.close()
        session.pop("carrito", None)

    flash("Tu pago está en proceso. Te avisaremos cuando se confirme.", "info")
    return redirect(url_for("index"))


@app.route("/pago/fallido")
def pago_fallido():
    # Pago fallido: descartar pending_order, el carrito se mantiene para reintentar
    session.pop("pending_order", None)
    flash("El pago no pudo procesarse. Intenta nuevamente o elige pago contra entrega.", "error")
    return redirect(url_for("ver_carrito"))


# ─────────────────────────────────────────
#  Rutas admin
# ─────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if u == ADMIN_USER and check_password_hash(ADMIN_HASH, p):
            session["admin"] = True
            flash("Bienvenido al panel de administración.", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("admin/login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()
    stats = {
        "total_productos":  conn.execute("SELECT COUNT(*) FROM productos WHERE activo=1").fetchone()[0],
        "total_categorias": conn.execute("SELECT COUNT(*) FROM categorias").fetchone()[0],
        "sin_stock":        conn.execute("SELECT COUNT(*) FROM productos WHERE stock=0 AND activo=1").fetchone()[0],
        "total_ordenes":    conn.execute("SELECT COUNT(*) FROM ordenes").fetchone()[0],
    }
    recientes = conn.execute(
        "SELECT p.*, c.nombre AS cat_nombre FROM productos p "
        "LEFT JOIN categorias c ON p.categoria_id=c.id ORDER BY p.id DESC LIMIT 5"
    ).fetchall()
    ultimas_ordenes = conn.execute(
        "SELECT * FROM ordenes ORDER BY fecha DESC LIMIT 5"
    ).fetchall()
    conn.close()

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        recientes=recientes,
        ultimas_ordenes=ultimas_ordenes,
    )


@app.route("/admin/productos")
@admin_required
def admin_productos():
    conn = get_db()
    productos = conn.execute(
        "SELECT p.*, c.nombre AS cat_nombre FROM productos p "
        "LEFT JOIN categorias c ON p.categoria_id=c.id ORDER BY p.id DESC"
    ).fetchall()
    conn.close()
    return render_template("admin/productos.html", productos=productos)


@app.route("/admin/producto/nuevo", methods=["GET", "POST"])
@admin_required
def admin_nuevo_producto():
    conn       = get_db()
    categorias = conn.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()

    if request.method == "POST":
        nombre      = request.form.get("nombre",      "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        precio      = request.form.get("precio",      "0")
        cat_id      = request.form.get("categoria_id") or None
        stock       = request.form.get("stock",       "0")
        activo      = 1 if request.form.get("activo") else 0

        imagen_nombre = None
        f = request.files.get("imagen")
        if f and f.filename and allowed_file(f.filename):
            fname = secure_filename(f.filename)
            dest  = os.path.join(UPLOAD_FOLDER, fname)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            f.save(dest)
            imagen_nombre = fname

        try:
            precio = float(precio)
            stock  = int(stock)
        except ValueError:
            flash("Precio o stock no válidos.", "error")
            conn.close()
            return render_template("admin/form_producto.html", categorias=categorias, producto=None)

        if not nombre:
            flash("El nombre es obligatorio.", "error")
            conn.close()
            return render_template("admin/form_producto.html", categorias=categorias, producto=None)

        conn.execute(
            "INSERT INTO productos (nombre, descripcion, precio, imagen, categoria_id, stock, activo)"
            " VALUES (?,?,?,?,?,?,?)",
            (nombre, descripcion, precio, imagen_nombre, cat_id, stock, activo),
        )
        conn.commit()
        conn.close()
        flash(f'Producto "{nombre}" creado exitosamente.', "success")
        return redirect(url_for("admin_productos"))

    conn.close()
    return render_template("admin/form_producto.html", categorias=categorias, producto=None)


@app.route("/admin/producto/<int:pid>/editar", methods=["GET", "POST"])
@admin_required
def admin_editar_producto(pid):
    conn       = get_db()
    producto   = conn.execute("SELECT * FROM productos WHERE id=?", (pid,)).fetchone()
    categorias = conn.execute("SELECT * FROM categorias ORDER BY nombre").fetchall()

    if not producto:
        flash("Producto no encontrado.", "error")
        conn.close()
        return redirect(url_for("admin_productos"))

    if request.method == "POST":
        nombre      = request.form.get("nombre",      "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        precio      = request.form.get("precio",      "0")
        cat_id      = request.form.get("categoria_id") or None
        stock       = request.form.get("stock",       "0")
        activo      = 1 if request.form.get("activo") else 0

        imagen_nombre = producto["imagen"]
        f = request.files.get("imagen")
        if f and f.filename and allowed_file(f.filename):
            fname = secure_filename(f.filename)
            dest  = os.path.join(UPLOAD_FOLDER, fname)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            f.save(dest)
            imagen_nombre = fname

        try:
            precio = float(precio)
            stock  = int(stock)
        except ValueError:
            flash("Precio o stock no válidos.", "error")
            conn.close()
            return render_template("admin/form_producto.html", categorias=categorias, producto=producto)

        conn.execute(
            "UPDATE productos SET nombre=?, descripcion=?, precio=?, imagen=?,"
            " categoria_id=?, stock=?, activo=? WHERE id=?",
            (nombre, descripcion, precio, imagen_nombre, cat_id, stock, activo, pid),
        )
        conn.commit()
        conn.close()
        flash(f'Producto "{nombre}" actualizado.', "success")
        return redirect(url_for("admin_productos"))

    conn.close()
    return render_template("admin/form_producto.html", categorias=categorias, producto=producto)


@app.route("/admin/producto/<int:pid>/eliminar", methods=["POST"])
@admin_required
def admin_eliminar_producto(pid):
    conn = get_db()
    p    = conn.execute("SELECT nombre FROM productos WHERE id=?", (pid,)).fetchone()
    if p:
        conn.execute("UPDATE productos SET activo=0 WHERE id=?", (pid,))
        conn.commit()
        flash(f'Producto "{p["nombre"]}" eliminado.', "success")
    conn.close()
    return redirect(url_for("admin_productos"))


@app.route("/admin/categorias")
@admin_required
def admin_categorias():
    conn = get_db()
    categorias = conn.execute("""
        SELECT c.*, COUNT(p.id) AS total_productos
        FROM categorias c
        LEFT JOIN productos p ON c.id=p.categoria_id AND p.activo=1
        GROUP BY c.id ORDER BY c.nombre
    """).fetchall()
    conn.close()
    return render_template("admin/categorias.html", categorias=categorias)


@app.route("/admin/categoria/nueva", methods=["POST"])
@admin_required
def admin_nueva_categoria():
    nombre = request.form.get("nombre", "").strip()
    if nombre:
        try:
            conn = get_db()
            conn.execute("INSERT INTO categorias (nombre) VALUES (?)", (nombre,))
            conn.commit()
            conn.close()
            flash(f'Categoría "{nombre}" creada.', "success")
        except sqlite3.IntegrityError:
            flash("Ya existe una categoría con ese nombre.", "error")
    return redirect(url_for("admin_categorias"))


@app.route("/admin/categoria/<int:cid>/eliminar", methods=["POST"])
@admin_required
def admin_eliminar_categoria(cid):
    conn = get_db()
    c    = conn.execute("SELECT nombre FROM categorias WHERE id=?", (cid,)).fetchone()
    if c:
        conn.execute("DELETE FROM categorias WHERE id=?", (cid,))
        conn.commit()
        flash(f'Categoría "{c["nombre"]}" eliminada.', "success")
    conn.close()
    return redirect(url_for("admin_categorias"))


@app.route("/admin/ordenes")
@admin_required
def admin_ordenes():
    conn    = get_db()
    ordenes = conn.execute("SELECT * FROM ordenes ORDER BY fecha DESC").fetchall()
    conn.close()
    return render_template("admin/ordenes.html", ordenes=ordenes)


@app.route("/admin/orden/<int:oid>/estado", methods=["POST"])
@admin_required
def admin_cambiar_estado(oid):
    estado = request.form.get("estado")
    if estado in ("pendiente", "confirmado", "enviado", "entregado", "cancelado"):
        conn = get_db()
        conn.execute("UPDATE ordenes SET estado=? WHERE id=?", (estado, oid))
        conn.commit()
        conn.close()
        flash("Estado del pedido actualizado.", "success")
    return redirect(url_for("admin_ordenes"))


if __name__ == "__main__":
    init_db()
    print("\n  ✔  Tienda Ropa iniciada")
    print("  →  Tienda:  http://localhost:5000")
    print("  →  Admin:   http://localhost:5000/admin")
    print("  →  Usuario: admin  |  Contraseña: admin123\n")
    app.run(debug=True, port=5000)
