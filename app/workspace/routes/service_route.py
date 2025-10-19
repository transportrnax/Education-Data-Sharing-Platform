# app/workspace/routes/service_route.py

from flask import request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from bson import ObjectId # 确保导入 ObjectId
from datetime import datetime, timezone
import logging #

from . import workspace_bp
from ..service.OrganizationService import OrganizationService
from ..service.WorkspaceService import WorkspaceService # 确保导入
from ..utils import ACTIVE, PENDING_EADMIN_APPROVAL, PENDING_SEADMIN_APPROVAL, REJECTED_BY_EADMIN, REJECTED_BY_SEADMIN, NOT_SUBMITTED
from app.main.User import User
from app.extensions import mongo

SERVICE_CONFIG_MAP = {
    'courseInfo': 'Course Information Sharing (Free)',
    'gpaRecord': 'Student GPA Record Access',
    'identityCheck': 'Student Identity Authentication',
    'thesisAccess': 'Thesis Sharing'
}

CONFIGURABLE_SERVICES_BY_PROVIDER = ['gpaRecord', 'identityCheck', 'thesisAccess']


def create_provider_notification(provider_user_id, organization_id, organization_name, service_key, service_display_name, oconvener_email):
    """
    Helper function to create a notification document.
    """
    notifications_collection = mongo.db.notifications 
    message = (
        f"Service '{service_display_name}' has been enabled for your organization "
        f"by administrator ({oconvener_email}). Please proceed to your Provider Dashboard "
        f"to configure its details (Base URL, Path, Schemas etc.) under the 'Manage Services' section."
    )
    try:
        if not isinstance(provider_user_id, ObjectId):
            provider_user_id_obj = ObjectId(provider_user_id)
        else:
            provider_user_id_obj = provider_user_id
        organization_id_for_db = organization_id
        notification_doc = {
            "user_id": provider_user_id_obj,
            "organization_id": organization_id_for_db,
            "organization_name": organization_name,
            "type": "SERVICE_CONFIGURATION_REQUIRED",
            "message": message,
            "service_name_to_configure": service_key,
            "service_display_name": service_display_name,
            "is_read": False,
            "created_at": datetime.now(timezone.utc),
            "link_to_action": url_for('datauser.provider_dashboard', _anchor='service-form', _external=False)
        }
        notifications_collection.insert_one(notification_doc)
        current_app.logger.info(f"Notification created for provider {provider_user_id} for service {service_key}")
        return True
    except Exception as e:
        current_app.logger.error(f"Error creating notification for provider {provider_user_id}, service {service_key}: {e}")
        return False

@workspace_bp.route('/services/set-availability', methods=['POST'])
@login_required
def oconvener_set_service_availability_route():
    """
    Handles setting the availability and scope of organization services based on the new form.
    Notifies providers if a configurable service is newly enabled.
    """
    if not hasattr(current_user, 'organization_id') or not current_user.organization_id:
        flash("User is not associated with an organization.", "service_availability_danger")
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    # 确保 current_user.organization_name 可用
    if not hasattr(current_user, 'organization_name') or not current_user.organization_name:
        flash("Organization name not found for the current user.", "service_availability_danger")
        # 你可能需要从 OrganizationService 获取组织名称
        # org_details = OrganizationService.get_organization_details(current_user.organization_id)
        # current_user.organization_name = org_details.get('name') if org_details else 'Unknown Organization'
        # 如果无法获取，则重定向或显示错误
        return redirect(url_for('workspace.oconvener_dashboard_page'))


    active_organization_entity = OrganizationService.get_organization_details(current_user.organization_id)
    if not active_organization_entity or active_organization_entity.get('status') != ACTIVE:
        flash("Organization is not active or setup is incomplete. Cannot manage services.", "service_availability_danger")
        return redirect(url_for('workspace.oconvener_dashboard_page'))

    service_configurations_to_save = {}
    notifications_to_send_details = [] # Store details for notifications

    current_org_services = active_organization_entity.get('services', {})

    for service_key, display_name in SERVICE_CONFIG_MAP.items():
        # 1. Get 'enabled' status from checkbox
        # Form name is like 'courseInfo_enabled', 'gpaRecord_enabled'
        is_enabled_from_form = request.form.get(f'{service_key}_enabled') == 'true'

        # 2. Get 'sharing_scope' from radio buttons
        # Form name is like 'courseInfo_scope', 'gpaRecord_scope'
        # Default to 'organization_only' if not provided or service is disabled
        sharing_scope_from_form = request.form.get(f'{service_key}_scope', 'organization_only')

        existing_service_config = current_org_services.get(service_key, {})

        # 3. Construct the configuration for this service
        new_config_for_service = {
            "enabled": is_enabled_from_form,
            "sharing_scope": sharing_scope_from_form if is_enabled_from_form else existing_service_config.get("sharing_scope", "organization_only"),
            "fee": float(request.form.get(f'{service_key}_fee', '0.00')),  # Get fee from form input
            "db_config_status": existing_service_config.get("db_config_status", "pending_provider_setup"),
            "needs_config_by_provider": service_key in CONFIGURABLE_SERVICES_BY_PROVIDER
        }

        # Specific handling for 'courseInfo'
        if service_key == 'courseInfo':
            new_config_for_service["fee"] = 0.00
            new_config_for_service["needs_config_by_provider"] = False
            new_config_for_service["db_config_status"] = "not_applicable" # Or whatever status indicates no provider config needed

        service_configurations_to_save[service_key] = new_config_for_service

        # Check if a configurable service was newly enabled
        was_previously_enabled = existing_service_config.get('enabled', False)
        if is_enabled_from_form and not was_previously_enabled and new_config_for_service["needs_config_by_provider"]:
            notifications_to_send_details.append({
                "service_key": service_key,
                "service_display_name": display_name
            })

    # Call WorkspaceService to save all configurations at once
    success, message = WorkspaceService.set_service_availability(
        organization_id=current_user.organization_id,
        service_configurations=service_configurations_to_save, # Pass the whole dict
        set_email=current_user.email
    )

    flash(message, "service_availability_success" if success else "service_availability_danger")

    # Trigger notifications if save was successful and there are services that were newly enabled
    if success and notifications_to_send_details:
        providers_notified_for_services = []
        users_collection = mongo.db.users
        providers_in_org = users_collection.find({
            "organization_id": current_user.organization_id,
            "access_level.2": True  # Assuming index 2 is 'Private data provision'
        })
        
        provider_docs_list = list(providers_in_org) # Convert cursor to list to iterate multiple times if needed

        for notif_detail in notifications_to_send_details:
            service_key = notif_detail["service_key"]
            service_display_name = notif_detail["service_display_name"]
            
            for provider_doc in provider_docs_list: # Iterate over the fetched list
                provider_user_id = provider_doc["_id"] # This should be ObjectId
                if not isinstance(provider_user_id, ObjectId): # Defensive check
                    try:
                        provider_user_id = ObjectId(provider_user_id)
                    except Exception:
                        current_app.logger.warning(f"Could not convert provider user ID {provider_user_id} to ObjectId.")
                        continue
                
                create_provider_notification(
                    provider_user_id=provider_user_id,
                    organization_id=current_user.organization_id, # Pass as is (string or ObjectId based on your User model)
                    organization_name=current_user.organization_name,
                    service_key=service_key,
                    service_display_name=service_display_name,
                    oconvener_email=current_user.email
                )
            providers_notified_for_services.append(service_display_name)
        
        if providers_notified_for_services:
            flash(f"Providers in your organization have been notified to configure: {', '.join(providers_notified_for_services)}.", "info")

    return redirect(url_for('workspace.oconvener_dashboard_page'))