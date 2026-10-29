from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    nickname = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    account_role = db.Column(db.String(20), nullable=False, default="user")
    account_status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    items = db.relationship("Item", back_populates="seller", lazy="dynamic")

    @property
    def is_active(self):
        return self.account_status == "active"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Item(db.Model):
    __tablename__ = "items"
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    condition_level = db.Column(db.String(30), nullable=False)
    stock_qty = db.Column(db.Integer, default=1, nullable=False)
    status = db.Column(db.String(24), default="pending_review", nullable=False, index=True)
    moderation_note = db.Column(db.String(500))
    view_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    seller = db.relationship("User", back_populates="items")
    category = db.relationship("Category")
    images = db.relationship("ItemImage", cascade="all, delete-orphan", order_by="ItemImage.sort_order")


class ItemImage(db.Model):
    __tablename__ = "item_images"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)


class Favorite(db.Model):
    __tablename__ = "favorites"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class UserVerification(db.Model):
    __tablename__ = "user_verifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), default="pending", nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.String(500))


class Conversation(db.Model):
    __tablename__ = "conversations"
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_message_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    item = db.relationship("Item")
    buyer = db.relationship("User", foreign_keys=[buyer_id])
    seller = db.relationship("User", foreign_keys=[seller_id])
    messages = db.relationship("Message", cascade="all, delete-orphan", order_by="Message.sent_at")
    __table_args__ = (db.UniqueConstraint("item_id", "buyer_id", "seller_id", name="uq_item_conversation"),)


class Message(db.Model):
    __tablename__ = "messages"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text)
    image_filename = db.Column(db.String(255))
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = db.Column(db.DateTime)
    sender = db.relationship("User")


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(40), unique=True, nullable=False, index=True)
    item_id = db.Column(db.Integer, db.ForeignKey("items.id"), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    item_title = db.Column(db.String(150), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_method = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(32), default="pending_seller", nullable=False, index=True)
    cancel_reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    item = db.relationship("Item")
    buyer = db.relationship("User", foreign_keys=[buyer_id])
    seller = db.relationship("User", foreign_keys=[seller_id])
    delivery = db.relationship("OrderDelivery", back_populates="order", uselist=False, cascade="all, delete-orphan")


class OrderStatusLog(db.Model):
    __tablename__ = "order_status_logs"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    old_status = db.Column(db.String(32))
    new_status = db.Column(db.String(32), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    remark = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class OrderDelivery(db.Model):
    __tablename__ = "order_deliveries"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False)
    carrier_name = db.Column(db.String(100))
    tracking_number = db.Column(db.String(100))
    recipient = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    address_snapshot = db.Column(db.String(500))
    meetup_location = db.Column(db.String(300))
    shipped_at = db.Column(db.DateTime)
    handed_over_at = db.Column(db.DateTime)
    received_at = db.Column(db.DateTime)
    order = db.relationship("Order", back_populates="delivery")


class AfterSalesCase(db.Model):
    __tablename__ = "after_sales_cases"
    id = db.Column(db.Integer, primary_key=True)
    case_no = db.Column(db.String(40), unique=True, nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    applicant_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    case_type = db.Column(db.String(20), nullable=False, default="refund")
    reason = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), default="refund_requested", nullable=False, index=True)
    resolution = db.Column(db.Text)
    handled_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    order = db.relationship("Order")
    applicant = db.relationship("User", foreign_keys=[applicant_id])
    evidences = db.relationship("CaseEvidence", cascade="all, delete-orphan", order_by="CaseEvidence.created_at")


class CaseEvidence(db.Model):
    __tablename__ = "case_evidences"
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("after_sales_cases.id"), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    uploader = db.relationship("User")


class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    content = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
    reviewee = db.relationship("User", foreign_keys=[reviewee_id])
    __table_args__ = (db.UniqueConstraint("order_id", "reviewer_id", name="uq_order_reviewer"),)


class Report(db.Model):
    __tablename__ = "reports"
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="open", nullable=False, index=True)
    handled_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    handled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reporter = db.relationship("User", foreign_keys=[reporter_id])


class Announcement(db.Model):
    __tablename__ = "announcements"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="published", nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    published_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    reference_type = db.Column(db.String(30))
    reference_id = db.Column(db.Integer)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AdminOperationLog(db.Model):
    __tablename__ = "admin_operation_logs"
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action_type = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(30), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
