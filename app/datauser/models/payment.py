from datetime import datetime
from ...extensions import mongo

class PaymentRecord:
    @staticmethod
    def create(student_id, org_id, amount, pay_type, detail=None):
        record = {
            'student_id': student_id,
            'org_id': org_id,
            'amount': amount,
            'pay_type': pay_type,  # 'download', 'record', 'identify'
            'detail': detail,
            'created_at': datetime.utcnow()
        }
        return mongo.db.payment_records.insert_one(record) 