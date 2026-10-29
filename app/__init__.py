import os
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, abort, render_template
from flask_login import current_user

from app.extensions import csrf, db, login_manager


def create_app():
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    upload_dir = Path(app.instance_path) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-before-deployment"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///app.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=str(upload_dir),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import Category, User
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.market import market_bp
    from app.routes.orders import orders_bp
    from app.routes.account import account_bp
    from app.routes.admin import admin_bp

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_shell_data():
        unread_count = 0
        if current_user.is_authenticated:
            from app.models import Notification
            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {"unread_count": unread_count}

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.cli.command("init-db")
    def init_db_command():
        """Create tables and the starter categories."""
        db.create_all()
        if Category.query.count() == 0:
            for index, name in enumerate(("数码电子", "家居生活", "服饰箱包", "书籍文具", "运动户外", "其他")):
                db.session.add(Category(name=name, sort_order=index))
            db.session.commit()
        click.echo("数据库表和默认分类已准备完成。")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True, help="管理员用户名")
    @click.option("--nickname", prompt="管理员昵称", default="平台管理员")
    @click.password_option(confirmation_prompt=True)
    def create_admin(username, nickname, password):
        """Create an administrator account interactively."""
        from app.models import User
        if len(password) < 8:
            raise click.ClickException("管理员密码至少需要 8 个字符。")
        if User.query.filter_by(username=username.strip()).first():
            raise click.ClickException("该用户名已存在。")
        user = User(username=username.strip(), nickname=nickname.strip(), account_role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo("管理员账号已创建。")

    with app.app_context():
        db.create_all()
        admin_username = os.getenv("ADMIN_USERNAME", "").strip()
        admin_nickname = os.getenv("ADMIN_NICKNAME", "").strip()
        admin_password = os.getenv("ADMIN_PASSWORD", "")
        if any((admin_username, admin_nickname, admin_password)):
            if not (admin_username and admin_nickname and admin_password):
                app.logger.warning("管理员初始化未执行：ADMIN_USERNAME、ADMIN_NICKNAME、ADMIN_PASSWORD 必须同时设置。")
            elif len(admin_username) < 3 or len(admin_username) > 60 or len(admin_nickname) > 50 or len(admin_password) < 8:
                app.logger.warning("管理员初始化未执行：请检查用户名、昵称长度及密码长度（至少 8 位）。")
            else:
                from app.models import User
                existing_user = User.query.filter_by(username=admin_username).first()
                if existing_user is None:
                    admin = User(username=admin_username, nickname=admin_nickname, account_role="admin")
                    admin.set_password(admin_password)
                    db.session.add(admin)
                    db.session.commit()
                    app.logger.info("已根据环境变量初始化管理员账号：%s", admin_username)
                elif existing_user.account_role != "admin":
                    app.logger.warning("管理员初始化未执行：该用户名已被普通用户使用。")
        if Category.query.count() == 0:
            for index, name in enumerate(("数码电子", "家居生活", "服饰箱包", "书籍文具", "运动户外", "其他")):
                db.session.add(Category(name=name, sort_order=index))
            db.session.commit()

    return app
