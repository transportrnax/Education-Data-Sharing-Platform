from ...extensions import mongo
from datetime import datetime, timezone
import uuid

class CourseInfo:
    """Model to manage public course information."""

    COLLECTION = "COURSE_INFO"

    def __init__(self, title: str, units: str, description: str,
                 provider_email: str, organization: str, _id: str = None,
                 created_at: datetime = None):
        self._id = _id or str(uuid.uuid4())
        self.title = title
        self.units = units
        self.description = description
        self.provider_email = provider_email
        self.organization = organization
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self):
        return {
            "_id": self._id,
            "title": self.title,
            "units": self.units,
            "description": self.description,
            "provider_email": self.provider_email,
            "organization": self.organization,
            "created_at": self.created_at
        }

    def save(self):
        mongo.db[self.COLLECTION].insert_one(self.to_dict())

    @staticmethod
    def update(course_id: str, provider_email: str, new_data: dict) -> bool: # FIXED: Added provider_email for security
        result = mongo.db[CourseInfo.COLLECTION].update_one(
            {"_id": course_id, "provider_email": provider_email}, {"$set": new_data} # FIXED: Include provider_email in query
        )
        return result.modified_count > 0

    @staticmethod
    def delete(course_id: str, provider_email: str) -> bool:
        result = mongo.db[CourseInfo.COLLECTION].delete_one({
            "_id": course_id,
            "provider_email": provider_email
        })
        return result.deleted_count > 0
    
    @staticmethod
    def delete_by_id(course_id: str, provider_email: str) -> bool:
        result = mongo.db[CourseInfo.COLLECTION].delete_one({
            "_id": course_id,
            "provider_email": provider_email
        })
        return result.deleted_count > 0


    @staticmethod
    def find_by_keyword(keyword: str) -> list:
        import re
        regex = re.compile(f".*{keyword}.*", re.IGNORECASE)
        return list(mongo.db[CourseInfo.COLLECTION].find({"title": regex}, {"_id": 0}))

    @staticmethod
    def find_by_provider(provider_email: str) -> list:
        # Remove the projection `{"_id": 0}` to include the _id field by default.
        # MongoDB includes _id by default if no projection or an inclusive projection is specified.
        return list(mongo.db[CourseInfo.COLLECTION].find(
            {"provider_email": provider_email}
        ))

    @staticmethod
    def find_all() -> list:
        return list(mongo.db[CourseInfo.COLLECTION].find({}, {"_id": 0}))