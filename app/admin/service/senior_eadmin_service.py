# app/admin/service/senior_eadmin_service.py
from flask import current_app
from bson import ObjectId
from datetime import datetime, timezone
from app.extensions import mongo
from app.main.User import User # EAdmin 角色定义
from app.admin.models import SeniorEAdmin # SeniorEAdmin 模型
# 导入状态常量
from .Eadmin_service import PENDING_SEADMIN_APPROVAL, ACTIVE, REJECTED_BY_SEADMIN, PENDING_EADMIN_APPROVAL

class SeniorEAdminService:

    def get_pending_organizations_for_senior_approval(self, senior_eadmin: SeniorEAdmin):
        """
        获取等待 Senior EAdmin 审批的组织列表。
        这些组织是已经被 EAdmin 批准过的。
        """
        if not senior_eadmin or senior_eadmin.role != User.Roles.SENIOR_EADMIN:
            current_app.logger.warning("Unauthorized attempt to view pending SEAdmin approvals.")
            return [], "Unauthorized"

        try:
            org_requests_collection = mongo.db.org_register_request
            # 查询状态为 "pending_seadmin_approval" 的申请
            pending_organizations = list(org_requests_collection.find({"status": PENDING_SEADMIN_APPROVAL}).sort("submit_time", 1))
            return pending_organizations, None
        except Exception as e:
            current_app.logger.error(f"Error fetching organizations pending SEAdmin approval: {e}")
            return [], "Database error while fetching requests."

    def approve_organization_final(self, senior_eadmin: SeniorEAdmin, request_id_str: str) -> tuple[bool, str]:
        """
        Senior EAdmin 最终批准组织。
        """
        if not senior_eadmin or senior_eadmin.role != User.Roles.SENIOR_EADMIN:
            return False, "Unauthorized action."

        try:
            request_id = ObjectId(request_id_str)
        except Exception:
            return False, "Invalid request ID format."

        org_requests_collection = mongo.db.org_register_request
        org_request = org_requests_collection.find_one({"_id": request_id, "status": PENDING_SEADMIN_APPROVAL})

        if not org_request:
            return False, "Organization request not found or not pending Senior EAdmin approval."

        try:
            # 1. 更新 org_register_request 状态为 active
            update_result_request = org_requests_collection.update_one(
                {"_id": request_id},
                {
                    "$set": {
                        "status": ACTIVE, # 最终批准状态
                        "seadmin_approved_by": senior_eadmin.email, # 记录由哪个SEadmin批准
                        "seadmin_approved_at": datetime.now(timezone.utc),
                        "last_updated_at": datetime.now(timezone.utc)
                    }
                }
            )

            if update_result_request.modified_count == 0:
                # 可能在检查和更新之间状态被改变了
                return False, "Failed to update organization request status. It might have been processed already."

            # 2. 更新 organizations 集合中的记录 (如果你的 EAdmin 审批步骤会创建或更新这个集合)
            #    如果 EAdmin 审批时只更新了 org_register_request，那么这一步需要确保 organizations 集合也同步
            #    假设 organizations 集合是在 EAdmin 批准时创建/更新为 PENDING_SEADMIN_APPROVAL 或类似状态的
            #    或者，如果 organizations 集合是在 OConvener 提交时就创建了，这里只是更新状态
            organizations_collection = mongo.db.organizations # 假设你的主组织表叫 'organizations'
                                                              # 或者沿用 org_register_request 作为唯一记录源，则此步骤省略或调整

            # 以下是假设你有一个独立的 organizations 集合，并且 EAdmin 审批后会将其状态更新为类似 PENDING_SEADMIN_APPROVAL
            # 如果不是这样，请调整此逻辑
            org_id_from_request = org_request.get("organization_id") # 从请求中获取组织ID
            if org_id_from_request:
                update_org_table = organizations_collection.update_one(
                    {"organization_id": org_id_from_request}, # 根据实际的 organizations 表结构调整查询字段
                    {
                        "$set": {
                            "status": ACTIVE,
                            "name": org_request.get("organization_name"), # 确保名称也更新
                            "last_updated_at": datetime.now(timezone.utc)
                            # 可以添加更多SEadmin批准的信息
                        },
                        "$setOnInsert": { # 如果 EAdmin 步骤没有创建主表记录，这里可以创建
                            "organization_id": org_id_from_request,
                            "created_oconvener": org_request.get("submit_user_id"), # 根据实际字段调整
                             "created_at": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True # 如果记录不存在则创建
                )
                current_app.logger.info(f"Organization table record for {org_id_from_request} updated/created by SEAdmin approval. Matched: {update_org_table.matched_count}, Upserted: {update_org_table.upserted_id}")

            # (可选) 发送通知给 O-Convener
            # ...

            current_app.logger.info(f"Organization request {request_id_str} approved by Senior EAdmin {senior_eadmin.email}")
            # ActivityRecord log
            return True, f"Organization '{org_request.get('organization_name')}' approved and set to active."

        except Exception as e:
            current_app.logger.error(f"Error during final approval of org request {request_id_str} by SEAdmin {senior_eadmin.email}: {e}")
            # 可考虑回滚 org_register_request 的状态更新
            return False, "A database error occurred during final approval."

    def reject_organization_final(self, senior_eadmin: SeniorEAdmin, request_id_str: str, rejection_reason: str) -> tuple[bool, str]:
        """
        Senior EAdmin 最终拒绝组织。
        """
        if not senior_eadmin or senior_eadmin.role != User.Roles.SENIOR_EADMIN:
            return False, "Unauthorized action."

        if not rejection_reason or not rejection_reason.strip():
            return False, "Rejection reason is required."

        try:
            request_id = ObjectId(request_id_str)
        except Exception:
            return False, "Invalid request ID format."

        org_requests_collection = mongo.db.org_register_request
        org_request = org_requests_collection.find_one({"_id": request_id, "status": PENDING_SEADMIN_APPROVAL})

        if not org_request:
            return False, "Organization request not found or not pending Senior EAdmin approval."

        try:
            update_result = org_requests_collection.update_one(
                {"_id": request_id},
                {
                    "$set": {
                        "status": REJECTED_BY_SEADMIN, # SEadmin 拒绝状态
                        "rejection_reason": rejection_reason,
                        "seadmin_rejected_by": senior_eadmin.email,
                        "seadmin_rejected_at": datetime.now(timezone.utc),
                        "last_updated_at": datetime.now(timezone.utc)
                    }
                }
            )

            if update_result.modified_count == 0:
                return False, "Failed to update organization request status for rejection."

            # (可选) 更新 organizations 集合中的状态为 REJECTED_BY_SEADMIN
            organizations_collection = mongo.db.organizations
            org_id_from_request = org_request.get("organization_id")
            if org_id_from_request:
                 organizations_collection.update_one(
                    {"organization_id": org_id_from_request},
                    {"$set": {"status": REJECTED_BY_SEADMIN, "last_updated_at": datetime.now(timezone.utc)}}
                )


            current_app.logger.info(f"Organization request {request_id_str} rejected by Senior EAdmin {senior_eadmin.email}. Reason: {rejection_reason}")
            # ActivityRecord log
            return True, f"Organization '{org_request.get('organization_name')}' rejected."

        except Exception as e:
            current_app.logger.error(f"Error during final rejection of org request {request_id_str} by SEAdmin {senior_eadmin.email}: {e}")
            return False, "A database error occurred during final rejection."