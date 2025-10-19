from flask import Flask
from .extensions import mongo, close_db, login_manager, mail
from .main.User import User
from .main.routes import main_bp
from .auth.routes import auth_bp
from .payment.routes import payment_bp
from .workspace.routes import workspace_bp
from .thesis.routes import thesis_bp
from .datauser.routes import datauser_bp
from .datauser.routes import datauser_bp, consumer_bp, public_bp
from .admin.routes import admin_bp
from app.main.User import User # Assuming User.Roles enum is here
from app.workspace.models import OConvener
from app.admin.models import TAdmin, EAdmin, SeniorEAdmin
from bson import ObjectId

def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # Initialize MongoDB
    mongo.init_app(app)
    login_manager.init_app(app)
    @login_manager.user_loader
    def load_user(user_id):
        #print(ObjectId(user_id))
        user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        role = user_doc.get('role')
        if int(role) == User.Roles.O_CONVENER.value:
            return OConvener(user_doc)
        elif int(role) == User.Roles.E_ADMIN.value:
            return EAdmin(user_doc)
        elif int(role) == User.Roles.T_ADMIN.value:
            return TAdmin(user_doc)
        elif role == User.Roles.SENIOR_EADMIN.value: # 新增 SeniorEAdmin 加载
            return SeniorEAdmin(user_doc)
        else:
            return User(user_doc) 

    mail.init_app(app)

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(workspace_bp)
    app.register_blueprint(thesis_bp)
    app.register_blueprint(datauser_bp)
    app.register_blueprint(consumer_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    # Disconnect database on exit
    app.teardown_appcontext(close_db)

    return app
