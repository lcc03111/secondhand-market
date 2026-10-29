from datetime import datetime
from decimal import Decimal
from secrets import token_hex

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import (AfterSalesCase, CaseEvidence, Conversation, Item, Message, Notification,
                        Order, OrderDelivery, OrderStatusLog, Report, Review)
from app.services import change_order_status, notify
from app.utils import save_upload
from flask import current_app

orders_bp = Blueprint("orders", __name__)


def _participant_order(order_id):
    order = Order.query.get_or_404(order_id)
    if current_user.id not in (order.buyer_id, order.seller_id) and current_user.account_role != "admin":
        abort(403)
    return order


def _restock(order):
    item = db.session.get(Item, order.item_id)
    if item:
        item.stock_qty += order.quantity
        if item.status in ("sold", "off_shelf"):
            item.status = "on_sale"


@orders_bp.route("/items/<int:item_id>/order", methods=["POST"])
@login_required
def create_order(item_id):
    item = Item.query.get_or_404(item_id)
    if item.seller_id == current_user.id:
        flash("不能购买自己发布的物品。", "error")
        return redirect(url_for("main.item_detail", item_id=item.id))
    quantity = request.form.get("quantity", type=int) or 0
    method = request.form.get("delivery_method", "")
    if item.status != "on_sale" or quantity < 1 or quantity > item.stock_qty:
        flash("物品暂不可购买，或库存数量不足。", "error")
        return redirect(url_for("main.item_detail", item_id=item.id))
    if method not in ("shipping", "meetup"):
        flash("请选择交付方式。", "error")
        return redirect(url_for("main.item_detail", item_id=item.id))
    if method == "shipping":
        recipient = request.form.get("recipient", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        if not recipient or not phone or not address:
            flash("快递交付需要填写收件人、电话和收货地址。", "error")
            return redirect(url_for("main.item_detail", item_id=item.id))
        delivery = OrderDelivery(recipient=recipient[:50], phone=phone[:20], address_snapshot=address[:500])
    else:
        meetup_location = request.form.get("meetup_location", "").strip()
        if not meetup_location:
            flash("请填写面交地点。", "error")
            return redirect(url_for("main.item_detail", item_id=item.id))
        delivery = OrderDelivery(meetup_location=meetup_location[:300])

    order = Order(
        order_no=f"SW{datetime.utcnow():%Y%m%d%H%M%S}{token_hex(3).upper()}",
        item_id=item.id, buyer_id=current_user.id, seller_id=item.seller_id,
        item_title=item.title, unit_price=item.price, quantity=quantity,
        total_amount=Decimal(item.price) * quantity, delivery_method=method,
        status="pending_seller", delivery=delivery,
    )
    item.stock_qty -= quantity
    if item.stock_qty == 0:
        item.status = "sold"
    db.session.add(order)
    db.session.flush()
    db.session.add(OrderStatusLog(order_id=order.id, old_status=None, new_status="pending_seller",
                                  changed_by=current_user.id, remark="买家提交订单"))
    conversation = Conversation.query.filter_by(item_id=item.id, buyer_id=current_user.id,
                                               seller_id=item.seller_id).first()
    if not conversation:
        conversation = Conversation(item_id=item.id, buyer_id=current_user.id, seller_id=item.seller_id)
        db.session.add(conversation)
        db.session.flush()
    conversation.order_id = order.id
    db.session.add(Message(conversation_id=conversation.id, sender_id=current_user.id,
                           body=f"已创建订单 {order.order_no}，请确认交易细节。"))
    notify(order.seller_id, "收到新订单", f"{order.item_title} × {quantity}", "order", order.id)
    db.session.commit()
    flash("订单已提交，等待卖家处理。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders")
@login_required
def order_list():
    orders = Order.query.filter((Order.buyer_id == current_user.id) | (Order.seller_id == current_user.id))\
        .order_by(Order.created_at.desc()).all()
    return render_template("orders/list.html", orders=orders)


@orders_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = _participant_order(order_id)
    cases = AfterSalesCase.query.filter_by(order_id=order.id).order_by(AfterSalesCase.created_at.desc()).all()
    reviews = Review.query.filter_by(order_id=order.id).all()
    status_logs = OrderStatusLog.query.filter_by(order_id=order.id).order_by(OrderStatusLog.created_at).all()
    return render_template("orders/detail.html", order=order, cases=cases, reviews=reviews,
                           status_logs=status_logs)


@orders_bp.route("/orders/<int:order_id>/accept", methods=["POST"])
@login_required
def accept_order(order_id):
    order = _participant_order(order_id)
    if current_user.id != order.seller_id or order.status != "pending_seller":
        abort(403)
    new_status = "pending_shipment" if order.delivery_method == "shipping" else "pending_meetup"
    change_order_status(order, new_status, current_user.id, "卖家接受订单")
    notify(order.buyer_id, "卖家已接受订单", f"订单 {order.order_no} 已接受。", "order", order.id)
    db.session.commit()
    flash("订单已接受。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/reject", methods=["POST"])
@login_required
def reject_order(order_id):
    order = _participant_order(order_id)
    if current_user.id != order.seller_id or order.status != "pending_seller":
        abort(403)
    order.cancel_reason = request.form.get("reason", "卖家暂时无法交易").strip()[:500]
    change_order_status(order, "rejected", current_user.id, order.cancel_reason)
    _restock(order)
    notify(order.buyer_id, "订单未被接受", order.cancel_reason, "order", order.id)
    db.session.commit()
    flash("订单已拒绝，库存已恢复。", "info")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = _participant_order(order_id)
    if current_user.id != order.buyer_id or order.status != "pending_seller":
        flash("当前订单状态不支持取消。", "error")
        return redirect(url_for("orders.order_detail", order_id=order.id))
    reason = request.form.get("reason", "买家取消订单").strip()[:500]
    order.cancel_reason = reason
    change_order_status(order, "canceled", current_user.id, reason)
    _restock(order)
    notify(order.seller_id, "买家取消订单", f"订单 {order.order_no} 已取消。", "order", order.id)
    db.session.commit()
    flash("订单已取消，库存已恢复。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/ship", methods=["POST"])
@login_required
def ship_order(order_id):
    order = _participant_order(order_id)
    if current_user.id != order.seller_id or order.status != "pending_shipment" or order.delivery_method != "shipping":
        abort(403)
    carrier = request.form.get("carrier_name", "").strip()
    tracking = request.form.get("tracking_number", "").strip()
    if not carrier or not tracking:
        flash("请填写物流公司和运单号。", "error")
    else:
        order.delivery.carrier_name = carrier[:100]
        order.delivery.tracking_number = tracking[:100]
        order.delivery.shipped_at = datetime.utcnow()
        change_order_status(order, "in_transit", current_user.id, f"卖家手动填写物流：{carrier} {tracking}")
        notify(order.buyer_id, "卖家已发货", f"{carrier}，运单号 {tracking}", "order", order.id)
        db.session.commit()
        flash("物流信息已保存。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/handoff", methods=["POST"])
@login_required
def meetup_handoff(order_id):
    order = _participant_order(order_id)
    if current_user.id != order.seller_id or order.delivery_method != "meetup" or order.status != "pending_meetup":
        abort(403)
    order.delivery.handed_over_at = datetime.utcnow()
    change_order_status(order, "pending_receipt", current_user.id, "卖家确认已完成面交")
    notify(order.buyer_id, "等待确认收货", "卖家已标记面交完成，请核对物品后确认。", "order", order.id)
    db.session.commit()
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/confirm", methods=["POST"])
@login_required
def confirm_receipt(order_id):
    order = _participant_order(order_id)
    if current_user.id != order.buyer_id or order.status not in ("in_transit", "pending_receipt"):
        abort(403)
    order.delivery.received_at = datetime.utcnow()
    change_order_status(order, "completed", current_user.id, "买家确认收到物品")
    if order.item.stock_qty == 0:
        order.item.status = "sold"
    notify(order.seller_id, "交易已完成", f"订单 {order.order_no} 已完成。", "order", order.id)
    db.session.commit()
    flash("已确认收货，交易完成。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/cases", methods=["POST"])
@login_required
def create_case(order_id):
    order = _participant_order(order_id)
    if current_user.id != order.buyer_id:
        abort(403)
    if order.status not in ("in_transit", "pending_meetup", "pending_receipt", "completed"):
        flash("当前订单状态暂不支持申请退款或纠纷处理。", "error")
        return redirect(url_for("orders.order_detail", order_id=order.id))
    active = AfterSalesCase.query.filter_by(order_id=order.id).filter(
        AfterSalesCase.status.in_(["refund_requested", "negotiating", "platform_processing"])
    ).first()
    if active:
        flash("该订单已有处理中申请。", "error")
        return redirect(url_for("orders.order_detail", order_id=order.id))
    description = request.form.get("description", "").strip()
    reason = request.form.get("reason", "其他").strip()[:100]
    if len(description) < 5:
        flash("请补充不少于 5 个字符的情况说明。", "error")
        return redirect(url_for("orders.order_detail", order_id=order.id))
    case = AfterSalesCase(case_no=f"AS{token_hex(5).upper()}", order_id=order.id,
                          applicant_id=current_user.id, reason=reason, description=description,
                          status="refund_requested")
    db.session.add(case)
    db.session.flush()
    try:
        for evidence in request.files.getlist("evidence")[:5]:
            filename = save_upload(evidence, current_app.config["UPLOAD_FOLDER"])
            if filename:
                db.session.add(CaseEvidence(case_id=case.id, uploaded_by=current_user.id, filename=filename))
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "error")
        return redirect(url_for("orders.order_detail", order_id=order.id))
    change_order_status(order, "refund_requested", current_user.id, "用户提交退款或纠纷申请")
    notify(order.seller_id, "订单有新的退款或纠纷申请", f"订单 {order.order_no}", "case", case.id)
    db.session.commit()
    flash("申请已提交。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/cases/<int:case_id>/respond", methods=["POST"])
@login_required
def respond_case(case_id):
    case = AfterSalesCase.query.get_or_404(case_id)
    order = _participant_order(case.order_id)
    if current_user.id != order.seller_id or case.status not in ("refund_requested", "negotiating"):
        abort(403)
    action = request.form.get("action")
    note = request.form.get("note", "").strip()[:1000]
    if action == "agree":
        case.status = "platform_processing"
        case.resolution = f"卖家同意申请，等待管理员记录处理结果。{note}"
        change_order_status(order, "platform_processing", current_user.id, "卖家同意申请，转管理员处理")
        notify(case.applicant_id, "卖家同意申请", "申请已转交管理员记录最终结果。", "case", case.id)
    else:
        case.status = "negotiating"
        case.resolution = f"卖家暂不同意，双方可继续协商。{note}"
        change_order_status(order, "negotiating", current_user.id, "卖家回应，进入协商")
        notify(case.applicant_id, "退款申请进入协商", note or "卖家已回应申请。", "case", case.id)
    db.session.commit()
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/review", methods=["POST"])
@login_required
def submit_review(order_id):
    order = _participant_order(order_id)
    if order.status != "completed" or current_user.id not in (order.buyer_id, order.seller_id):
        abort(403)
    if Review.query.filter_by(order_id=order.id, reviewer_id=current_user.id).first():
        flash("你已经评价过该订单。", "info")
        return redirect(url_for("orders.order_detail", order_id=order.id))
    rating = request.form.get("rating", type=int) or 0
    content = request.form.get("content", "").strip()
    if rating < 1 or rating > 5 or not content:
        flash("请选择 1 到 5 分并填写评价内容。", "error")
    else:
        reviewee_id = order.seller_id if current_user.id == order.buyer_id else order.buyer_id
        db.session.add(Review(order_id=order.id, reviewer_id=current_user.id, reviewee_id=reviewee_id,
                              rating=rating, content=content[:1000]))
        notify(reviewee_id, "收到交易评价", f"订单 {order.order_no} 有新评价。", "order", order.id)
        db.session.commit()
        flash("评价已发布。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))


@orders_bp.route("/orders/<int:order_id>/report", methods=["POST"])
@login_required
def report_order(order_id):
    order = _participant_order(order_id)
    if current_user.id not in (order.buyer_id, order.seller_id):
        abort(403)
    reason = request.form.get("reason", "交易问题").strip()[:100]
    description = request.form.get("description", "").strip()
    db.session.add(Report(reporter_id=current_user.id, target_type="order", target_id=order.id,
                          reason=reason, description=description))
    db.session.commit()
    flash("交易举报已提交。", "success")
    return redirect(url_for("orders.order_detail", order_id=order.id))
