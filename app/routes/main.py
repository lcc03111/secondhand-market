from flask import Blueprint, abort, current_app, render_template, request, send_from_directory
from flask_login import current_user
from sqlalchemy import or_

from app.models import Announcement, Category, Favorite, Item, Review

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order, Category.name).all()
    latest_items = Item.query.filter_by(status="on_sale").order_by(Item.created_at.desc()).limit(8).all()
    announcements = Announcement.query.filter_by(status="published").order_by(Announcement.published_at.desc()).limit(3).all()
    favorite_ids = set()
    if current_user.is_authenticated:
        favorite_ids = {row.item_id for row in Favorite.query.filter_by(user_id=current_user.id).all()}
    return render_template("main/home.html", categories=categories, items=latest_items,
                           announcements=announcements, favorite_ids=favorite_ids)


@main_bp.route("/items")
def item_list():
    query = Item.query.filter_by(status="on_sale")
    keyword = request.args.get("q", "").strip()
    category_id = request.args.get("category", type=int)
    condition = request.args.get("condition", "").strip()
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    if keyword:
        query = query.filter(or_(Item.title.ilike(f"%{keyword}%"), Item.description.ilike(f"%{keyword}%")))
    if category_id:
        query = query.filter_by(category_id=category_id)
    if condition:
        query = query.filter_by(condition_level=condition)
    if min_price is not None:
        query = query.filter(Item.price >= min_price)
    if max_price is not None:
        query = query.filter(Item.price <= max_price)
    items = query.order_by(Item.created_at.desc()).all()
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order).all()
    return render_template("main/items.html", items=items, categories=categories,
                           keyword=keyword, category_id=category_id, condition=condition,
                           min_price=request.args.get("min_price", ""), max_price=request.args.get("max_price", ""))


@main_bp.route("/items/<int:item_id>")
def item_detail(item_id):
    item = Item.query.get_or_404(item_id)
    if item.status != "on_sale" and (not current_user.is_authenticated or
                                     (current_user.id != item.seller_id and current_user.account_role != "admin")):
        abort(404)
    item.view_count += 1
    from app.extensions import db
    db.session.commit()
    is_favorite = False
    if current_user.is_authenticated:
        is_favorite = Favorite.query.filter_by(user_id=current_user.id, item_id=item.id).first() is not None
    reviews = Review.query.filter_by(reviewee_id=item.seller_id).order_by(Review.created_at.desc()).limit(5).all()
    return render_template("main/item_detail.html", item=item, is_favorite=is_favorite, reviews=reviews)


@main_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
