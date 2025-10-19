from datetime import datetime, timezone
from bson import ObjectId
from .. import mongo

class Payment:
    def __init__(self, document):
        self.payment_id = document.get('_id')
        self.user_id = document.get('user_id')
        self.organization_id = document.get('organization_id')
        self.amount = document.get('amount', 0.0)
        self.service_type = document.get('service_type')
        self.status = document.get('status', 'pending')
        self.payment_method = document.get('payment_method')
        self.created_at = document.get('created_at', datetime.utcnow())
        self.updated_at = document.get('updated_at', datetime.utcnow())
        self.description = document.get('description', '')

    @staticmethod
    def create(user_id, organization_id, amount, service_type, payment_method, description=''):
        payment_data = {
            'user_id': user_id,
            'organization_id': organization_id,
            'amount': float(amount),
            'service_type': service_type,
            'status': 'pending',
            'payment_method': payment_method,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'description': description
        }
        
        result = mongo.db.payments.insert_one(payment_data)
        payment_data['_id'] = result.inserted_id
        return Payment(payment_data)

    @staticmethod
    def get_by_id(payment_id):
        payment_data = mongo.db.payments.find_one({'_id': ObjectId(payment_id)})
        return Payment(payment_data) if payment_data else None

    @staticmethod
    def get_by_organization_id(organization_id):
        payments = mongo.db.payments.find({'organization_id': organization_id})
        return [Payment(payment) for payment in payments]

    @staticmethod
    def get_by_user_id(user_id):
        payments = mongo.db.payments.find({'user_id': user_id})
        return [Payment(payment) for payment in payments]

    def update_status(self, status):
        update_data = {
            'status': status,
            'updated_at': datetime.utcnow()
        }
        
        result = mongo.db.payments.update_one(
            {'_id': self.payment_id},
            {'$set': update_data}
        )
        
        if result.modified_count > 0:
            self.status = status
            self.updated_at = update_data['updated_at']
            return True
        return False

    def to_dict(self):
        return {
            'payment_id': str(self.payment_id),
            'user_id': str(self.user_id),
            'organization_id': str(self.organization_id),
            'amount': self.amount,
            'service_type': self.service_type,
            'status': self.status,
            'payment_method': self.payment_method,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'description': self.description
        } 