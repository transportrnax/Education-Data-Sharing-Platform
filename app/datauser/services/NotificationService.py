
from bson import ObjectId
from datetime import datetime, timezone
from app.extensions import mongo

class NotificationService:
    @staticmethod
    def get_user_notifications(organization_name: str):
        notifications = list(mongo.db.notifications.find(
            {"organization_name": organization_name}
        ).sort("created_at", -1))
        for n in notifications:
            n["_id"] = str(n["_id"])
            n["user_id"] = str(n["user_id"])
            n["organization_id"] = str(n["organization_id"]) if "organization_id" in n else None
            n["created_at"] = n.get("created_at").isoformat() if n.get("created_at") else None
            n["read_at"] = n.get("read_at").isoformat() if n.get("read_at") else None
        return notifications

    @staticmethod
    def mark_as_read(notification_id: str):
        notif = mongo.db.notifications.find_one({
            "_id": ObjectId(notification_id),
        })
        if not notif:
            return False, "Notification not found or not owned by user."
        if notif.get("is_read"):
            return True, "Already marked as read."
        mongo.db.notifications.update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}}
        )
        return True, "Notification marked as read."