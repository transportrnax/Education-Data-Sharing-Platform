from datetime import datetime, UTC
from app.extensions import mongo
from app.main.User import User
from bson import ObjectId

class TAdmin(User):
    def __init__(self, user_doc: dict):
        user_doc['role'] = User.Roles.T_ADMIN.value

        super().__init__(user_doc)

class EAdmin(User):
    def __init__(self, user_doc: dict):
        user_doc['role'] = User.Roles.E_ADMIN.value
        super().__init__(user_doc)

class SeniorEAdmin(User):
    def __init__(self, user_doc: dict):
        user_doc['role'] = User.Roles.SENIOR_EADMIN.value 
        super().__init__(user_doc)

class UserQuestion:
    PENDING = "pending"
    ANSWERED = "answered"

    def __init__(self, user_account: str, question: str,
                 _id: ObjectId = None, question_time: datetime = None,
                 status: str = PENDING, answer: str = None,
                 answered_by: str = None, answered_time: datetime = None):
        self._id = _id  
        self.user_account = user_account 
        self.question = question  
        self.question_time = question_time if question_time else datetime.now(UTC) 
        self.status = status 
        self.answer = answer 
        self.answered_by = answered_by  
        self.answered_time = answered_time

    @classmethod
    def from_document(cls, doc):
        if not doc:
            return None
        return cls(_id=doc.get('_id'),  user_account=doc.get('user_account'),
                    question=doc.get('question'), question_time=doc.get('question_time'),
                    status=doc.get('status'), answer=doc.get('answer'),
                    answered_by=doc.get('answered_by'),  answered_time=doc.get('answered_time'))

    @classmethod
    def find_by_id(cls, question_id):
        collection = mongo.db.help
        if isinstance(question_id, str):
            if not ObjectId.is_valid(question_id):
                return None
            question_id = ObjectId(question_id)
        elif not isinstance(question_id, ObjectId):
            return None
        doc = collection.find_one({"_id": question_id})
        return cls.from_document(doc)
    
    @classmethod
    def find_by_status(cls, status = PENDING, limit: int = 100):
        collection = mongo.db.help
        docs = collection.find({"status": status}).sort("question_time", 1).limit(limit)
        return [cls.from_document(doc) for doc in docs]
    
    @classmethod
    def __repr__(self):
        return f"<UserQuestion id='{self._id}' user='{self.user_account}' status='{self.status}'>"
