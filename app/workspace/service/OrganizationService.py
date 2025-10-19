from datetime import datetime, timezone
import re # For email validation if used here
from bson import ObjectId
from app.extensions import mongo
from app.models.ActivityRecord import ActivityRecord
# Assuming User base class and OConvener are now in .models
from ..models import Workspace, OConvener 
from app.main.User import User 
from app.auth.utils import is_valid_email
from datetime import datetime, UTC
from ..utils import ACTIVE, PENDING_EADMIN_APPROVAL, PENDING_SEADMIN_APPROVAL, REJECTED_BY_EADMIN, REJECTED_BY_SEADMIN, NOT_SUBMITTED

class OrganizationService:
    @classmethod
    def submit_org_for_approval(cls, oconvener: OConvener, org_name: str, proof_document: str, email: str) -> tuple[bool, str]:
        '''
        Submit organization registration request for EAdmin
        args:
            oconvener: who send this request
            org_name: registered organization name
            email: get the verfication code
            proof_document: to proof the organizatoin document 
        '''
        if not oconvener.organization_id:
            return False, "Oconvener account missing"
        
        if not is_valid_email(email):
            return False, "Invalid email format"
        if oconvener.organization_name != org_name:
            oconvener.organization_name = org_name
            try:
                user_collection = mongo.db.users
                user_object_id_to_update = None

                if oconvener.user_id and oconvener.user_id != "-1":
                    try:
                        user_object_id_to_update = ObjectId(oconvener.user_id)
                    except Exception as e_oid: # Handles invalid ObjectId format
                        #ActivityRecord(userAccount=oconvener.email, activityName="User ID format error for update", details=f"Invalid ObjectId string: {oconvener.user_id}, Error: {str(e_oid)}").addRecord()
                        return False, f"Invalid user ID format ({oconvener.user_id}) for updating user record."
                
                if not user_object_id_to_update:
                    #ActivityRecord(userAccount=oconvener.email, activityName="User ID missing for update", details=f"User ID was '{oconvener.user_id}', resulting in no ObjectId for update.").addRecord()
                    return False, "User ID is missing or invalid for updating user record."

                update_result = user_collection.update_one(
                    {"_id": user_object_id_to_update}, # Use ObjectId here
                    {"$set": {"organization_name": oconvener.organization_name, "last_updated_at": datetime.now(UTC)}}
                )

                # Corrected typo: match_count -> matched_count
                if update_result.matched_count == 0:
                    #ActivityRecord(userAccount=oconvener.email, activityName="The update of the user organization name failed", details=f"User not found with _id: {user_object_id_to_update}").addRecord()
                    return False, "Failed to update user record: User not found in database."
            except Exception as e:
                #ActivityRecord(userAccount=oconvener.email, activityName="User organization name update database error", details=str(e)).addRecord()
                # It's helpful to log the actual exception 'e' to the console or a log file for debugging
                return False, "Failed to update user record due to a database error."

            
        pending_collection = mongo.db.org_register_request
        oconvener_actual_id = oconvener.user_id if oconvener.user_id and oconvener.user_id != "-1" else None
        # check whether this organization exist
        existing_request = pending_collection.find_one({
            "oconvener_user_id": oconvener_actual_id, 
            "organization_id_on_user": oconvener.organization_id,
            "status": PENDING_EADMIN_APPROVAL
        })
        # if exist return false
        if existing_request:
            ActivityRecord(userAccount=oconvener.email, activityName="Failed register organization", details=f"Organization {oconvener.organization_name} already exist").addRecord()
            return False, f"Organization '{org_name}' already submitted and pending approval."

        # if registration not exist insert to org_register_request(wating for appproval)
        request_data = {
            "submit_user_id": oconvener_actual_id,
            "organization_id": oconvener.organization_id,
            "organization_name": oconvener.organization_name,
            "proof_document_path": proof_document,
            "status": PENDING_EADMIN_APPROVAL,
            "submit_time": datetime.now(UTC),
            "email": email   
        }

        pending_collection.insert_one(request_data)
        org_collection = mongo.db.org_register_request
        org_collection.insert_one(request_data)

        #ActivityRecord(userAccount=oconvener.email, activityName="Organization submitted for approval", details=f"Org ID on User: {oconvener.organization_id}, Submitted Name: {org_name}").addRecord()
        return True, "Organization '{org_name}' submitted for E-Admin approval."
    
    @classmethod
    def update_org_name(cls, oconvener: OConvener, new_name: str) -> bool:
        org_collection = mongo.db.org_register_request
        users_collection = mongo.db.users
        now_utc = datetime.now(UTC)
        try:
            # update 'organizations' collection org name
            result_org_update = org_collection.update_one(
                {"organization_id": oconvener.organization_id, "status": ACTIVE}, 
                {"$set": {"organization_name": new_name, "last_updated_at": now_utc}}
            )
            if result_org_update.matched_count == 0:
                message = f"Organization {oconvener.organization_id} not found or not active for name update in 'organizations' collection."
                print(message)
                return False, message

            oconvener.organization_name = new_name
            # update all user belongs to organization
            update_users_result = users_collection.update_many(
                {"organization_id": oconvener.organization_id}, 
                {"$set": {"organization_name": new_name, "last_updated_at": now_utc}}
            )
                    
            # ActivityRecord(
            #     userAccount=oconvener.email, 
            #     activityName="Organization Name Updated (Org Table and All Members)",
            #     details=f"Org ID: {oconvener.organization_id}, New Name: {new_name}, Users Updated: {update_users_result.modified_count}"
            # ).addRecord()
            return True, f"Organization name updated to '{new_name}' successfully for the organization and its members."

        except Exception as e:
            error_message = f"Error updating organization name for {oconvener.organization_id}: {e}"
            print(error_message)
            #ActivityRecord(userAccount=oconvener.email, activityName="Org Name Update DB Error", details=str(e)).addRecord()
            return False, f"Server error during organization name update: {e}"

    @classmethod
    def get_organization_details(cls, organization_id: str) -> dict[str, any] | None:
        org_collection = mongo.db.org_register_request
        org_doc = org_collection.find_one({"organization_id": organization_id})
        if org_doc and '_id' in org_doc and not isinstance(org_doc['_id'], str):
            org_doc['_id'] = str(org_doc['_id']) 
        return org_doc

    
    @classmethod
    def get_latest_organization_approval_request(cls, oconvener_user_id: str, organization_id: str) -> dict[str, any] | None:
        """Fetches the most recent approval request. oconvener_user_id should be ObjectId."""
        if not oconvener_user_id or not organization_id:
            return None
        approval_requests_coll = mongo.db.org_register_request
        result = approval_requests_coll.find_one(
            {"submit_user_id": oconvener_user_id, "organization_id": organization_id}
        )
        return result