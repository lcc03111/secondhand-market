from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.models import (AfterSalesCase, Announcement, Category, Item, Order, Report,
                        User, UserVerification)
from app.security import admin_required
from app.services import change_order_status, log_admin_action, notify

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@admin_required
def dashboard():
    stats = {
        "users": User.query.filter_by(account_role="user").count(),
        "items": Item.query.count(),
        "pending_items": Item.query.filter_by(status="pending_review").count(),
        "orders": Order.query.count(),
        "open_cases": AfterSalesCase.query.filter(AfterSalesCase.status.in_(
            ["refund_requested", "negotiating", "platform_processing"])).count(),
        "open_reports": Report.query.filter_by(status="open").count(),
    }
    return render_template("admin/dashboard.html", stats=stats)


@admin_bp.route("/items")
@admin_required
def items():
    pending = Item.query.filter_by(status="pending_review").order_by(Item.created_at).all()
    return render_template("admin/items.html", items=pending)


@admin_bp.route("/items/<int:item_id>/moderate", methods=["POST"])
@admin_required
def moderate_item(item_id):
    item = Item.query.get_or_404(item_id)
    action = request.form.get("action")
    note = request.form.get("note", "").strip()[:500]
    if item.status != "pending_review" or action not in ("approve", "reject"):
        flash("该物品当前不能审核。", "error")
    else:
        item.status = "on_sale" if action == "approve" else "rejected"
        item.moderation_note = note
        log_admin_action(current_user.id, f"item_{action}", "item", item.id, note)
        notify(item.seller_id, "物品审核结果", "物品已通过审核。" if action == "approve" else (note or "物品未通过审核。"),
               "item", item.id)
        db.session.commit()
        flash("审核处理完成。", "success")
    return redirect(url_for("admin.items"))


@admin_bp.route("/users")
@admin_required
def users():
    rows = User.query.order_by(User.created_at.desc()).all()
    verifications = (UserVerification.query.join(User, UserVerification.user_id == User.id)
                     .filter(UserVerification.status == "pending", User.account_role == "user")
                     .order_by(UserVerification.submitted_at).all())
    return render_template("admin/users.html", users=rows, verifications=verifications)


@admin_bp.route("/users/<int:user_id>/status", methods=["POST"])
@admin_required
def update_user_status(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id or user.account_role == "admin":
        flash("不能修改当前管理员或其他管理员的账号状态。", "error")
    else:
        user.account_status = "suspended" if user.account_status == "active" else "active"
        log_admin_action(current_user.id, "user_status", "user", user.id, user.account_status)
        db.session.commit()
        flash("用户状态已更新。", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/verifications/<int:verification_id>", methods=["POST"])
@admin_required
def review_verification(verification_id):
    verification = UserVerification.query.get_or_404(verification_id)
    applicant = db.session.get(User, verification.user_id)
    if applicant is None or applicant.account_role == "admin" or applicant.id == current_user.id:
        flash("管理员账号不需要身份核验，且不能审核自己的申请。", "error")
    elif verification.status != "pending":
        flash("该核验申请已处理。", "info")
    else:
        action = request.form.get("action")
        if action not in ("approve", "reject"):
            flash("无效的核验操作。", "error")
        else:
            verification.status = "approved" if action == "approve" else "rejected"
            verification.reviewed_by = current_user.id
            verification.reviewed_at = datetime.utcnow()
            verification.rejection_reason = request.form.get("reason", "").strip()[:500] or None
            log_admin_action(current_user.id, "verification_review", "verification", verification.id,
                             verification.status)
            notify(verification.user_id, "身份核验结果",
                   "身份核验已通过。" if action == "approve" else (verification.rejection_reason or "身份核验未通过。"),
                   "profile", verification.user_id)
            db.session.commit()
            flash("核验状态已更新。", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name or len(name) > 50:
            flash("分类名称必填且不能超过 50 个字符。", "error")
        elif Category.query.filter_by(name=name).first():
            flash("该分类已存在。", "error")
        else:
            category = Category(name=name, sort_order=request.form.get("sort_order", type=int) or 0)
            db.session.add(category)
            db.session.flush()
            log_admin_action(current_user.id, "category_create", "category", category.id, name)
            db.session.commit()
            flash("分类已新增。", "success")
            return redirect(url_for("admin.categories"))
    rows = Category.query.order_by(Category.sort_order, Category.name).all()
    return render_template("admin/categories.html", categories=rows)


@admin_bp.route("/categories/<int:category_id>/toggle", methods=["POST"])
@admin_required
def toggle_category(category_id):
    category = Category.query.get_or_404(category_id)
    category.is_active = not category.is_active
    log_admin_action(current_user.id, "category_toggle", "category", category.id,
                     "active" if category.is_active else "inactive")
    db.session.commit()
    return redirect(url_for("admin.categories"))


@admin_bp.route("/cases")
@admin_required
def cases():
    rows = AfterSalesCase.query.order_by(AfterSalesCase.created_at.desc()).all()
    return render_template("admin/cases.html", cases=rows)


@admin_bp.route("/cases/<int:case_id>/resolve", methods=["POST"])
@admin_required
def resolve_case(case_id):
    case = AfterSalesCase.query.get_or_404(case_id)
    order = db.session.get(Order, case.order_id)
    action = request.form.get("action")
    note = request.form.get("resolution", "").strip()[:2000]
    if case.status not in ("refund_requested", "negotiating", "platform_processing"):
        flash("该申请已处理。", "info")
    elif action == "process":
        case.status = "platform_processing"
        change_order_status(order, "platform_processing", current_user.id, "管理员介入处理")
        case.handled_by = current_user.id
        case.resolution = note or "平台正在处理该申请。"
        notify(case.applicant_id, "平台已介入", case.resolution, "case", case.id)
        db.session.commit()
        flash("申请已转入平台处理。", "success")
    elif action in ("refund", "reject"):
        case.status = "resolved_refund" if action == "refund" else "resolved_rejected"
        case.handled_by = current_user.id
        case.resolution = note or ("平台同意退款申请。" if action == "refund" else "平台驳回退款申请。")
        change_order_status(order, "refunded" if action == "refund" else "refund_rejected",
                            current_user.id, case.resolution)
        log_admin_action(current_user.id, f"case_{action}", "case", case.id, case.resolution)
        notify(case.applicant_id, "退款或纠纷处理结果", case.resolution, "case", case.id)
        notify(order.seller_id if case.applicant_id == order.buyer_id else order.buyer_id,
               "退款或纠纷处理结果", case.resolution, "case", case.id)
        db.session.commit()
        flash("处理结果已记录。", "success")
    else:
        flash("请选择有效处理方式。", "error")
    return redirect(url_for("admin.cases"))


@admin_bp.route("/reports")
@admin_required
def reports():
    rows = Report.query.order_by(Report.created_at.desc()).all()
    return render_template("admin/reports.html", reports=rows)


@admin_bp.route("/reports/<int:report_id>/close", methods=["POST"])
@admin_required
def close_report(report_id):
    report = Report.query.get_or_404(report_id)
    report.status = "closed"
    report.handled_by = current_user.id
    report.handled_at = datetime.utcnow()
    log_admin_action(current_user.id, "report_close", "report", report.id,
                     request.form.get("note", "").strip()[:1000])
    db.session.commit()
    flash("举报已标记为处理完成。", "success")
    return redirect(url_for("admin.reports"))


@admin_bp.route("/announcements", methods=["GET", "POST"])
@admin_required
def announcements():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        if not title or not content:
            flash("公告标题和内容均为必填。", "error")
        else:
            announcement = Announcement(title=title[:150], content=content, created_by=current_user.id)
            db.session.add(announcement)
            db.session.flush()
            log_admin_action(current_user.id, "announcement_create", "announcement", announcement.id, title)
            db.session.commit()
            flash("公告已发布。", "success")
            return redirect(url_for("admin.announcements"))
    rows = Announcement.query.order_by(Announcement.published_at.desc()).all()
    return render_template("admin/announcements.html", announcements=rows)


@admin_bp.route("/announcements/<int:announcement_id>/toggle", methods=["POST"])
@admin_required
def toggle_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    announcement.status = "hidden" if announcement.status == "published" else "published"
    db.session.commit()
    return redirect(url_for("admin.announcements"))
