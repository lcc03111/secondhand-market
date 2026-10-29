from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from app.extensions import db
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        nickname = request.form.get("nickname", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not username or not nickname:
            flash("请填写用户名和昵称。", "error")
        elif len(username) < 3 or len(username) > 60:
            flash("用户名长度需为 3 到 60 个字符。", "error")
        elif len(nickname) > 50:
            flash("昵称不能超过 50 个字符。", "error")
        elif len(password) < 8:
            flash("密码至少需要 8 个字符。", "error")
        elif password != confirm:
            flash("两次输入的密码不一致。", "error")
        elif User.query.filter_by(username=username).first():
            flash("该用户名已被使用。", "error")
        else:
            user = User(username=username, nickname=nickname)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("注册成功，欢迎加入拾物。", "success")
            return redirect(url_for("main.home"))
    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            login_user(user)
            flash("登录成功。", "success")
            return redirect(url_for("main.home"))
        flash("用户名或密码错误，或账号当前不可用。", "error")
    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("已退出登录。", "info")
    return redirect(url_for("auth.login"))
