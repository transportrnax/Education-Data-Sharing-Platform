from flask import current_app
# Organization Status Constants
PENDING_EADMIN_APPROVAL = "pending_eadmin_approval"  # EAdmin 审批后的状态，等待 SEadmin 审批
PENDING_SEADMIN_APPROVAL = "pending_seadmin_approval" # 新增状态，专指等待SEadmin审批
ACTIVE = "active"  # SEAdmin 批准后的状态
REJECTED_BY_EADMIN = "rejected_by_eadmin" # EAdmin 拒绝
REJECTED_BY_SEADMIN = "rejected_by_seadmin" # SEadmin 拒绝 (新增)
NOT_SUBMITTED = "not_submitted"

def allowed_file_for_proof(filename: str) -> bool:
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS_DOCS', {'pdf'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def allowed_file_for_excel(filename: str) -> bool:
    allowed_extensions = current_app.config.get('ALLOWED_EXCEL_EXTENSIONS', {'xlsx', 'xls'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions