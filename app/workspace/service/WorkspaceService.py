from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from ..models import OConvener 
from app.extensions import mongo 
from app.models.ActivityRecord import ActivityRecord 
from ..models import Workspace, OConvener
from datetime import datetime, UTC
from flask import current_app
from ..utils import ACTIVE, PENDING_EADMIN_APPROVAL, PENDING_SEADMIN_APPROVAL, REJECTED_BY_EADMIN, REJECTED_BY_SEADMIN, NOT_SUBMITTED

class WorkspaceService:
    @classmethod
    def create_workspace(cls, oconvener: OConvener, name: str = None) -> Workspace:
        print(oconvener)
        created_oconvener_id  = str(oconvener.email) if hasattr(oconvener, 'email') and oconvener.email else None
        if not created_oconvener_id:
            #ActivityRecord(userAccount=oconvener.email, activityName="Failed create workspace-lack oconvener ID", details=f"Failed create workspace for {oconvener.organization_name}").addRecord()
            return None

        if not oconvener.organization_id or not oconvener.organization_name:
            #ActivityRecord(userAccount=oconvener.email, activityName="Failed create workspace-lack organization information", details=f"Failed create workspace for {oconvener.organization_name}").addRecord()
            return None
        
        workspaces_collection = mongo.db.workspaces
        existing_workspace = workspaces_collection.find_one({
            'organization_id': oconvener.organization_id,
            'organization_name': oconvener.organization_name
        })

        # check whether org has workspace
        if existing_workspace:
            #ActivityRecord(userAccount=oconvener.email, activityName="Failed created workspace-already exist workspace", details=f"organization {oconvener.organization_name} alreday has workspace {existing_workspace['name']}").addRecord()
            return None
        
        workspace_name = name if name else f"{oconvener.organization_name} workspace"

        workspace_doc: dict[str, Any] = {
            "name": workspace_name,
            "organization_id": oconvener.organization_id,
            "created_oconvener_id": created_oconvener_id
        }
        new_workspace = Workspace(workspace_doc=workspace_doc)
        workspace_data = new_workspace.to_dict()
        result = workspaces_collection.insert_one(workspace_data)

        if result.inserted_id:
            #ActivityRecord(userAccount=oconvener.email, activityName="Create workspace successfully!", details=f"Create workspace {workspace_name} for organization: {oconvener.organization_name} ").addRecord()
            return new_workspace
        else:
            #ActivityRecord(userAccount=oconvener.email, activityName="Failed create workspace successfully!", details=f"Failed create workspace {workspace_name} for organization: {oconvener.organization_name} ").addRecord()
            return None
        
    @classmethod
    def get_workspace_byid(cls, workspace_id: str, organizatio_id: str) -> Workspace:
        workspace_id_obj = ObjectId(workspace_id)
        workspace_data = mongo.db.workspaces.find_one({
            '_id': workspace_id_obj
        })
        return Workspace.from_dict(workspace_data) if workspace_data else None
    
    @classmethod
    def get_workspace_org(cls, organization_id: str)  -> Workspace:
        if not organization_id: 
            return None
        workspace_data = mongo.db.workspaces.find_one({"organization_id": organization_id})
        return Workspace.from_dict(workspace_data) if workspace_data else None
    
    @classmethod
    def set_service_availability(cls, organization_id: str, service_configurations: dict, set_email: str) -> tuple[bool, str]:
        org_collection = mongo.db.org_register_request # Assuming this collection stores active org details including services
        
        if not organization_id:
            current_app.logger.warning("set_service_availability: Organization ID is required.")
            return False, "Organization ID is required."

        current_org_doc = org_collection.find_one({"organization_id": organization_id, "status": ACTIVE})
        if not current_org_doc:
            current_app.logger.warning(f"set_service_availability: Active organization with ID {organization_id} not found.")
            return False, "Active organization not found."
        
        updates_for_mongo_services_field = {}
        existing_services_config = current_org_doc.get("services", {})
        any_actual_change = False

        for service_key, new_config_from_route in service_configurations.items():
            current_specific_service_config = existing_services_config.get(service_key, {})
            print(new_config_from_route)
            # --- Fee Parsing Logic ---
            fee_str = new_config_from_route.get("fee")
            print(fee_str)
            parsed_fee = current_specific_service_config.get("fee", 0.0) # Default to existing fee or 0.0

            if fee_str is not None and str(fee_str).strip() != "":
                try:
                    temp_fee = float(fee_str)
                    if temp_fee >= 0:
                        parsed_fee = round(temp_fee, 2) # Round to 2 decimal places for currency
                    else:
                        current_app.logger.warning(
                            f"Negative fee value '{fee_str}' provided for service '{service_key}' in org '{organization_id}'. "
                            f"Using existing/default fee: {parsed_fee:.2f}"
                        )
                except ValueError:
                    current_app.logger.warning(
                        f"Invalid fee value '{fee_str}' (not a number) provided for service '{service_key}' in org '{organization_id}'. "
                        f"Using existing/default fee: {parsed_fee:.2f}"
                    )
            # --- End Fee Parsing Logic ---

            final_config_for_service = {
                "enabled": new_config_from_route.get("enabled", False), # Assumes "enabled" comes as boolean or string "true"
                "sharing_scope": new_config_from_route.get("sharing_scope", "organization_only"),
                "fee": parsed_fee, # Use the parsed and validated fee
                "needs_config_by_provider": new_config_from_route.get("needs_config_by_provider", service_key not in ['courseInfo']),
                "db_config_status": new_config_from_route.get("db_config_status",
                                                              current_specific_service_config.get("db_config_status",
                                                                                                "pending_provider_setup" if service_key not in ['courseInfo'] else "not_applicable"))
            }
            
            # Ensure 'enabled' is a boolean
            if isinstance(final_config_for_service["enabled"], str):
                final_config_for_service["enabled"] = final_config_for_service["enabled"].lower() == 'true'

            # Special handling for courseInfo (always free)
            if service_key == 'courseInfo':
                final_config_for_service["fee"] = 0.0
                final_config_for_service["needs_config_by_provider"] = False
                final_config_for_service["db_config_status"] = "not_applicable"

            # Check if there's any actual change compared to the existing configuration for this service
            if final_config_for_service != current_specific_service_config:
                any_actual_change = True
            
            updates_for_mongo_services_field[f"services.{service_key}"] = final_config_for_service

        if not any_actual_change:
            current_app.logger.info(f"No actual changes to service configurations for org {organization_id}.")
            return True, "No changes to service availability were detected or applied."

        try:
            result = org_collection.update_one(
                {"organization_id": organization_id, "status": ACTIVE},
                {"$set": updates_for_mongo_services_field, "$currentDate": {"last_updated_at": True}}
            )

            if result.modified_count > 0:
                # Construct log details from the actual updates applied
                log_details_parts = []
                for key, config in updates_for_mongo_services_field.items():
                    service_name = key.split('.')[-1] # Get service name like 'gpaRecord' from 'services.gpaRecord'
                    log_details_parts.append(
                        f"{service_name}: "
                        f"Enabled={config.get('enabled', False)}, "
                        f"Scope={config.get('sharing_scope', 'N/A')}, "
                        f"Fee={config.get('fee', 0.0):.2f}" # Format fee to 2 decimal places
                    )
                log_details_str = "; ".join(log_details_parts)
                
                # ActivityRecord(userAccount=set_email, activityName="Service Configurations Updated", details=f"OrgID:{organization_id}, Details: {log_details_str}").addRecord()
                current_app.logger.info(f"Service configurations for organization '{organization_id}' updated by '{set_email}'. Details: {log_details_str}")
                return True, "Service configurations updated successfully."
            elif result.matched_count > 0: # Document found but no fields were different
                current_app.logger.info(f"Organization '{organization_id}' matched but no service configurations were modified (data was identical).")
                return True, "No effective changes made to service configurations."
            else: # No document matched the query (e.g., org_id not found or status not active)
                current_app.logger.warning(f"set_service_availability: Failed to find active organization {organization_id} to update (matched_count=0).")
                return False, "Organization not found or not active."

        except Exception as e:
            current_app.logger.error(f"Error updating service configurations for org {organization_id} in DB: {e}", exc_info=True)
            # ActivityRecord(userAccount=set_email, activityName="Service Config Update DB Error", details=str(e)).addRecord()
            return False, f"Server error during service configuration update: {str(e)}"

    @classmethod
    def get_organization_logs(cls, organization_id: str, performed_by_email: str, page: int = 1, limit: int = 15) -> tuple[list[dict[str, any]], int]: 
        if not organization_id:
            return [], 0

        users_collection = mongo.db.users
        log_collection = mongo.db.activity_log
        
        member_emails = [member_doc['email'] for member_doc in users_collection.find(
            {"organization_id": organization_id}, {"email": 1}) if 'email' in member_doc
        ]
        if performed_by_email and performed_by_email not in member_emails:
            oconvener_user = users_collection.find_one({"email": performed_by_email, "organization_id": organization_id})
            if oconvener_user:
                 member_emails.append(performed_by_email)

        if not member_emails: 
            return [],0

        query = {"userAccount": {"$in": member_emails}}
        total_logs_count = log_collection.count_documents(query)

        skip_value = (page - 1) * limit
        if skip_value < 0: 
            skip_value = 0
        
        logs_cursor = log_collection.find(query).sort([("activityTime", -1), ("_id", -1)]).skip(skip_value).limit(limit)
        logs_for_page = list(logs_cursor)
        return logs_for_page, total_logs_count