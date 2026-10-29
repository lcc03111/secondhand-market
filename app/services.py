from datetime import datetime

from app.extensions import db
from app.models import AdminOperationLog, Notification, OrderStatusLog


def notify(user_id, title, content, reference_type=None, reference_id=None):
    db.session.add(Notification(
        user_id=user_id, title=title, content=content,
        reference_type=reference_type, reference_id=reference_id,
    ))


def change_order_status(order, new_status, actor_id=None, remark=None):
    old_status = order.status
    order.status = new_status
    order.updated_at = datetime.utcnow()
    db.session.add(OrderStatusLog(
        order_id=order.id, old_status=old_status, new_status=new_status,
        changed_by=actor_id, remark=remark,
    ))


def log_admin_action(admin_id, action_type, target_type, target_id, details=""):
    db.session.add(AdminOperationLog(
        admin_id=admin_id, action_type=action_type,
        target_type=target_type, target_id=target_id, details=details,
    ))
