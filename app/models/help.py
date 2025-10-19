from datetime import datetime
from app.extensions import mongo

class Help:
    def __init__(self, question, user_id, answer=None, answered_by=None, answered_at=None, created_at=None):
        self.question = question
        self.user_id = user_id
        self.answer = answer
        self.answered_by = answered_by
        self.answered_at = answered_at
        self.created_at = created_at or datetime.utcnow()

    @staticmethod
    def create(question, user_id):
        help_doc = {
            'question': question,
            'user_id': user_id,
            'created_at': datetime.utcnow()
        }
        result = mongo.db.help.insert_one(help_doc)
        return result.inserted_id

    @staticmethod
    def get_by_id(help_id):
        help_doc = mongo.db.help.find_one({'_id': help_id})
        if help_doc:
            return Help(
                question=help_doc['question'],
                user_id=help_doc['user_id'],
                answer=help_doc.get('answer'),
                answered_by=help_doc.get('answered_by'),
                answered_at=help_doc.get('answered_at'),
                created_at=help_doc.get('created_at')
            )
        return None

    @staticmethod
    def get_by_user_id(user_id):
        help_docs = mongo.db.help.find({'user_id': user_id}).sort('created_at', -1)
        return [Help(
            question=doc['question'],
            user_id=doc['user_id'],
            answer=doc.get('answer'),
            answered_by=doc.get('answered_by'),
            answered_at=doc.get('answered_at'),
            created_at=doc.get('created_at')
        ) for doc in help_docs]

    @staticmethod
    def get_all():
        help_docs = mongo.db.help.find().sort('created_at', -1)
        return [Help(
            question=doc['question'],
            user_id=doc['user_id'],
            answer=doc.get('answer'),
            answered_by=doc.get('answered_by'),
            answered_at=doc.get('answered_at'),
            created_at=doc.get('created_at')
        ) for doc in help_docs]

    def update_answer(self, answer, answered_by):
        mongo.db.help.update_one(
            {'_id': self._id},
            {
                '$set': {
                    'answer': answer,
                    'answered_by': answered_by,
                    'answered_at': datetime.utcnow()
                }
            }
        ) 