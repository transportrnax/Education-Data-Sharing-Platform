from flask_pymongo import PyMongo, MongoClient
from flask_login import LoginManager
from flask_mail import Mail
from flask import g


mongo = PyMongo()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
mail = Mail()

# from app.main.User import User # Assuming User.Roles enum is here
# from app.workspace.models import OConvener
# from app.admin.models import TAdmin
# from bson import ObjectId

# @login_manager.user_loader
# def load_user(user_id):
#     user_doc = mongo.db.users.find_one({"_id": user_id})
#     role = user_doc.get('role')
#     if int(role) == User.Roles.O_CONVENER.value:
#         return OConvener(user_doc)
#     elif int(role) == User.Roles.E_ADMIN.value:
#         return TAdmin(user_doc)
#     else:
#         return User(user_doc) 

def get_db():
    if 'db' not in g:
        g.db = mongo.db

    return g.db


def close_db(e=None):
    """
    Closes the database client connection if it exists.

    :param e: An optional exception that triggered the closing, used typically
              in teardown callbacks. This parameter is not used within the function.
    :raises: Any exceptions raised by the `close` method of the `db_client`.

   This function assumes that `g` is a global or context-local object where
   the `db_client` is stored under the key 'db_client'.
    """
    g.pop('db', None)
