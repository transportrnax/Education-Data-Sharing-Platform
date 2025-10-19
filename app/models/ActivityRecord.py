from enum import Enum
from datetime import datetime, timezone # Use timezone consistently
from bson import ObjectId

from ..extensions import get_db

class ActivityRecord:
    class Event(Enum):
        SYSTEM = 0

        AUTH = 1
        DOWNLOAD = 2
        PURCHASE = 3
        STU_AUTH = 4
        VIEW_COURSE = 5
        QUERY_GPA = 6

        GENERAL = 7

        ERROR = -1

    def __init__(self):
        self.activity_record_id = '-1'
        # If activityTime is not provided, set it to the current UTC time
        self.time = datetime.now(timezone.utc)
        self.user = ""
        self.event = ActivityRecord.Event.GENERAL
        self.detail = ""

    def parse(self) -> dict:
        parsed = {
            'activity_record_id': self.activity_record_id,
            'time': int(self.time.timestamp() * 1000),
            'user': str(self.user),
            'event': self.event,
            'detail': self.detail
        }

        return parsed

    def addRecord(self):
        db = get_db()

        db.ActivityRecords.insert_one(self.parse(), {'activity_record_id': False})

    def deleteRecord(self):
        db = get_db()

        result = db.ActivityRecords.delete_one({'_id': ObjectId(self.activity_record_id)})

        return result.deleted_count

    @staticmethod
    def getAllRecords(limit: int | None = 100) -> list[dict]:
        db = get_db()

        cursor = db.ActivityRecords.find().sort("activityTime", -1).limit(limit)

        return ActivityRecord.__parse_cursor(cursor)

    @staticmethod
    def findRecordByUser(user: str | ObjectId, limit: int | None = 100) -> list[dict]:
        db = get_db()

        cursor = db.ActivityRecords.find({'user': user}).sort("time", -1).limit(limit)

        return ActivityRecord.__parse_cursor(cursor)

    @staticmethod
    def findRecordByEvent(event: Event, limit: int | None = 100) -> list[dict]:
        db = get_db()

        cursor = db.ActivityRecords.find({'event': event}).sort("time", -1).limit(limit)

        return ActivityRecord.__parse_cursor(cursor)

    @staticmethod
    def findRecordById(_id: str) -> dict:
        db = get_db()

        data = db.ActivityRecords.find_one({'_id': ObjectId(_id)})

        return data

    @staticmethod
    def __parse_cursor(cursor) -> list[dict]:
        records = [{
            'id': str(record['_id']),
            'time': datetime.fromtimestamp(record['time'] / 1000.0),
            'user': str(record['user']),
            'event': record['event'] if record['event'] in ActivityRecord.Event else ActivityRecord.Event.ERROR,
            'detail': record['detail']
        } for record in cursor]

        return records