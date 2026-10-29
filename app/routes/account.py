from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Notification, UserVerification

account_bp = Blueprint("account", __name__)


@account_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        phone = request.form.get("phone", "").strip()
        if not nickname or len(nickname) > 50 or len(phone) > 20:
            flash("请填写有效昵称，联系方式不能超过 20 个字符。", "error")
        else:
            current_user.nickname = nickname
            current_user.phone = phone or None
            db.session.commit()
            flash("个人资料已保存。", "success")
            return redirect(url_for("account.profile"))
    verification = UserVerification.query.filter_by(user_id=current_user.id)\
        .order_by(UserVerification.submitted_at.desc()).first()
    return render_template("account/profile.html", verification=verification)


@account_bp.route("/verification", methods=["POST"])
@login_required
def request_verification():
    if current_user.account_role == "admin":
        flash("管理员账号不需要身份核验。", "info")
        return redirect(url_for("account.profile"))
    pending = UserVerification.query.filter_by(user_id=current_user.id, status="pending").first()
    if pending:
        flash("你的核验申请正在处理中。", "info")
    else:
        db.session.add(UserVerification(user_id=current_user.id, status="pending"))
        db.session.commit()
        flash("核验申请已提交。当前项目只维护核验状态，不收集或保存真实身份证件材料。", "success")
    return redirect(url_for("account.profile"))


@account_bp.route("/notifications")
@login_required
def notifications():
    rows = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return render_template("account/notifications.html", notifications=rows)
