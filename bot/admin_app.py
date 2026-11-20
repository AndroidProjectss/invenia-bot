"""Веб-админка диалогов и webhook WhatsApp Cloud API."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from functools import wraps

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from bot.channels import send_channel, send_whatsapp
from bot.corpus import ROOT
from bot.service import process_incoming, select_faq
from bot.storage import (
    add_message,
    dashboard_stats,
    ensure_chat,
    get_chat,
    get_messages,
    init_db,
    list_chats,
    update_chat,
)


def _load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def create_app(test_config: dict | None = None) -> Flask:
    _load_dotenv()
    app = Flask(__name__, template_folder="templates")
    app.config.update(
        SECRET_KEY=os.environ.get("ADMIN_SECRET_KEY") or secrets.token_hex(32),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", ""),
    )
    if test_config:
        app.config.update(test_config)
    init_db()

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin_authenticated"):
                return redirect(url_for("login", next=request.full_path))
            return view(*args, **kwargs)

        return wrapped

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "invenia-admin"}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            configured = app.config["ADMIN_PASSWORD"]
            if not configured:
                flash("Сначала задайте ADMIN_PASSWORD в окружении.", "error")
            elif hmac.compare_digest(request.form.get("password", ""), configured):
                session.clear()
                session["admin_authenticated"] = True
                return redirect(request.args.get("next") or url_for("dashboard"))
            else:
                flash("Неверный пароль.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def dashboard():
        status = request.args.get("status", "")
        channel = request.args.get("channel", "")
        query = request.args.get("q", "").strip()
        chats = list_chats(status=status, channel=channel, query=query)
        selected = None
        messages = []
        raw_chat_id = request.args.get("chat", "")
        if raw_chat_id.isdigit():
            selected = get_chat(int(raw_chat_id))
        elif chats:
            selected = chats[0]
        if selected:
            messages = get_messages(selected["id"])
            update_chat(selected["id"], unread_count=0)
        return render_template(
            "admin.html",
            chats=chats,
            selected=selected,
            messages=messages,
            stats=dashboard_stats(),
            filters={"status": status, "channel": channel, "q": query},
        )

    @app.post("/chats/<int:chat_id>/reply")
    @login_required
    def reply(chat_id: int):
        chat = get_chat(chat_id)
        if not chat:
            abort(404)
        text = request.form.get("text", "").strip()
        if not text:
            flash("Ответ не может быть пустым.", "error")
        else:
            try:
                send_channel(chat["channel"], chat["external_id"], text)
            except Exception as error:  # сообщение показывается оператору, процесс не падает
                flash(f"Не удалось отправить: {error}", "error")
            else:
                add_message(chat_id, "outbound", "operator", text, mode="manual")
                update_chat(chat_id, status="open", bot_enabled=0)
                flash("Ответ отправлен. Автоответ для диалога приостановлен.", "success")
        return redirect(url_for("dashboard", chat=chat_id))

    @app.post("/chats/<int:chat_id>/status")
    @login_required
    def change_status(chat_id: int):
        if not get_chat(chat_id):
            abort(404)
        status = request.form.get("status", "open")
        if status not in {"open", "needs_human", "closed"}:
            abort(400)
        update_chat(chat_id, status=status)
        return redirect(url_for("dashboard", chat=chat_id))

    @app.post("/chats/<int:chat_id>/bot")
    @login_required
    def toggle_bot(chat_id: int):
        chat = get_chat(chat_id)
        if not chat:
            abort(404)
        enabled = 0 if chat["bot_enabled"] else 1
        update_chat(chat_id, bot_enabled=enabled, status="open")
        flash("Автоответ включён." if enabled else "Автоответ приостановлен.", "success")
        return redirect(url_for("dashboard", chat=chat_id))

    @app.get("/webhooks/whatsapp")
    def verify_whatsapp():
        expected = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge", "")
        if expected and mode == "subscribe" and hmac.compare_digest(token or "", expected):
            return challenge, 200
        abort(403)

    @app.post("/webhooks/whatsapp")
    def whatsapp_webhook():
        if not _valid_whatsapp_signature(request.get_data()):
            abort(403)
        payload = request.get_json(silent=True) or {}
        for value in _whatsapp_values(payload):
            names = {
                contact.get("wa_id"): (contact.get("profile") or {}).get("name", "")
                for contact in value.get("contacts", [])
            }
            for message in value.get("messages", []):
                sender = str(message.get("from", ""))
                if not sender:
                    continue
                interactive = message.get("interactive") or {}
                button = interactive.get("button_reply") or {}
                button_id = button.get("id", "")
                if button_id.startswith("faq:"):
                    _handle_whatsapp_faq(sender, names.get(sender, ""), message, button)
                    continue
                text = (message.get("text") or {}).get("body", "").strip()
                if not text:
                    continue
                result = process_incoming(
                    "whatsapp",
                    sender,
                    text,
                    display_name=names.get(sender, ""),
                    external_message_id=message.get("id"),
                )
                if result.get("send"):
                    send_whatsapp(sender, result["message"], result["buttons"])
        return {"status": "ok"}

    return app


def _valid_whatsapp_signature(raw_body: bytes) -> bool:
    secret = os.environ.get("WHATSAPP_APP_SECRET", "").strip()
    if not secret:
        return True
    received = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received, expected)


def _whatsapp_values(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "messages":
                yield change.get("value") or {}


def _handle_whatsapp_faq(sender: str, name: str, message: dict, button: dict) -> None:
    parts = button.get("id", "").split(":")
    if len(parts) != 3 or not parts[1].isdigit():
        return
    faq_id = int(parts[1])
    lang = parts[2] if parts[2] in {"ru", "ky"} else "ru"
    chat = ensure_chat("whatsapp", sender, display_name=name, language=lang)
    saved = add_message(
        chat["id"],
        "inbound",
        "customer",
        button.get("title", ""),
        mode="selection",
        external_message_id=message.get("id"),
    )
    if saved is None:
        return
    result = select_faq("whatsapp", sender, faq_id, lang)
    send_whatsapp(sender, result["message"])


def run_admin() -> None:
    app = create_app()
    host = os.environ.get("ADMIN_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", os.environ.get("ADMIN_PORT", "8080")))
    app.run(host=host, port=port, debug=False)
