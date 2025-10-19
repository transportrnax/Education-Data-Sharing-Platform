from app.main.User import User
from ...extensions import mongo
import re

class PublicDataConsumer(User):
    """Level 1: Can access public course info."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    @staticmethod
    def is_eligible(user: User) -> bool:
        return (
            isinstance(user.role, User.Roles)
            and user.access_level[0] is True  # Level 1 权限
        )

    def search_courses(self, keyword: str) -> list:
        """
        Search public courses from all organizations by keyword.
        """
        if not keyword:
            return []

        regex = re.compile(f".*{re.escape(keyword)}.*", re.IGNORECASE)
        return list(mongo.db["COURSE_INFO"].find({"title": regex}, {"_id": 0}))

    def list_all_courses(self) -> list:
        """
        View all public course listings.
        """
        return list(mongo.db["COURSE_INFO"].find({}, {"_id": 0}))
