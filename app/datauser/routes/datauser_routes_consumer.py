from flask import Blueprint, request, jsonify, send_file, render_template
from flask import current_app as app
from ..models.service_config import ServiceConfig
from ..services.interface_dispatcher import dispatch_service_request
from ..models.public_consumer import PublicDataConsumer
from ..models.private_consumer import PrivateDataConsumer
from ...extensions import mongo, get_db
from datetime import datetime, timezone
import requests
import os
from flask import send_from_directory

consumer_bp = Blueprint("consumer", __name__, url_prefix="/api/consumer")

def get_user_email():
    return request.headers.get("X-User-Email", "")

# 1. Search or List Public Courses
@consumer_bp.route("/courses", methods=["GET"])
def search_courses():
    keyword = request.args.get("keyword", "").strip()
    consumer = PublicDataConsumer({})
    if keyword:
        results = consumer.search_courses(keyword)
    else:
        results = consumer.list_all_courses()
    return jsonify(results)

# 1b. List All Courses (no keyword)
@consumer_bp.route("/courses/all", methods=["GET"])
def list_all_courses():
    courses = list(mongo.db.COURSE_INFO.find({}, {"_id": 0}))
    return jsonify(courses)

@consumer_bp.route("/courses/list", methods=["GET"])
def list_show_courses():
    consumer = PublicDataConsumer({})
    return render_template("datauser/course.html", courses = consumer.list_all_courses())

# 1c. List All Theses
@consumer_bp.route("/theses", methods=["GET"])
def list_theses():
    theses = list(mongo.db.THESIS.find({}, {"_id": 0, "pdf_path": 0}))
    return jsonify(theses)

# 2. View Thesis Metadata
@consumer_bp.route("/thesis/metadata", methods=["GET"])
def view_thesis_metadata():
    title = request.args.get("title", "").strip()
    if not title:
        return jsonify({"error": "MISSING_TITLE"}), 400

    record = mongo.db.THESIS.find_one({"title": {"$regex": title, "$options": "i"}})
    if not record:
        return jsonify({"message": "NOT_FOUND"}), 404

    return jsonify({
        "thesis_id": record.get("_id"),
        "title": record.get("title"),
        "abstract": record.get("abstract"),
        "price": record.get("price", 0)
    })

# 3. View Quota Info
@consumer_bp.route("/quota", methods=["GET"])
def check_quota():
    email = request.args.get("email", "").strip()
    if not email:
        return jsonify({"error": "MISSING_EMAIL"}), 400

    record = mongo.db.USER_QUOTA.find_one({"user_email": email}) or {}
    return jsonify({
        "used_today": record.get("used_today", 0),
        "max_daily": record.get("max_daily", 5),
        "last_used": record.get("last_used")
    })

# 4. Check Account Balance
@consumer_bp.route("/bank/balance", methods=["POST"])
def check_balance():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not all([email, password]):
        return jsonify({"error": "MISSING_FIELDS"}), 400

    user = mongo.db.users.find_one({"email": email})
    if not user:
        return jsonify({"error": "USER_NOT_FOUND"}), 404

    org_id = user.get("organization_id")
    if not org_id:
        return jsonify({"error": "NO_ORG_ID"}), 400

    account = mongo.db.BANK_ACCOUNT.find_one({
        "organization_id": org_id,
        "password": password
    })

    if not account:
        return jsonify({"error": "BANK_AUTH_FAILED"}), 403

    return jsonify({
        "balance": round(account.get("balance", 0), 2),
        "account_name": account.get("account_name", "N/A"),
        "organization_id": org_id
    })

# 5. Download Thesis (with quota & balance check)
@consumer_bp.route("/thesis/download", methods=["POST"])
def download_thesis():
    data = request.json or {}
    title = data.get("title", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not all([title, email, password]):
        return jsonify({"error": "MISSING_FIELDS"}), 400

    quota = mongo.db.USER_QUOTA.find_one({"user_email": email}) or {}
    used = quota.get("used_today", 0)
    max_daily = quota.get("max_daily", 5)
    if used >= max_daily:
        return jsonify({"error": "QUOTA_EXCEEDED", "used": used, "max": max_daily}), 403

    thesis = mongo.db.THESIS.find_one({"title": {"$regex": title, "$options": "i"}})
    if not thesis:
        return jsonify({"error": "THESIS_NOT_FOUND"}), 404

    thesis_id = thesis.get("_id")
    price = thesis.get("price", 0)

    file_entry = mongo.db.THESIS_FILES.find_one({"title": {"$regex": title, "$options": "i"}})
    if not file_entry or not file_entry.get("pdf_path"):
        return jsonify({"error": "PDF_NOT_AVAILABLE"}), 404
    pdf_path = file_entry["pdf_path"]

    user_doc = mongo.db.users.find_one({"email": email})
    if not user_doc:
        return jsonify({"error": "USER_NOT_FOUND"}), 404
    org_id = user_doc.get("organization_id")

    account = mongo.db.BANK_ACCOUNT.find_one({
        "organization_id": org_id,
        "password": password
    })

    if not account:
        return jsonify({"error": "BANK_AUTH_FAILED"}), 403

    if account.get("balance", 0) < price:
        return jsonify({"error": "INSUFFICIENT_FUNDS"}), 402

    mongo.db.BANK_ACCOUNT.update_one(
        {"_id": account["_id"]},
        {"$inc": {"balance": -price}}
    )

    mongo.db.THESIS_PURCHASE.insert_one({
        "user_email": email,
        "thesis_id": thesis_id,
        "title": title,
        "price": price,
        "time": datetime.now(timezone.utc)
    })

    mongo.db.USER_QUOTA.update_one(
        {"user_email": email},
        {"$inc": {"used_today": 1}, "$set": {"last_used": datetime.now(timezone.utc)}},
        upsert=True
    )

    # return PDF 
    file_entry = mongo.db.THESIS_FILES.find_one({
        "title": {"$regex": title, "$options": "i"}
    })

    if not file_entry or not file_entry.get("pdf_path"):
        return jsonify({"error": "PDF_NOT_AVAILABLE"}), 404

    pdf_path = file_entry["pdf_path"]
    full_path = os.path.abspath(pdf_path)

    print("📄 Downloading file:", full_path)
    if not os.path.exists(full_path):
        return jsonify({"error": "FILE_NOT_FOUND", "path": full_path}), 404

    try:
        return send_file(
            full_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=os.path.basename(full_path)
        )
    except Exception as e:
        print("❌ send_file error:", e)
        return jsonify({"error": "FILE_ERROR", "detail": str(e)}), 500
    


# 3. View available services of an org
@consumer_bp.route("/services/<org>", methods=["GET"])
def get_services_by_org(org):
    email = request.headers.get("X-User-Email", "")
    user_doc = mongo.db.users.find_one({"email": email})
    if not user_doc:
        return jsonify({"error": "AUTH_REQUIRED"}), 401

    requester_org = user_doc.get("organization", "").lower()
    org_doc = mongo.db.org_register_request.find_one({"organization_name": org})
    if not org_doc or "services" not in org_doc:
        return jsonify([])

    print("🔎 user email:", email)
    print("🔎 user org:", requester_org)
    print("🔎 viewing org:", org.lower())
    visible_services = []
    
    # （org_field -> service_config_name）
    service_map = {
        "courseInfo": "course_info",
        "gpaRecord": "student_record",
        "identityCheck": "student_auth",
        "thesisAccess": "thesis_search"
    }

    service_configs = list(mongo.db.SERVICE_CONFIG.find({"organization": org.lower()}))

    for org_field, svc_name in service_map.items():
        svc_meta = org_doc["services"].get(org_field)
        if not svc_meta or not svc_meta.get("enabled"):
            continue

        scope = svc_meta.get("sharing_scope", "")
        same_org = (requester_org == org.lower())

        if scope == "organization_only" and not same_org:
            continue
        if scope == "selective_organizations" and not same_org:
            continue

        config_entry = next((sc for sc in service_configs if sc["service_name"] == svc_name), None)
        if config_entry:
            visible_services.append({
                "service_name": svc_name,
                "config": config_entry["config"]
            })

    return jsonify(visible_services)

@consumer_bp.route("/services/available", methods=["GET"])
def get_available_services():
    email = request.headers.get("X-User-Email", "")
    user_doc = mongo.db.users.find_one({"email": email})
    if not user_doc:
        return jsonify({"error": "AUTH_REQUIRED"}), 401

    requester_org = user_doc.get("organization", "").lower()
    all_orgs = mongo.db.org_register_request.find()

    service_map = {
        "courseInfo": "course_info",
        "gpaRecord": "student_record",
        "identityCheck": "student_auth",
        "thesisAccess": "thesis_search"
    }

    available_services = []

    for org_doc in all_orgs:
        org_name = org_doc.get("organization_name", "").lower()
        services = org_doc.get("services", {})
        for org_field, svc_meta in services.items():
            svc_name = service_map.get(org_field)
            if not svc_name or not svc_meta.get("enabled"):
                continue

            scope = svc_meta.get("sharing_scope")
            if scope == "organization_only" and requester_org != org_name:
                continue
            if scope == "selective_organizations" and requester_org != org_name:
                continue

            config_entry = mongo.db.SERVICE_CONFIG.find_one({
                "organization": org_name,
                "service_name": svc_name
            })

            if config_entry:
                available_services.append({
                    "service_name": svc_name,
                    "organization": org_name,
                    "config": config_entry["config"]
                })

    return jsonify(available_services)


# 4. Call a remote service (identity or record verification)
@consumer_bp.route("/service/query/<org>/<service_name>", methods=["POST"])
def use_service(org, service_name):
    email = get_user_email()
    user_doc = mongo.db.users.find_one({"email": email})
    if not user_doc:
        return jsonify({"error": "AUTH_REQUIRED"}), 401

    user = PrivateDataConsumer(user_doc)
    if not PrivateDataConsumer.is_eligible(user):
        return jsonify({"error": "FORBIDDEN"}), 403

    req_data = request.get_json()
    
    input_data = req_data.get("input") if isinstance(req_data, dict) and "input" in req_data else req_data

    try:
        result = user.access_service(service_name, org.lower(), input_data)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"DISPATCH_FAILED: {str(e)}"}), 500


@consumer_bp.route("/thesis/metadata", methods=["GET"])
def thesis_metadata():
    title = request.args.get("title", "").strip()
    thesis = mongo.db.THESIS.find_one({"title": {"$regex": title, "$options": "i"}})
    if not thesis:
        return jsonify({"message": "NOT_FOUND"})
    return jsonify({
        "thesis_id": thesis.get("_id"),
        "title": thesis.get("title"),
        "abstract": thesis.get("abstract"),
        "price": thesis.get("price", 0)
    })

# policies
@consumer_bp.route("/policies", methods=["GET"])
def list_policies():
    folder = os.path.abspath("src/uploads/policies")
    if not os.path.exists(folder):
        return jsonify([])

    files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    return jsonify(files)

@consumer_bp.route("/policies/download/<filename>", methods=["GET"])
def download_policy(filename):
    folder = os.path.abspath("src/uploads/policies")
    try:
        return send_from_directory(folder, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "FILE_NOT_FOUND"}), 404
