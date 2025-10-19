from ...extensions import mongo
from datetime import datetime, timezone

class Policy:
    """Model to manage service access policies for consumers."""

    COLLECTION = "POLICIES"

    def __init__(self, consumer_email: str, organization: str, service_name: str, 
                 access_level: str, status: str = "active"):
        self.consumer_email = consumer_email
        self.organization = organization
        self.service_name = service_name
        self.access_level = access_level
        self.status = status
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self):
        return {
            "consumer_email": self.consumer_email,
            "organization": self.organization,
            "service_name": self.service_name,
            "access_level": self.access_level,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    def save(self):
        mongo.db[self.COLLECTION].replace_one(
            {
                "consumer_email": self.consumer_email,
                "service_name": self.service_name
            },
            self.to_dict(),
            upsert=True
        )

    @staticmethod
    def delete(consumer_email: str, service_name: str) -> bool:
        result = mongo.db[Policy.COLLECTION].delete_one({
            "consumer_email": consumer_email,
            "service_name": service_name
        })
        return result.deleted_count > 0

    @staticmethod
    def find_by_consumer(consumer_email: str) -> list:
        return list(mongo.db[Policy.COLLECTION].find(
            {"consumer_email": consumer_email, "status": "active"},
            {"_id": 0}
        ))

    @staticmethod
    def find_by_service(organization: str, service_name: str) -> list:
        return list(mongo.db[Policy.COLLECTION].find(
            {
                "organization": organization,
                "service_name": service_name,
                "status": "active"
            },
            {"_id": 0}
        ))

    @staticmethod
    def find_by_consumer_and_service(consumer_email: str, service_name: str) -> dict:
        """根据消费者邮箱和服务名称查找策略"""
        return mongo.db[Policy.COLLECTION].find_one(
            {
                "consumer_email": consumer_email,
                "service_name": service_name,
                "status": "active"
            },
            {"_id": 0}
        )

    @staticmethod
    def find_active_policies() -> list:
        """查找所有活跃的策略"""
        return list(mongo.db[Policy.COLLECTION].find(
            {"status": "active"},
            {"_id": 0}
        ))

    @staticmethod
    def update_organization_name(old_name: str, new_name: str) -> bool:
        """Update organization name across all policies"""
        try:
            result = mongo.db[Policy.COLLECTION].update_many(
                {"organization": old_name},
                {"$set": {"organization": new_name}}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating organization name in policies: {str(e)}")
            return False 