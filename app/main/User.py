from enum import Enum
from flask_login import UserMixin
from bson import ObjectId
from app.extensions import get_db


class User(UserMixin):
    """
    Access right level in Long Description, which is also Access Level in our design, is saved into a boolean array.
    Each element represents a right level, so that we can easily save coexisting access levels.
    Correspondence as follow:
    access_level[0] -> Public data access
    access_level[1] -> Public data consumption
    access_level[2] -> Public data provision
    """
    class Roles(Enum):
        T_ADMIN = 1
        E_ADMIN = 2
        O_CONVENER = 3
        NORMAL = 4
        SENIOR_EADMIN = 5

        NULL = -1

    def __init__(self, user_doc: dict):
        self.user_id = str(user_doc['_id']) if '_id' in user_doc else "-1"
        self.email = user_doc.get('email', "")
        self.username = user_doc.get('username', "")
        self.role = User.Roles(user_doc.get('role', User.Roles.NULL))
        self.access_level = user_doc.get('access_level', [False, False, False])
        self.organization = str(user_doc['organization']) if 'organization' in user_doc else "-1"

    def get_id(self):
        return str(self.user_id)

    @staticmethod
    def get_by_id(user_id: str):
        db = get_db()

        data = db.users.find_one({"_id": ObjectId(user_id)})

        return User(data) if data else None

    @staticmethod
    def get_by_email(email: str):
        db = get_db()

        data = db.users.find_one({"email": email})

        return User(data) if data else None