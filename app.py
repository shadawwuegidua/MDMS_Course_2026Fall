"""Flask pages and APIs for the first-stage MongoDB survey project."""

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from bson import ObjectId
from dotenv import load_dotenv
from flask import (
    Flask, abort, g, jsonify, redirect, render_template, request, session, url_for,
)
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, init_db
from logic import (
    ValidationError, build_statistics, next_question_id, normalize_questions,
    validate_answer, validate_submission,
)

LOCAL_TIMEZONE = timezone(timedelta(hours=8))


def now_utc():
    return datetime.now(timezone.utc)


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                abort(401, description="请先登录。")
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def object_id(value):
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        abort(404, description="问卷不存在，或你无权访问。")
    return ObjectId(value)


def find_survey(survey_id, *, owner=False):
    query = {"_id": object_id(survey_id)}
    if owner:
        query["owner_id"] = g.user["_id"]
    survey = get_db().surveys.find_one(query)
    if survey is None:
        abort(404, description="问卷不存在，或你无权访问。")
    return survey


def require_open(survey):
    if survey["status"] != "published":
        abort(409, description="问卷尚未发布或已经关闭，无法填写。")
    if survey["deadline"] is not None and now_utc() >= survey["deadline"]:
        abort(409, description="问卷已截止，无法继续提交。")


def iso_date(value):
    return value.isoformat() if value is not None else None


def survey_json(survey):
    return {
        "id": str(survey["_id"]), "title": survey["title"],
        "description": survey["description"], "status": survey["status"],
        "is_anonymous": survey["is_anonymous"],
        "allow_multiple": survey["allow_multiple"],
        "deadline": iso_date(survey["deadline"]),
        "questions": survey["questions"],
        "created_at": iso_date(survey["created_at"]),
        "updated_at": iso_date(survey["updated_at"]),
    }


def json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(400, description="请求内容必须是 JSON 对象。")
    return body


def parse_deadline(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError("截止时间格式不正确。")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=LOCAL_TIMEZONE)
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValidationError("截止时间格式不正确。") from None


def survey_fields(body):
    title = body.get("title", "")
    description = body.get("description", "")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
        raise ValidationError("问卷标题需为 1—200 个字符。")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValidationError("问卷说明最多 5000 个字符。")
    for name in ("is_anonymous", "allow_multiple"):
        if name in body and not isinstance(body[name], bool):
            raise ValidationError("匿名和重复填写设置必须是布尔值。")
    return {
        "title": title.strip(), "description": description.strip(),
        "is_anonymous": body.get("is_anonymous", False),
        "allow_multiple": body.get("allow_multiple", False),
        "deadline": parse_deadline(body.get("deadline")),
        "questions": normalize_questions(body.get("questions", [])),
    }


def safe_next(value):
    if isinstance(value, str) and value.startswith("/") and not value.startswith("//") and "\\" not in value and not any(ord(c) < 32 for c in value):
        try:
            parts = urlsplit(value)
        except ValueError:
            return url_for("dashboard")
        if not parts.netloc and not parts.scheme:
            return value
    return url_for("dashboard")


def format_answer(question, value):
    if value is None:
        return "未作答或已跳过"
    labels = {option["id"]: option["text"] for option in question["options"]}
    if question["type"] == "single":
        return labels.get(value, str(value))
    if question["type"] == "multiple":
        return "、".join(labels.get(item, str(item)) for item in value)
    return str(value)


def statistics_for(survey):
    responses = list(get_db().responses.find({"survey_id": survey["_id"]}).sort("submitted_at", -1))
    result = build_statistics(survey, responses)
    selected = request.args.get("question_id", "")
    if selected:
        result["questions"] = [item for item in result["questions"] if item["id"] == selected]
        if not result["questions"]:
            abort(404, description="题目不存在。")
    names = {}
    if not survey["is_anonymous"]:
        ids = list({item["respondent_id"] for item in responses})
        names = {item["_id"]: item["username"] for item in get_db().users.find({"_id": {"$in": ids}}, {"username": 1})}
    result["responses"] = [
        {
            "id": str(item["_id"]),
            "respondent": "匿名" if survey["is_anonymous"] else names.get(item["respondent_id"], "账号不可用"),
            "submitted_at": iso_date(item["submitted_at"]),
            "answers": {key: value for key, value in item["answers"].items() if not selected or key == selected},
        }
        for item in responses
    ]
    return result


def create_app(test_config=None):
    load_dotenv(Path(__file__).with_name(".env"))
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
        MONGO_URI=os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/"),
        MONGO_DB=os.getenv("MONGO_DB", "survey_stage1"),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    init_db(app)

    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        user_id = session.get("user_id")
        if isinstance(user_id, str) and ObjectId.is_valid(user_id):
            g.user = get_db().users.find_one({"_id": ObjectId(user_id)})
        if user_id and g.user is None:
            session.clear()
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            provided = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not expected or not re.fullmatch(r"[0-9a-f]{64}", str(provided)) or not secrets.compare_digest(str(provided), str(expected)):
                abort(400, description="页面验证已失效，请刷新页面后重试。")

    @app.context_processor
    def template_helpers():
        return {"csrf_token": csrf_token, "format_answer": format_answer}

    @app.template_filter("localtime")
    def localtime(value):
        if not value:
            return "不设截止时间"
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.astimezone(LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M")

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return render_template("error.html", message=error.description, code=error.code), error.code

    @app.errorhandler(ValidationError)
    def validation_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=str(error), question_id=getattr(error, "question_id", None)), 400
        return render_template("error.html", message=str(error), code=400), 400

    @app.errorhandler(PyMongoError)
    def database_error(error):
        app.logger.exception("Database operation failed")
        if request.path.startswith("/api/"):
            return jsonify(error="数据库暂时不可用，请稍后重试。"), 503
        return render_template("error.html", message="数据库暂时不可用，请稍后重试。", code=503), 503

    @app.get("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.get("/health")
    def health():
        try:
            get_db().command("ping")
        except PyMongoError:
            return jsonify(status="error", database="unavailable"), 503
        return jsonify(status="ok", database="connected")

    @app.get("/api/session")
    def session_info():
        user = {"id": str(g.user["_id"]), "username": g.user["username"]} if g.user else None
        return jsonify(user=user, csrf_token=csrf_token())

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "GET":
            return redirect(url_for("dashboard")) if g.user else render_template("auth.html", mode="register", error=None)
        username, password = request.form.get("username", "").strip(), request.form.get("password", "")
        error = None
        if not re.fullmatch(r"[\w.-]{3,40}", username):
            error = "用户名需为 3—40 个字符，可用中文、字母、数字、下划线、点和短横线。"
        elif not 6 <= len(password) <= 128:
            error = "密码需为 6—128 个字符。"
        if error:
            return render_template("auth.html", mode="register", error=error), 400
        try:
            user_id = get_db().users.insert_one({"username": username, "password_hash": generate_password_hash(password), "created_at": now_utc()}).inserted_id
        except DuplicateKeyError:
            return render_template("auth.html", mode="register", error="用户名已被使用。"), 400
        session.clear()
        session["user_id"] = str(user_id)
        return redirect(safe_next(request.form.get("next")))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return redirect(url_for("dashboard")) if g.user else render_template("auth.html", mode="login", error=None)
        user = get_db().users.find_one({"username": request.form.get("username", "").strip()})
        password = request.form.get("password", "")
        if user is None or len(password) > 128 or not check_password_hash(user["password_hash"], password):
            return render_template("auth.html", mode="login", error="用户名或密码不正确。"), 400
        session.clear()
        session["user_id"] = str(user["_id"])
        return redirect(safe_next(request.form.get("next")))

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        surveys = list(get_db().surveys.find({"owner_id": g.user["_id"]}).sort("created_at", -1))
        return render_template("dashboard.html", surveys=surveys, now=now_utc())

    @app.get("/surveys/new")
    @login_required
    def new_survey():
        return render_template("editor.html", survey=None)

    @app.get("/surveys/<survey_id>/edit")
    @login_required
    def edit_survey(survey_id):
        survey = find_survey(survey_id, owner=True)
        if survey["status"] != "draft":
            abort(409, description="发布后题目与规则固定，可回到列表调整截止时间或关闭问卷。")
        return render_template("editor.html", survey=survey_json(survey))

    @app.get("/survey/<survey_id>")
    @login_required
    def fill_survey(survey_id):
        survey = find_survey(survey_id)
        require_open(survey)
        if not survey["allow_multiple"] and get_db().responses.find_one({"survey_id": survey["_id"], "respondent_id": g.user["_id"]}):
            abort(409, description="你已经提交过这份问卷，该问卷不允许重复填写。")
        return render_template("fill.html", survey=survey_json(survey))

    @app.get("/survey/<survey_id>/thanks")
    @login_required
    def thanks(survey_id):
        survey = find_survey(survey_id)
        if not get_db().responses.find_one({"survey_id": survey["_id"], "respondent_id": g.user["_id"]}):
            return redirect(url_for("fill_survey", survey_id=survey_id))
        return render_template("thanks.html", survey=survey)

    @app.get("/surveys/<survey_id>/statistics")
    @login_required
    def statistics_page(survey_id):
        survey = find_survey(survey_id, owner=True)
        return render_template("statistics.html", survey=survey, statistics=statistics_for(survey), selected=request.args.get("question_id", ""))

    @app.get("/api/surveys")
    @login_required
    def list_surveys():
        return jsonify(surveys=[survey_json(item) for item in get_db().surveys.find({"owner_id": g.user["_id"]}).sort("created_at", -1)])

    @app.post("/api/surveys")
    @login_required
    def create_survey():
        fields = survey_fields(json_body())
        survey_id = get_db().surveys.insert_one({**fields, "owner_id": g.user["_id"], "status": "draft", "created_at": now_utc(), "updated_at": now_utc()}).inserted_id
        return jsonify(id=str(survey_id), redirect=url_for("edit_survey", survey_id=survey_id)), 201

    @app.get("/api/surveys/<survey_id>")
    @login_required
    def get_survey(survey_id):
        return jsonify(survey_json(find_survey(survey_id, owner=True)))

    @app.put("/api/surveys/<survey_id>")
    @login_required
    def update_survey(survey_id):
        survey = find_survey(survey_id, owner=True)
        if survey["status"] != "draft":
            abort(409, description="发布后不能修改题目和规则。")
        fields = survey_fields(json_body())
        result = get_db().surveys.update_one({"_id": survey["_id"], "owner_id": g.user["_id"], "status": "draft"}, {"$set": {**fields, "updated_at": now_utc()}})
        if result.matched_count != 1:
            abort(409, description="问卷状态已变化，请刷新后重试。")
        return jsonify(id=survey_id, message="草稿已保存。")

    @app.post("/api/surveys/<survey_id>/publish")
    @login_required
    def publish_survey(survey_id):
        survey = find_survey(survey_id, owner=True)
        if survey["status"] != "draft":
            abort(409, description="只有草稿可以发布。")
        if not survey["questions"]:
            raise ValidationError("至少添加一道题再发布。")
        normalize_questions(survey["questions"])
        if survey["deadline"] is not None and survey["deadline"] <= now_utc():
            raise ValidationError("发布时截止时间必须晚于当前时间。")
        # Publish exactly the question definition and deadline we just checked.
        # A concurrent draft save must finish first, or receive a conflict.
        result = get_db().surveys.update_one(
            {"_id": survey["_id"], "status": "draft", "questions": survey["questions"], "deadline": survey["deadline"]},
            {"$set": {"status": "published", "updated_at": now_utc()}},
        )
        if result.matched_count != 1:
            abort(409, description="问卷状态已变化，请刷新后重试。")
        return jsonify(id=survey_id, fill_url=url_for("fill_survey", survey_id=survey_id))

    @app.post("/api/surveys/<survey_id>/close")
    @login_required
    def close_survey(survey_id):
        survey = find_survey(survey_id, owner=True)
        if survey["status"] == "draft":
            abort(409, description="草稿还没有发布。")
        get_db().surveys.update_one({"_id": survey["_id"]}, {"$set": {"status": "closed", "updated_at": now_utc()}})
        return jsonify(id=survey_id, message="问卷已关闭。")

    @app.patch("/api/surveys/<survey_id>/deadline")
    @login_required
    def change_deadline(survey_id):
        survey = find_survey(survey_id, owner=True)
        if survey["status"] == "closed":
            abort(409, description="已关闭的问卷不能再调整截止时间。")
        deadline = parse_deadline(json_body().get("deadline"))
        result = get_db().surveys.update_one({"_id": survey["_id"], "status": {"$ne": "closed"}}, {"$set": {"deadline": deadline, "updated_at": now_utc()}})
        if result.matched_count != 1:
            abort(409, description="问卷已经关闭，请刷新后重试。")
        return jsonify(id=survey_id, deadline=iso_date(deadline))

    @app.get("/api/public/surveys/<survey_id>")
    @login_required
    def public_survey(survey_id):
        survey = find_survey(survey_id)
        require_open(survey)
        return jsonify(survey_json(survey))

    @app.post("/api/surveys/<survey_id>/responses")
    @login_required
    def submit_response(survey_id):
        survey = find_survey(survey_id)
        require_open(survey)
        answers = validate_submission(survey["questions"], json_body().get("answers"))
        response = {"survey_id": survey["_id"], "respondent_id": g.user["_id"], "single_submission": not survey["allow_multiple"], "answers": answers, "submitted_at": now_utc()}
        try:
            response_id = get_db().responses.insert_one(response).inserted_id
        except DuplicateKeyError:
            abort(409, description="你已经提交过这份问卷，该问卷不允许重复填写。")
        return jsonify(id=str(response_id), redirect=url_for("thanks", survey_id=survey_id)), 201

    @app.post("/api/surveys/<survey_id>/check-answer")
    @login_required
    def check_answer(survey_id):
        survey = find_survey(survey_id)
        require_open(survey)
        body = json_body()
        question = next((item for item in survey["questions"] if item["id"] == body.get("question_id")), None)
        if question is None:
            abort(404, description="题目不存在。")
        answer = validate_answer(question, body.get("value"))
        return jsonify(answer=answer, next_id=next_question_id(survey["questions"], question["id"], answer))

    @app.get("/api/surveys/<survey_id>/statistics")
    @login_required
    def statistics_api(survey_id):
        return jsonify(statistics_for(find_survey(survey_id, owner=True)))

    return app


if __name__ == "__main__":
    try:
        application = create_app()
    except PyMongoError as exc:
        raise SystemExit("MongoDB 连接或初始化失败。请先启动数据库并检查 .env 配置。") from exc
    application.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
