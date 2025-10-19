from pymongo import MongoClient
from app import mongo
from flask import current_app
from pymongo.errors import PyMongoError
from ..models.service_config import ServiceConfig
from ..models.course_info import CourseInfo
from app.main.User import User
import requests
from datetime import datetime, timezone
import uuid

class PrivateDataProvider(User):
    SERVICE_COLLECTION = "SERVICE_CONFIG"
    COURSE_COLLECTION = "COURSE_INFO"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = self._extract_org_from_email()

    @staticmethod
    def find_by_email(email: str):
        user_doc = mongo.db.USERS.find_one({"email": email})
        if user_doc:
            return PrivateDataProvider(user_doc)
        return None

    @staticmethod
    def is_eligible(user: User) -> bool:
        return user.access_level[2] is True

    def _extract_org_from_email(self) -> str | None:
        """
        Safely extracts the organization name from the provider's email.
        Returns organization name in lowercase or None if extraction fails.
        """
        if not self.email or not isinstance(self.email, str) or '@' not in self.email:
            current_app.logger.error(f"Cannot extract organization: Invalid email for provider: {self.email}")
            return None
        try:
            domain_part = self.email.split('@')[-1]
            return domain_part.split('.')[0].lower()
        except IndexError:
            current_app.logger.error(f"Cannot extract organization: Error parsing email: {self.email}")
            return None

    def add_course(self, course_data: dict) -> str:
        required_fields = {"title", "units", "description"}
        if not required_fields.issubset(course_data):
            current_app.logger.warning(f"Add course failed: Missing required fields. Data: {course_data}")
            return "COURSE_DATA_INVALID"

        if not self.email:
            current_app.logger.error("Add course failed: Provider email is missing.")
            return "PROVIDER_EMAIL_MISSING"

        organization = self._extract_org_from_email()
        if not organization:
            return "ORGANIZATION_EXTRACTION_FAILED"

        try:
            exists = mongo.db[self.COURSE_COLLECTION].find_one({
                "title": course_data["title"],
                "units": course_data["units"],
                "organization": organization
            })
            if exists:
                current_app.logger.info(f"Add course attempt failed: Course already exists. Data: {course_data}, Org: {organization}")
                return "COURSE_ALREADY_EXISTS"

            new_course_doc = {
                "_id": str(uuid.uuid4()),
                "title": course_data["title"],
                "units": course_data["units"],
                "description": course_data["description"],
                "provider_email": self.email,
                "organization": organization,
                "created_at": datetime.now(timezone.utc)
            }

            mongo.db[self.COURSE_COLLECTION].insert_one(new_course_doc)
            current_app.logger.info(f"Course added successfully by {self.email}: {new_course_doc['_id']} - {new_course_doc['title']}")
            return "COURSE_ADDED"

        except PyMongoError as e:
            current_app.logger.error(f"MongoDB error during add_course by {self.email}: {e}")
            return "DATABASE_ERROR"
        except Exception as e:
            current_app.logger.error(f"Unexpected error in add_course by {self.email}: {e}", exc_info=True)
            return "UNEXPECTED_ERROR"

    def list_courses(self) -> list:
        """Lists courses provided by this provider."""
        if not self.email:
            current_app.logger.error("List courses failed: Provider email is missing.")
            return []
        try:
            return CourseInfo.find_by_provider(self.email)
        except PyMongoError as e:
            current_app.logger.error(f"MongoDB error during list_courses for {self.email}: {e}")
            return []
        except Exception as e:
            current_app.logger.error(f"Unexpected error in list_courses for {self.email}: {e}", exc_info=True)
            return []

    def update_course(self, course_id: str, update_data: dict) -> bool:
        # FIXED: Changed to CourseInfo.update and passed self.email
        return CourseInfo.update(course_id, self.email, update_data)

    def delete_course(self, course_id: str) -> bool:
        return CourseInfo.delete_by_id(course_id, self.email)

    # Removed duplicate list_courses method (it was defined twice)

    def add_service_config(self, service_data: dict) -> str:
        required_fields = {"service_name", "base_url", "path", "method", "input", "output"}
        if not required_fields.issubset(service_data):
            current_app.logger.warning(f"Add service config failed: Missing required fields. Data: {service_data}")
            return "SERVICE_CONFIG_DATA_INVALID"

        config_payload = {
            "base_url": service_data["base_url"],
            "path": service_data["path"],
            "method": service_data["method"],
            "input": service_data["input"],
            "output": service_data["output"]
        }

        try:
            # FIXED: Instantiate ServiceConfig and call its instance method .save()
            config_instance = ServiceConfig(
                provider_email=self.email,
                organization=self.organization,
                service_name=service_data["service_name"],
                config=config_payload
            )
            config_instance.save() # Call the instance method. Assuming it handles upsert.
            return "SERVICE_CONFIGURED" # Return a consistent success string

        except PyMongoError as e:
            current_app.logger.error(f"MongoDB error during add_service_config by {self.email}: {e}")
            return "DATABASE_ERROR"
        except Exception as e:
            current_app.logger.error(f"Unexpected error in add_service_config by {self.email}: {e}", exc_info=True)
            return "UNEXPECTED_ERROR"

    def delete_service_config(self, service_name: str) -> bool:
        return ServiceConfig.delete(self.email, service_name)

    def list_service_configs(self) -> list:
        # Fixed in previous iteration to use find_by_org as ServiceConfig likely has this method
        return ServiceConfig.find_by_org(self.organization)

    def test_service_config(self, service_name: str, test_input: dict) -> dict:
        config_entry = ServiceConfig.find_by_service(self.organization, service_name)
        if not config_entry:
            return {"error": "SERVICE_NOT_FOUND"}
        try:
            config = config_entry["config"]
            url = f"{config['base_url'].rstrip('/')}/{config['path'].lstrip('/')}"
            method = config["method"].upper()
            response = requests.request(method, url, json=test_input, timeout=3)
            return {
                "status": "success" if response.status_code < 400 else "failed",
                "response": response.json()
            }
        except Exception as e:
            return {"error": f"DISPATCH_FAILED: {str(e)}"}