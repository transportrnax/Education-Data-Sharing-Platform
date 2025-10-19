from ...extensions import mongo
from datetime import datetime, timezone

class ServiceConfig:
    """Model to manage external service configuration by private data providers."""

    COLLECTION = "SERVICE_CONFIG"

    def __init__(self, provider_email: str, organization: str, service_name: str, config: dict):
        self.provider_email = provider_email
        self.organization = organization
        self.service_name = service_name
        self.config = config
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self):
        return {
            "provider_email": self.provider_email,
            "organization": self.organization,
            "service_name": self.service_name,
            "config": self.config,
            "created_at": self.created_at
        }

    def save(self):
        mongo.db[self.COLLECTION].replace_one(
            {
                "provider_email": self.provider_email,
                "service_name": self.service_name
            },
            self.to_dict(),
            upsert=True
        )

    @staticmethod
    def delete(provider_email: str, service_name: str) -> bool:
        result = mongo.db[ServiceConfig.COLLECTION].delete_one({
            "provider_email": provider_email,
            "service_name": service_name
        })
        return result.deleted_count > 0

    @staticmethod
    def find_by_org(org: str) -> list:
        return list(mongo.db[ServiceConfig.COLLECTION].find(
            {"organization": org}, {"_id": 0}
        ))

    @staticmethod
    def find_by_service(org: str, service_name: str) -> dict:
        return mongo.db[ServiceConfig.COLLECTION].find_one({
            "organization": org,
            "service_name": service_name
        }, {"_id": 0})
    