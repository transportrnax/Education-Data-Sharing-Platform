from datetime import datetime, timezone
from bson import ObjectId

from app.extensions import get_db

class ThesisPurchase:
	def __init__(self, purchase_doc: dict):
		self.purchase_id = str(purchase_doc['_id']) if '_id' in purchase_doc else "-1"
		self.thesis_id = str(purchase_doc['thesis_id']) if 'thesis_id' in purchase_doc else "-1"
		self.user_id = str(purchase_doc['user_id']) if 'user_id' in purchase_doc else "-1"
		self.price = purchase_doc.get('price', -1)
		self.time = datetime.fromtimestamp(purchase_doc['time'] * 1000.0) if 'time' in purchase_doc else datetime.now(timezone.utc)

	@staticmethod
	def get_by_id(purchase_id: str):
		db = get_db()

		data = db.ThesisPurchase.find_one({"_id": ObjectId(purchase_id)})

		return ThesisPurchase(data) if data else None

	@staticmethod
	def get_by_thesis(thesis_id: str, limit: int | None = 100) -> list[dict]:
		db = get_db()

		cursor = db.ActivityRecords.find({'thesis_id': thesis_id}).sort("time", -1).limit(limit)

		return ThesisPurchase.__parse_cursor(cursor)

	@staticmethod
	def __parse_cursor(cursor) -> list[dict]:
		records = [{
			'purchase_id': str(record['_id']),
			'thesis_id': str(record['thesis_id']),
			'user_id': str(record['user_id']),
			'price': record['price'],
			'time': datetime.fromtimestamp(record['time'] * 1000.0) if 'time' in record else datetime.now(timezone.utc)
		} for record in cursor]

		return records