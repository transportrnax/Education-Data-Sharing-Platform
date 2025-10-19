from datetime import datetime
from bson import ObjectId
from .. import mongo

class Help:
    def __init__(self, question, user_id, answer=None, created_at=None, updated_at=None, _id=None, answered_at=None):
        self.question = question
        self.user_id = user_id
        self.answer = answer
        self._id = _id
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.answered_at = updated_at or datetime.utcnow()
    @staticmethod
    def create(question, user_id):
        help_data = {
            'question': question,
            'user_id': user_id,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'status': "pending"
        }
        result = mongo.db.help.insert_one(help_data)
        return result.inserted_id

    @staticmethod
    def get_by_id(help_id):
        help_data = mongo.db.help.find_one({'_id': ObjectId(help_id)})
        if help_data:
            return Help(
                _id=help_data.get('_id'),
                question=help_data['question'],
                user_id=help_data['user_id'],
                answer=help_data.get('answer'),
                created_at=help_data['created_at'],
                updated_at=help_data['updated_at']
            )
        return None

    @staticmethod
    def get_user_questions(user_id):
        questions = []
        for help_data in mongo.db.help.find({'user_id': str(user_id)}).sort('created_at', -1):
            questions.append(Help(
                _id=help_data.get('_id'),
                question=help_data['question'],
                user_id=help_data['user_id'],
                answer=help_data.get('answer'),
                created_at=help_data['created_at'],
                updated_at=help_data['updated_at']
            ))
        return questions

    @staticmethod
    def get_all_questions():
        questions = []
        for help_data in mongo.db.help.find().sort('created_at', -1):
            questions.append(Help(
                _id=help_data.get('_id'),
                question=help_data['question'],
                user_id=help_data['user_id'],
                answer=help_data.get('answer'),
                created_at=help_data['created_at'],
                updated_at=help_data['updated_at'],
            ))
        return questions
    
    def save(self, help_id: ObjectId, answer: str, answer_by: str):
        print(help_id)
        print(answer)
        mongo.db.help.update_one(
            {'_id': help_id},
            {
                '$set': {
                    'answer': answer,
                    'answered_at': datetime.utcnow(),
                    'answered_by': answer_by,
                    'status': "answered"
                }
            }
        ) 