from app.main.User import User
from ...extensions import mongo
from ..services.interface_dispatcher import dispatch_service_request

class PrivateDataConsumer(User):
    """Level 2: Can access paid services like thesis or identity verification."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def is_eligible(user: User) -> bool:
        return (
            isinstance(user.role, User.Roles)
            and user.access_level[1] is True  # Level 2 权限
        )

    def access_service(self, service_name: str, target_org: str, input_data: dict):
        """
        Request a configured service (like identity verification or thesis) from another org.
        """
        service = mongo.db["SERVICE_CONFIG"].find_one({
            "organization": target_org,
            "service_name": service_name
        })
        print("INPUT TYPE:", type(input_data), "CONTENT:", input_data)

        if not service:
            return {"error": "SERVICE_NOT_AVAILABLE"}

        return dispatch_service_request(service["config"], input_data)
