from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Category, Conversation, Favorite, Item, ItemImage, Message, Notification, Report, User
from app.utils import save_upload

market_bp = Blueprint("market", __name__)
CONDITIONS = ("全新", "几乎全新", "轻微使用痕迹", "正常使用痕迹", "明显使用痕迹")


def _owned_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.seller_id != current_user.id:
        abort(403)
    return item


@market_bp.route("/items/new", methods=["GET", "POST"])
@login_required
def create_item():
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id", type=int)
        condition_level = request.form.get("condition_level", "")
        quantity = request.form.get("stock_qty", type=int) or 0
        try:
            price = Decimal(request.form.get("price", "0").strip())
        except (InvalidOperation, AttributeError):
            price = Decimal("0")
        category = db.session.get(Category, category_id) if category_id else None
        if len(title) < 2 or len(title) > 150 or not description:
            flash("请填写有效的物品名称和描述。", "error")
        elif not category or not category.is_active:
            flash("请选择有效的物品分类。", "error")
        elif price <= 0 or quantity < 1 or quantity > 999:
            flash("价格必须大于 0，库存数量需为 1 到 999。", "error")
        elif condition_level not in CONDITIONS:
            flash("请选择物品成色。", "error")
        else:
            item = Item(seller_id=current_user.id, category_id=category.id, title=title,
                        description=description, price=price, condition_level=condition_level,
                        stock_qty=quantity, status="pending_review")
            db.session.add(item)
            db.session.flush()
            try:
                for index, image in enumerate(request.files.getlist("images")[:8]):
                    filename = save_upload(image, current_app.config["UPLOAD_FOLDER"])
                    if filename:
                        db.session.add(ItemImage(item_id=item.id, filename=filename, sort_order=index))
            except ValueError as error:
                db.session.rollback()
                flash(str(error), "error")
                return render_template("market/item_form.html", item=None, categories=categories,
                                       conditions=CONDITIONS)
            db.session.commit()
            flash("物品已提交审核，通过后会在列表中展示。", "success")
            return redirect(url_for("market.my_items"))
    return render_template("market/item_form.html", item=None, categories=categories, conditions=CONDITIONS)


@market_bp.route("/my/items")
@login_required
def my_items():
    items = Item.query.filter_by(seller_id=current_user.id).order_by(Item.created_at.desc()).all()
    return render_template("market/my_items.html", items=items)


@market_bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = _owned_item(item_id)
    if item.status == "sold":
        flash("已售出的物品不能编辑。", "error")
        return redirect(url_for("market.my_items"))
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id", type=int)
        condition_level = request.form.get("condition_level", "")
        quantity = request.form.get("stock_qty", type=int) or 0
        try:
            price = Decimal(request.form.get("price", "0").strip())
        except (InvalidOperation, AttributeError):
            price = Decimal("0")
        category = db.session.get(Category, category_id) if category_id else None
        if not title or not description or not category or price <= 0 or quantity < 1 or condition_level not in CONDITIONS:
            flash("请检查物品名称、分类、价格、成色和库存。", "error")
        else:
            item.title, item.description, item.category_id = title, description, category.id
            item.price, item.condition_level, item.stock_qty = price, condition_level, quantity
            item.status = "pending_review"
            try:
                start = len(item.images)
                for index, image in enumerate(request.files.getlist("images")[:8]):
                    filename = save_upload(image, current_app.config["UPLOAD_FOLDER"])
                    if filename:
                        db.session.add(ItemImage(item_id=item.id, filename=filename, sort_order=start + index))
            except ValueError as error:
                db.session.rollback()
                flash(str(error), "error")
            else:
                db.session.commit()
                flash("物品信息已更新并重新提交审核。", "success")
                return redirect(url_for("market.my_items"))
    return render_template("market/item_form.html", item=item, categories=categories, conditions=CONDITIONS)


@market_bp.route("/items/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_item(item_id):
    item = _owned_item(item_id)
    if item.status == "on_sale":
        item.status = "off_shelf"
        flash("物品已下架。", "success")
    elif item.status == "off_shelf" and item.stock_qty > 0:
        item.status = "on_sale"
        flash("物品已重新上架。", "success")
    else:
        flash("当前状态的物品不能上架或下架。", "error")
    db.session.commit()
    return redirect(url_for("market.my_items"))


@market_bp.route("/items/<int:item_id>/favorite", methods=["POST"])
@login_required
def toggle_favorite(item_id):
    item = Item.query.get_or_404(item_id)
    favorite = Favorite.query.filter_by(user_id=current_user.id, item_id=item.id).first()
    if favorite:
        db.session.delete(favorite)
        flash("已取消收藏。", "info")
    else:
        db.session.add(Favorite(user_id=current_user.id, item_id=item.id))
        flash("已加入收藏。", "success")
    db.session.commit()
    return redirect(request.referrer or url_for("main.item_detail", item_id=item.id))


@market_bp.route("/items/<int:item_id>/contact", methods=["POST"])
@login_required
def contact_seller(item_id):
    item = Item.query.get_or_404(item_id)
    if item.seller_id == current_user.id:
        flash("不能向自己发起咨询。", "error")
        return redirect(url_for("main.item_detail", item_id=item.id))
    conversation = Conversation.query.filter_by(
        item_id=item.id, buyer_id=current_user.id, seller_id=item.seller_id
    ).first()
    if not conversation:
        conversation = Conversation(item_id=item.id, buyer_id=current_user.id, seller_id=item.seller_id)
        db.session.add(conversation)
        db.session.flush()
    initial = request.form.get("message", "").strip()
    if initial:
        db.session.add(Message(conversation_id=conversation.id, sender_id=current_user.id, body=initial))
        conversation.last_message_at = datetime.utcnow()
        db.session.add(Notification(user_id=item.seller_id, title="收到物品咨询", content=initial[:150],
                                    reference_type="conversation", reference_id=conversation.id))
    db.session.commit()
    return redirect(url_for("market.conversation", conversation_id=conversation.id))


@market_bp.route("/messages")
@login_required
def inbox():
    conversations = Conversation.query.filter(
        (Conversation.buyer_id == current_user.id) | (Conversation.seller_id == current_user.id)
    ).order_by(Conversation.last_message_at.desc()).all()
    return render_template("market/inbox.html", conversations=conversations)


@market_bp.route("/messages/<int:conversation_id>", methods=["GET", "POST"])
@login_required
def conversation(conversation_id):
    conversation = Conversation.query.get_or_404(conversation_id)
    if current_user.id not in (conversation.buyer_id, conversation.seller_id):
        abort(403)
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        image = request.files.get("image")
        try:
            image_filename = save_upload(image, current_app.config["UPLOAD_FOLDER"])
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("market.conversation", conversation_id=conversation.id))
        if not body and not image_filename:
            flash("请输入消息或选择图片。", "error")
        else:
            db.session.add(Message(conversation_id=conversation.id, sender_id=current_user.id,
                                   body=body or None, image_filename=image_filename))
            conversation.last_message_at = datetime.utcnow()
            recipient_id = conversation.seller_id if current_user.id == conversation.buyer_id else conversation.buyer_id
            db.session.add(Notification(user_id=recipient_id, title="收到新消息", content=(body or "收到一张图片")[:150],
                                        reference_type="conversation", reference_id=conversation.id))
            db.session.commit()
            return redirect(url_for("market.conversation", conversation_id=conversation.id))
    messages = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.sent_at).all()
    Message.query.filter(Message.conversation_id == conversation.id, Message.sender_id != current_user.id,
                         Message.read_at.is_(None)).update({"read_at": datetime.utcnow()})
    db.session.commit()
    return render_template("market/conversation.html", conversation=conversation, messages=messages)


@market_bp.route("/items/<int:item_id>/report", methods=["POST"])
@login_required
def report_item(item_id):
    item = Item.query.get_or_404(item_id)
    if item.seller_id == current_user.id:
        flash("不能举报自己发布的物品。", "error")
    else:
        reason = request.form.get("reason", "其他").strip()[:100]
        description = request.form.get("description", "").strip()
        db.session.add(Report(reporter_id=current_user.id, target_type="item", target_id=item.id,
                              reason=reason, description=description))
        db.session.commit()
        flash("举报已提交，管理员会进行核查。", "success")
    return redirect(url_for("main.item_detail", item_id=item.id))


@market_bp.route("/users/<int:user_id>/report", methods=["POST"])
@login_required
def report_user(user_id):
    target = User.query.get_or_404(user_id)
    if target.id == current_user.id:
        flash("不能举报自己的账号。", "error")
    else:
        db.session.add(Report(
            reporter_id=current_user.id, target_type="user", target_id=target.id,
            reason=request.form.get("reason", "其他").strip()[:100],
            description=request.form.get("description", "").strip(),
        ))
        db.session.commit()
        flash("用户举报已提交。", "success")
    return redirect(request.referrer or url_for("main.home"))
