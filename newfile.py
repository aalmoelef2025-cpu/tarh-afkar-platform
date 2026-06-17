from flask import Flask, request, redirect, session, send_from_directory, render_template_string, jsonify
import os, sqlite3, time, socket, secrets
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "tarh_afkar.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
SECRET_FILE = os.path.join(BASE_DIR, ".secret_key")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_MB = 5
ONLINE_SECONDS = 90
CATEGORIES = ["عام", "تاريخي", "ديني", "اجتماعي", "تطوير الذات", "ترفيهي", "رياضة", "علمي", "تقني"]

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def load_secret_key():
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(key)
    return key

app = Flask(__name__)
app.secret_key = load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_MB * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.permanent_session_lifetime = timedelta(days=30)

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def column_exists(con, table, column):
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)

def add_column_if_missing(con, table, column, definition):
    if not column_exists(con, table, column):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS articles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        image TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS likes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        UNIQUE(article_id, user_id),
        FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        comment TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        body TEXT NOT NULL,
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(receiver_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    add_column_if_missing(con, "users", "bio", "TEXT DEFAULT ''")
    add_column_if_missing(con, "users", "avatar", "TEXT")
    add_column_if_missing(con, "users", "last_seen", "INTEGER DEFAULT 0")
    add_column_if_missing(con, "users", "created_at", "TEXT DEFAULT ''")
    add_column_if_missing(con, "users", "full_name", "TEXT DEFAULT ''")
    add_column_if_missing(con, "articles", "category", "TEXT DEFAULT 'عام'")
    add_column_if_missing(con, "articles", "views", "INTEGER DEFAULT 0")

    con.execute("CREATE INDEX IF NOT EXISTS idx_articles_user ON articles(user_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_id)")
    con.commit()
    con.close()

init_db()

STYLE = """
<style>
*{box-sizing:border-box}
body{font-family:Arial,Tahoma,sans-serif;background:#eef2f7;margin:0;direction:rtl;color:#172033}
a{color:#4f46e5;text-decoration:none;font-weight:bold}
nav{background:white;padding:13px 16px;box-shadow:0 2px 12px #d7dce5;display:flex;gap:12px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:10}
.logo{font-size:22px;color:#4f46e5}.container{max-width:1050px;margin:20px auto;padding:12px}
.card{background:white;padding:18px;border-radius:18px;margin-bottom:16px;box-shadow:0 2px 12px #dce1ea}
input,textarea,select{width:100%;padding:12px;margin:8px 0;border:1px solid #cbd5e1;border-radius:12px;font-size:16px;background:white}
textarea{resize:vertical;line-height:1.8}
button,.btn{background:#4f46e5;color:white;border:0;padding:10px 17px;border-radius:12px;cursor:pointer;font-size:15px;display:inline-block}
button:hover,.btn:hover{background:#4338ca;color:white}
.btn-light{background:#eef2ff;color:#3730a3}.btn-danger{background:#e11d48}
img{max-width:100%;border-radius:14px;margin-top:10px}
.small{color:#64748b;font-size:14px}.actions{display:flex;gap:10px;align-items:center;margin-top:10px;flex-wrap:wrap}
.comment{background:#f1f5f9;padding:10px;border-radius:10px;margin-top:8px;line-height:1.7}
.article-content{white-space:pre-wrap;line-height:1.9}.notice{background:#eef2ff;border:1px solid #c7d2fe;color:#312e81}
.error{background:#fff1f2;border:1px solid #fecdd3;color:#9f1239}
.profile-row{display:flex;gap:14px;align-items:center}.avatar{width:58px;height:58px;border-radius:50%;object-fit:cover;background:#e2e8f0;border:2px solid #eef2ff}
.avatar-big{width:110px;height:110px;border-radius:50%;object-fit:cover;background:#e2e8f0}
.online{color:#16a34a;font-weight:bold}.offline{color:#64748b}
.message{padding:10px 12px;border-radius:14px;margin:8px 0;max-width:80%;line-height:1.7}
.mine{background:#4f46e5;color:white;margin-right:auto}.theirs{background:#f1f5f9;margin-left:auto}
.chat-box{max-height:430px;overflow:auto;padding:10px;background:#fbfdff;border-radius:14px;border:1px solid #e2e8f0}
.badge{background:#ef4444;color:white;border-radius:999px;padding:2px 7px;font-size:12px}
.category-badge{background:#14b8a6;color:white;border-radius:999px;padding:3px 8px;font-size:13px;font-weight:normal}
.searchbar{display:flex;gap:8px}.searchbar input{margin:0}
@media(max-width:760px){.container{margin:8px auto;padding:10px}nav{gap:9px;font-size:14px}.logo{width:100%}.card{padding:14px}.message{max-width:92%}.searchbar{display:block}}
</style>
"""

def safe_text(text, limit):
    return (text or "").strip()[:limit]

def is_online(user_row):
    return bool(user_row) and int(time.time()) - int(user_row["last_seen"] or 0) <= ONLINE_SECONDS

def online_label(user_row):
    return "أونلاين" if is_online(user_row) else "غير متصل"

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    original = secure_filename(file_storage.filename)
    if not original or not allowed_file(original):
        return "__BAD_TYPE__"
    ext = original.rsplit(".", 1)[1].lower()
    new_name = f"{int(time.time())}_{secrets.token_hex(8)}.{ext}"
    file_storage.save(os.path.join(UPLOAD_FOLDER, new_name))
    return new_name

def current_user(update_seen=True):
    user_id = session.get("user_id")
    if not user_id:
        return None
    con = db()
    if update_seen:
        con.execute("UPDATE users SET last_seen=? WHERE id=?", (int(time.time()), user_id))
        con.commit()
    user = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    con.close()
    return user

def unread_count(user_id):
    con = db()
    count = con.execute("SELECT COUNT(*) AS c FROM messages WHERE receiver_id=? AND is_read=0", (user_id,)).fetchone()["c"]
    con.close()
    return count

def generate_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]

def navbar_html():
    return """
    <nav>
        <b class="logo">💡 طرح الأفكار</b>
        <a href="/">الرئيسية</a>
        <a href="/users">الأعضاء</a>
        <a href="/about">عن المنصة</a>
        {% if user %}
            <a href="/publish">نشر مقال</a>
            <a href="/my">مقالاتي</a>
            <a href="/messages">المحادثات {% if unread %}<span class="badge">{{ unread }}</span>{% endif %}</a>
            <a href="/profile">بروفايلي</a>
            <a href="/logout">خروج</a>
            <span class="small">مرحباً، {{ user.full_name or user.username }}</span>
        {% else %}
            <a href="/login">دخول</a>
            <a href="/register">حساب جديد</a>
        {% endif %}
    </nav>
    """

def render_page(body, status=200, **context):
    user = context.pop("user", current_user())
    unread = unread_count(user["id"]) if user else 0
    html = STYLE + navbar_html() + body
    return render_template_string(
        html,
        user=user,
        unread=unread,
        csrf_token=generate_csrf_token(),
        is_online=is_online,
        online_label=online_label,
        CATEGORIES=CATEGORIES,
        **context
    ), status

def message_page(title, message, status=200, error=False):
    return render_page("""
    <div class="container">
        <div class="card {{ 'error' if error else 'notice' }}">
            <h2>{{ title }}</h2>
            <p>{{ message }}</p>
            <a href="/">الرجوع للرئيسية</a>
        </div>
    </div>
    """, status=status, title=title, message=message, error=error)

def login_required():
    user = current_user()
    if not user:
        return None, redirect("/login")
    return user, None

def get_lan_ip():
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        if sock:
            sock.close()

@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            return message_page("خطأ أمني", "الطلب غير صالح. حدّث الصفحة وجرب مرة ثانية.", 403, True)

@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

@app.errorhandler(413)
def file_too_large(error):
    return message_page("الملف كبير", f"أقصى حجم للصورة {MAX_IMAGE_MB}MB.", 413, True)

@app.errorhandler(404)
def not_found(error):
    return message_page("الصفحة غير موجودة", "الرابط غير صحيح أو الصفحة انحذفت.", 404, True)

@app.route("/")
def home():
    user = current_user()
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", "").strip()

    con = db()
    params = []
    where = []

    if cat in CATEGORIES:
        where.append("articles.category=?")
        params.append(cat)

    if q:
        p = f"%{q}%"
        where.append("(users.username LIKE ? OR users.full_name LIKE ? OR articles.title LIKE ? OR articles.content LIKE ?)")
        params.extend([p, p, p, p])

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    articles = con.execute(f"""
        SELECT articles.*, users.username, users.full_name, users.avatar, users.last_seen,
        (SELECT COUNT(*) FROM likes WHERE likes.article_id=articles.id) AS likes_count,
        (SELECT COUNT(*) FROM comments WHERE comments.article_id=articles.id) AS comments_count
        FROM articles
        JOIN users ON users.id=articles.user_id
        {where_sql}
        ORDER BY articles.id DESC
    """, params).fetchall()

    con.close()

    return render_page("""
    <div class="container">
        <div class="card" style="display:flex;gap:10px;overflow-x:auto;white-space:nowrap">
            <a class="btn {% if not cat %}mine{% else %}btn-light{% endif %}" href="/">الكل</a>
            {% for c in CATEGORIES %}
                <a class="btn {% if cat == c %}mine{% else %}btn-light{% endif %}" href="/?cat={{ c }}">{{ c }}</a>
            {% endfor %}
        </div>

        <form method="get" class="card searchbar">
            {% if cat %}<input type="hidden" name="cat" value="{{ cat }}">{% endif %}
            <input name="q" placeholder="ابحث عن مقال أو ناشر" value="{{ q }}">
            <button>بحث</button>
        </form>

        {% for a in articles %}
        <div class="card">
            <div class="profile-row">
                {% if a.avatar %}<img class="avatar" src="/uploads/{{ a.avatar }}">{% else %}<div class="avatar"></div>{% endif %}
                <div>
                    <h2 style="margin:0"><a href="/article/{{ a.id }}">{{ a.title }}</a> <span class="category-badge">{{ a.category }}</span></h2>
                    <p class="small">
                        بواسطة: <a href="/user/{{ a.user_id }}">{{ a.full_name or a.username }}</a>
                        | {{ a.created_at }}
                        | 👁️ {{ a.views }}
                        | <span class="{{ 'online' if is_online(a) else 'offline' }}">{{ online_label(a) }}</span>
                    </p>
                </div>
            </div>

            <p class="article-content">{{ a.content[:700] }}{% if a.content|length > 700 %}...{% endif %}</p>
            {% if a.image %}<img src="/uploads/{{ a.image }}">{% endif %}

            <div class="actions">
                <a class="btn btn-light" href="/article/{{ a.id }}">قراءة كاملة</a>

                {% if user %}
                <form method="post" action="/like/{{ a.id }}">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                    <button>👍 إعجاب {{ a.likes_count }}</button>
                </form>
                {% else %}
                    <span>👍 {{ a.likes_count }}</span>
                {% endif %}

                <span class="small">💬 {{ a.comments_count }}</span>

                {% if user and user.id != a.user_id %}
                    <a class="btn btn-light" href="/chat/{{ a.user_id }}">مراسلة</a>
                {% endif %}

                {% if user and user.id == a.user_id %}
                    <form method="post" action="/delete_article/{{ a.id }}" onsubmit="return confirm('حذف المقال نهائياً؟')">
                        <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                        <button class="btn-danger">حذف</button>
                    </form>
                {% endif %}
            </div>
        </div>
        {% else %}
        <div class="card">لا توجد مقالات حالياً.</div>
        {% endfor %}
    </div>
    """, user=user, articles=articles, q=q, cat=cat)

@app.route("/article/<int:article_id>")
def article_details(article_id):
    me = current_user()
    con = db()
    con.execute("UPDATE articles SET views = COALESCE(views,0) + 1 WHERE id=?", (article_id,))
    con.commit()

    article = con.execute("""
        SELECT articles.*, users.username, users.full_name, users.avatar, users.last_seen
        FROM articles
        JOIN users ON users.id=articles.user_id
        WHERE articles.id=?
    """, (article_id,)).fetchone()

    if not article:
        con.close()
        return message_page("غير موجود", "المقال غير موجود.", 404, True)

    comments = con.execute("""
        SELECT comments.*, users.username
        FROM comments
        JOIN users ON users.id=comments.user_id
        WHERE comments.article_id=?
        ORDER BY comments.id ASC
    """, (article_id,)).fetchall()

    likes_count = con.execute("SELECT COUNT(*) AS c FROM likes WHERE article_id=?", (article_id,)).fetchone()["c"]
    con.close()

    share_url = request.host_url.rstrip("/") + f"/article/{article_id}"

    return render_page("""
    <div class="container">
        <div class="card">
            <div class="profile-row">
                {% if article.avatar %}<img class="avatar" src="/uploads/{{ article.avatar }}">{% else %}<div class="avatar"></div>{% endif %}
                <div>
                    <h2 style="margin:0">{{ article.title }} <span class="category-badge">{{ article.category }}</span></h2>
                    <p class="small">
                        بواسطة: <a href="/user/{{ article.user_id }}">{{ article.full_name or article.username }}</a>
                        | {{ article.created_at }}
                        | 👁️ {{ article.views }}
                    </p>
                </div>
            </div>

            <p class="article-content">{{ article.content }}</p>
            {% if article.image %}<img src="/uploads/{{ article.image }}">{% endif %}

            <div class="actions">
                <input value="{{ share_url }}" readonly onclick="this.select()">
                {% if user %}
                <form method="post" action="/like/{{ article.id }}">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                    <button>👍 إعجاب {{ likes_count }}</button>
                </form>
                {% endif %}
            </div>
        </div>

        <div class="card">
            <h3>التعليقات</h3>
            {% for c in comments %}
            <div class="comment">
                <b>{{ c.username }}</b>: {{ c.comment }}
                <div class="small">{{ c.created_at }}</div>

                {% if user and (user.id == c.user_id or user.id == article.user_id) %}
                <form method="post" action="/delete_comment/{{ c.id }}" style="margin-top:6px">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                    <button class="btn-danger">حذف التعليق</button>
                </form>
                {% endif %}
            </div>
            {% else %}
            <p class="small">لا توجد تعليقات.</p>
            {% endfor %}

            {% if user %}
            <form method="post" action="/comment/{{ article.id }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                <input name="comment" maxlength="300" placeholder="اكتب تعليقك" required>
                <button>تعليق</button>
            </form>
            {% endif %}
        </div>
    </div>
    """, user=me, article=article, comments=comments, likes_count=likes_count, share_url=share_url)

@app.route("/publish", methods=["GET", "POST"])
def publish():
    user, response = login_required()
    if response:
        return response

    if request.method == "POST":
        title = safe_text(request.form.get("title"), 120)
        content = safe_text(request.form.get("content"), 5000)
        category = request.form.get("category", "عام")

        if category not in CATEGORIES:
            category = "عام"

        if len(title) < 2 or len(content) < 5:
            return message_page("خطأ", "اكتب عنوان ومحتوى واضح.", 400, True)

        image_name = save_image(request.files.get("image"))
        if image_name == "__BAD_TYPE__":
            return message_page("نوع صورة غير مدعوم", "ارفع صورة png أو jpg أو jpeg أو gif أو webp.", 400, True)

        con = db()
        con.execute("""
            INSERT INTO articles(user_id,title,content,category,image,created_at,views)
            VALUES(?,?,?,?,?,datetime('now','localtime'),0)
        """, (user["id"], title, content, category, image_name))
        con.commit()
        con.close()
        return redirect("/")

    return render_page("""
    <div class="container">
        <div class="card">
            <h2>نشر مقال جديد</h2>
            <form method="post" enctype="multipart/form-data">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                <input name="title" maxlength="120" placeholder="عنوان المقال" required>

                <select name="category" required>
                    {% for c in CATEGORIES %}
                        <option value="{{ c }}">{{ c }}</option>
                    {% endfor %}
                </select>

                <textarea name="content" maxlength="5000" rows="10" placeholder="اكتب مقالك هنا حتى 5000 حرف" required></textarea>
                <input type="file" name="image" accept="image/png,image/jpeg,image/gif,image/webp">
                <p class="small">أقصى حجم للصورة: {{ max_mb }}MB</p>
                <button>نشر</button>
            </form>
        </div>
    </div>
    """, max_mb=MAX_IMAGE_MB)

@app.route("/my")
def my_articles():
    user, response = login_required()
    if response:
        return response

    con = db()
    articles = con.execute("SELECT * FROM articles WHERE user_id=? ORDER BY id DESC", (user["id"],)).fetchall()
    con.close()

    return render_page("""
    <div class="container">
        <h2>مقالاتي</h2>
        {% for a in articles %}
        <div class="card">
            <h3><a href="/article/{{ a.id }}">{{ a.title }}</a> <span class="category-badge">{{ a.category }}</span></h3>
            <p class="small">{{ a.created_at }} | 👁️ {{ a.views }}</p>
            <p class="article-content">{{ a.content[:500] }}{% if a.content|length > 500 %}...{% endif %}</p>
            {% if a.image %}<img src="/uploads/{{ a.image }}">{% endif %}
            <div class="actions">
                <a class="btn btn-light" href="/article/{{ a.id }}">فتح</a>
                <form method="post" action="/delete_article/{{ a.id }}" onsubmit="return confirm('حذف المقال نهائياً؟')">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                    <button class="btn-danger">حذف</button>
                </form>
            </div>
        </div>
        {% else %}
        <div class="card">ما عندك مقالات حالياً.</div>
        {% endfor %}
    </div>
    """, user=user, articles=articles)

@app.route("/user/<int:user_id>")
def public_profile(user_id):
    me = current_user()
    con = db()
    profile_user = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    articles = con.execute("SELECT * FROM articles WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    con.close()

    if not profile_user:
        return message_page("غير موجود", "هذا الحساب غير موجود.", 404, True)

    return render_page("""
    <div class="container">
        <div class="card profile-row">
            {% if profile_user.avatar %}<img class="avatar-big" src="/uploads/{{ profile_user.avatar }}">{% else %}<div class="avatar-big"></div>{% endif %}
            <div>
                <h2>{{ profile_user.full_name or profile_user.username }}</h2>
                <p class="small">@{{ profile_user.username }} | <span class="{{ 'online' if is_online(profile_user) else 'offline' }}">{{ online_label(profile_user) }}</span></p>
                <p>{{ profile_user.bio or 'لا توجد نبذة.' }}</p>
                {% if me and me.id != profile_user.id %}<a class="btn" href="/chat/{{ profile_user.id }}">إرسال رسالة</a>{% endif %}
            </div>
        </div>

        <h2>مقالات العضو</h2>
        {% for a in articles %}
        <div class="card">
            <h3><a href="/article/{{ a.id }}">{{ a.title }}</a> <span class="category-badge">{{ a.category }}</span></h3>
            <p class="small">{{ a.created_at }} | 👁️ {{ a.views }}</p>
            <p class="article-content">{{ a.content[:500] }}{% if a.content|length > 500 %}...{% endif %}</p>
        </div>
        {% else %}
        <div class="card">لا توجد مقالات.</div>
        {% endfor %}
    </div>
    """, user=me, profile_user=profile_user, articles=articles)

@app.route("/delete_article/<int:article_id>", methods=["POST"])
def delete_article(article_id):
    user, response = login_required()
    if response:
        return response

    con = db()
    article = con.execute("SELECT user_id, image FROM articles WHERE id=?", (article_id,)).fetchone()

    if not article or article["user_id"] != user["id"]:
        con.close()
        return message_page("غير مصرح", "لا تملك صلاحية حذف هذا المقال.", 403, True)

    if article["image"]:
        img_path = os.path.join(UPLOAD_FOLDER, article["image"])
        if os.path.exists(img_path):
            os.remove(img_path)

    con.execute("DELETE FROM articles WHERE id=?", (article_id,))
    con.commit()
    con.close()
    return redirect(request.referrer or "/")

@app.route("/delete_comment/<int:comment_id>", methods=["POST"])
def delete_comment(comment_id):
    user, response = login_required()
    if response:
        return response

    con = db()
    comment = con.execute("""
        SELECT comments.*, articles.user_id AS article_owner
        FROM comments
        JOIN articles ON articles.id=comments.article_id
        WHERE comments.id=?
    """, (comment_id,)).fetchone()

    if not comment or (user["id"] != comment["user_id"] and user["id"] != comment["article_owner"]):
        con.close()
        return message_page("غير مصرح", "لا تملك صلاحية حذف هذا التعليق.", 403, True)

    article_id = comment["article_id"]
    con.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    con.commit()
    con.close()
    return redirect(f"/article/{article_id}")

@app.route("/about")
def about():
    return render_page("""
    <div class="container">
        <div class="card">
            <h2>عن منصة طرح الأفكار</h2>
            <p>منصة عربية لنشر المقالات والأفكار، فيها حسابات، بروفايلات، تعليقات، إعجابات، مشاهدات، محادثات خاصة، وحالة أونلاين.</p>
        </div>
    </div>
    """)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = safe_text(request.form.get("username"), 30)
        full_name = safe_text(request.form.get("full_name"), 60)
        password = request.form.get("password", "")

        if len(username) < 3 or len(password) < 6:
            return message_page("خطأ", "اسم المستخدم 3 أحرف على الأقل، وكلمة المرور 6 أحرف على الأقل.", 400, True)

        con = db()
        try:
            con.execute("""
                INSERT INTO users(username, full_name, password, created_at, last_seen)
                VALUES(?, ?, ?, datetime('now','localtime'), ?)
            """, (username, full_name, generate_password_hash(password), int(time.time())))
            con.commit()
        except sqlite3.IntegrityError:
            con.close()
            return message_page("اسم موجود", "اسم المستخدم موجود من قبل.", 409, True)

        con.close()
        return redirect("/login")

    return render_page("""
    <div class="container">
        <div class="card">
            <h2>إنشاء حساب جديد</h2>
            <form method="post">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                <input name="full_name" maxlength="60" placeholder="الاسم الظاهر اختياري">
                <input name="username" maxlength="30" placeholder="اسم المستخدم" required>
                <input name="password" type="password" placeholder="كلمة المرور" required>
                <button>تسجيل</button>
            </form>
            <p><a href="/login">عندي حساب</a></p>
        </div>
    </div>
    """)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        con = db()
        user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        con.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            generate_csrf_token()
            current_user(update_seen=True)
            return redirect("/")

        return message_page("فشل الدخول", "بيانات الدخول غير صحيحة.", 401, True)

    return render_page("""
    <div class="container">
        <div class="card">
            <h2>تسجيل الدخول</h2>
            <form method="post">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                <input name="username" placeholder="اسم المستخدم" required>
                <input name="password" type="password" placeholder="كلمة المرور" required>
                <button>دخول</button>
            </form>
            <p><a href="/register">إنشاء حساب جديد</a></p>
        </div>
    </div>
    """)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    user, response = login_required()
    if response:
        return response

    if request.method == "POST":
        full_name = safe_text(request.form.get("full_name"), 60)
        bio = safe_text(request.form.get("bio"), 300)
        avatar = save_image(request.files.get("avatar"))

        if avatar == "__BAD_TYPE__":
            return message_page("نوع صورة غير مدعوم", "ارفع صورة png أو jpg أو jpeg أو gif أو webp.", 400, True)

        con = db()
        if avatar:
            old = con.execute("SELECT avatar FROM users WHERE id=?", (user["id"],)).fetchone()
            if old and old["avatar"]:
                old_path = os.path.join(UPLOAD_FOLDER, old["avatar"])
                if os.path.exists(old_path):
                    os.remove(old_path)
            con.execute("UPDATE users SET full_name=?, bio=?, avatar=? WHERE id=?", (full_name, bio, avatar, user["id"]))
        else:
            con.execute("UPDATE users SET full_name=?, bio=? WHERE id=?", (full_name, bio, user["id"]))

        con.commit()
        con.close()
        return redirect("/profile")

    return render_page("""
    <div class="container">
        <div class="card">
            <h2>تعديل البروفايل</h2>
            <div class="profile-row">
                {% if user.avatar %}<img class="avatar-big" src="/uploads/{{ user.avatar }}">{% else %}<div class="avatar-big"></div>{% endif %}
                <div><b>{{ user.username }}</b><p class="small">{{ online_label(user) }}</p></div>
            </div>

            <form method="post" enctype="multipart/form-data">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                <input name="full_name" maxlength="60" placeholder="الاسم الظاهر" value="{{ user.full_name or '' }}">
                <textarea name="bio" maxlength="300" rows="4" placeholder="نبذة قصيرة">{{ user.bio or '' }}</textarea>
                <input type="file" name="avatar" accept="image/png,image/jpeg,image/gif,image/webp">
                <button>حفظ التغييرات</button>
            </form>
        </div>
    </div>
    """, user=user)

@app.route("/users")
def users():
    user = current_user()
    q = request.args.get("q", "").strip()

    con = db()
    if q:
        p = f"%{q}%"
        rows = con.execute("SELECT * FROM users WHERE username LIKE ? OR full_name LIKE ? ORDER BY last_seen DESC", (p, p)).fetchall()
    else:
        rows = con.execute("SELECT * FROM users ORDER BY last_seen DESC, id DESC").fetchall()
    con.close()

    return render_page("""
    <div class="container">
        <form method="get" class="card searchbar">
            <input name="q" placeholder="ابحث عن عضو" value="{{ q }}">
            <button>بحث</button>
        </form>

        {% for u in rows %}
        <div class="card profile-row">
            {% if u.avatar %}<img class="avatar" src="/uploads/{{ u.avatar }}">{% else %}<div class="avatar"></div>{% endif %}
            <div style="flex:1">
                <h3 style="margin:0"><a href="/user/{{ u.id }}">{{ u.full_name or u.username }}</a></h3>
                <p class="small">@{{ u.username }} | <span class="{{ 'online' if is_online(u) else 'offline' }}">{{ online_label(u) }}</span></p>
                <p>{{ u.bio or '' }}</p>
            </div>
            {% if user and user.id != u.id %}
                <a class="btn" href="/chat/{{ u.id }}">مراسلة</a>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    """, user=user, rows=rows, q=q)

@app.route("/like/<int:article_id>", methods=["POST"])
def like(article_id):
    user, response = login_required()
    if response:
        return response

    con = db()
    article = con.execute("SELECT id FROM articles WHERE id=?", (article_id,)).fetchone()

    if not article:
        con.close()
        return message_page("خطأ", "المقال غير موجود.", 404, True)

    try:
        con.execute("INSERT INTO likes(article_id,user_id) VALUES(?,?)", (article_id, user["id"]))
    except sqlite3.IntegrityError:
        con.execute("DELETE FROM likes WHERE article_id=? AND user_id=?", (article_id, user["id"]))

    con.commit()
    con.close()
    return redirect(request.referrer or "/")

@app.route("/comment/<int:article_id>", methods=["POST"])
def comment(article_id):
    user, response = login_required()
    if response:
        return response

    text = safe_text(request.form.get("comment"), 300)
    if not text:
        return redirect(request.referrer or "/")

    con = db()
    article = con.execute("SELECT id FROM articles WHERE id=?", (article_id,)).fetchone()
    if article:
        con.execute("""
            INSERT INTO comments(article_id,user_id,comment,created_at)
            VALUES(?,?,?,datetime('now','localtime'))
        """, (article_id, user["id"], text))
        con.commit()
    con.close()

    return redirect(request.referrer or f"/article/{article_id}")

@app.route("/messages")
def messages():
    user, response = login_required()
    if response:
        return response

    con = db()
    conversations = con.execute("""
        SELECT u.*,
        (SELECT body FROM messages m WHERE (m.sender_id=u.id AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=u.id) ORDER BY m.id DESC LIMIT 1) AS last_message,
        (SELECT created_at FROM messages m WHERE (m.sender_id=u.id AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=u.id) ORDER BY m.id DESC LIMIT 1) AS last_time,
        (SELECT COUNT(*) FROM messages m WHERE m.sender_id=u.id AND m.receiver_id=? AND m.is_read=0) AS unread
        FROM users u
        WHERE u.id != ?
        AND EXISTS(
            SELECT 1 FROM messages m
            WHERE (m.sender_id=u.id AND m.receiver_id=?)
            OR (m.sender_id=? AND m.receiver_id=u.id)
        )
        ORDER BY last_time DESC
    """, (user["id"], user["id"], user["id"], user["id"], user["id"], user["id"], user["id"], user["id"])).fetchall()
    con.close()

    return render_page("""
    <div class="container">
        <div class="card">
            <h2>المحادثات</h2>
            <a class="btn btn-light" href="/users">ابدأ محادثة من صفحة الأعضاء</a>
        </div>

        {% for c in conversations %}
        <div class="card profile-row">
            {% if c.avatar %}<img class="avatar" src="/uploads/{{ c.avatar }}">{% else %}<div class="avatar"></div>{% endif %}
            <div style="flex:1">
                <h3 style="margin:0"><a href="/chat/{{ c.id }}">{{ c.full_name or c.username }}</a> {% if c.unread %}<span class="badge">{{ c.unread }}</span>{% endif %}</h3>
                <p class="small"><span class="{{ 'online' if is_online(c) else 'offline' }}">{{ online_label(c) }}</span> | {{ c.last_time }}</p>
                <p>{{ c.last_message }}</p>
            </div>
            <a class="btn" href="/chat/{{ c.id }}">فتح</a>
        </div>
        {% else %}
        <div class="card">ما عندك محادثات حالياً.</div>
        {% endfor %}
    </div>
    """, user=user, conversations=conversations)

@app.route("/chat/<int:other_id>", methods=["GET", "POST"])
def chat(other_id):
    user, response = login_required()
    if response:
        return response

    if other_id == user["id"]:
        return redirect("/messages")

    con = db()
    other = con.execute("SELECT * FROM users WHERE id=?", (other_id,)).fetchone()

    if not other:
        con.close()
        return message_page("غير موجود", "هذا العضو غير موجود.", 404, True)

    if request.method == "POST":
        body = safe_text(request.form.get("body"), 1000)
        if body:
            con.execute("""
                INSERT INTO messages(sender_id,receiver_id,body,created_at)
                VALUES(?,?,?,datetime('now','localtime'))
            """, (user["id"], other_id, body))
            con.commit()
        con.close()
        return redirect(f"/chat/{other_id}")

    con.execute("UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?", (other_id, user["id"]))
    con.commit()

    msgs = con.execute("""
        SELECT * FROM messages
        WHERE (sender_id=? AND receiver_id=?)
        OR (sender_id=? AND receiver_id=?)
        ORDER BY id ASC
    """, (user["id"], other_id, other_id, user["id"])).fetchall()

    con.close()

    return render_page("""
    <div class="container">
        <div class="card">
            <div class="profile-row">
                {% if other.avatar %}<img class="avatar" src="/uploads/{{ other.avatar }}">{% else %}<div class="avatar"></div>{% endif %}
                <div>
                    <h2 style="margin:0">محادثة مع {{ other.full_name or other.username }}</h2>
                    <p class="small"><span class="{{ 'online' if is_online(other) else 'offline' }}">{{ online_label(other) }}</span></p>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="chat-box" id="chatBox">
                {% for m in msgs %}
                <div class="message {{ 'mine' if m.sender_id == user.id else 'theirs' }}">
                    {{ m.body }}
                    <div class="small" style="color:inherit;opacity:.8">{{ m.created_at }}</div>
                </div>
                {% else %}
                <p class="small">ابدأ المحادثة برسالة.</p>
                {% endfor %}
            </div>

            <form method="post" class="searchbar" style="margin-top:10px">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                <input name="body" maxlength="1000" placeholder="اكتب رسالة" required>
                <button>إرسال</button>
            </form>
        </div>
    </div>

    <script>
    var box=document.getElementById('chatBox');
    if(box){box.scrollTop=box.scrollHeight;}
    </script>
    """, user=user, other=other, msgs=msgs)

@app.route("/api/online")
def api_online():
    current_user()
    con = db()
    rows = con.execute("SELECT id, username, full_name, last_seen FROM users ORDER BY last_seen DESC LIMIT 50").fetchall()
    con.close()
    return jsonify([
        {"id": r["id"], "name": r["full_name"] or r["username"], "online": is_online(r)}
        for r in rows
    ])

@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    port = 5000
    lan_ip = get_lan_ip()
    print("\n==============================")
    print("منصة طرح الأفكار اشتغلت ✅")
    print(f"افتح من نفس الهاتف: http://127.0.0.1:{port}")
    print(f"افتح من جهاز ثاني على نفس الواي فاي: http://{lan_ip}:{port}")
    print("البيانات محفوظة في tarh_afkar.db")
    print("لإيقاف السيرفر اضغط CTRL + C")
    print("==============================\n")
    app.run(host="0.0.0.0", port=port, debug=False)