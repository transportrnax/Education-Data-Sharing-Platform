# ✅ Full Updated Version of datauser_routes_public.py
from flask import Blueprint, request, jsonify, send_file
from ..models.public_consumer import PublicDataConsumer
from ...extensions import mongo
from datetime import datetime, timezone
import os
from flask import send_from_directory

public_bp = Blueprint("public", __name__, url_prefix="/api/public")

# 🔍 1. Search or List Public Courses
@public_bp.route("/courses", methods=["GET"])
def search_courses():
    keyword = request.args.get("keyword", "").strip()
    consumer = PublicDataConsumer({})
    if keyword:
        results = consumer.search_courses(keyword)
    else:
        results = consumer.list_all_courses()
    return jsonify(results)

# 📘 1b. List All Courses (no keyword)
@public_bp.route("/courses/all", methods=["GET"])
def list_all_courses():
    courses = list(mongo.db.COURSE_INFO.find({}, {"_id": 0}))
    return jsonify(courses)

# 📗 1c. List All Theses
@public_bp.route("/theses", methods=["GET"])
def list_theses():
    theses = list(mongo.db.THESIS.find({}, {"_id": 0, "pdf_path": 0}))
    return jsonify(theses)

# 📄 2. View Thesis Metadata
@public_bp.route("/thesis/metadata", methods=["GET"])
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

# 📊 3. View Quota Info
@public_bp.route("/quota", methods=["GET"])
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

# 💰 4. Check Account Balance
@public_bp.route("/bank/balance", methods=["POST"])
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


# 💾 5. Download Thesis (with quota & balance check)
@public_bp.route("/thesis/download", methods=["POST"])
def download_thesis():
    data = request.json or {}
    title = data.get("title", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not all([title, email, password]):
        return jsonify({"error": "MISSING_FIELDS"}), 400

    # ✅ 1. 配额检查
    quota = mongo.db.USER_QUOTA.find_one({"user_email": email}) or {}
    used = quota.get("used_today", 0)
    max_daily = quota.get("max_daily", 5)
    if used >= max_daily:
        return jsonify({"error": "QUOTA_EXCEEDED", "used": used, "max": max_daily}), 403

    # ✅ 2. 查找论文
    thesis = mongo.db.THESIS.find_one({"title": {"$regex": title, "$options": "i"}})
    if not thesis:
        return jsonify({"error": "THESIS_NOT_FOUND"}), 404

    thesis_id = thesis.get("_id")
    price = thesis.get("price", 0)

    file_entry = mongo.db.THESIS_FILES.find_one({"title": {"$regex": title, "$options": "i"}})
    if not file_entry or not file_entry.get("pdf_path"):
        return jsonify({"error": "PDF_NOT_AVAILABLE"}), 404
    pdf_path = file_entry["pdf_path"]

    # ✅ 3. 查找用户所属组织 ID
    user_doc = mongo.db.users.find_one({"email": email})
    if not user_doc:
        return jsonify({"error": "USER_NOT_FOUND"}), 404
    org_id = user_doc.get("organization_id")

    # ✅ 4. 用组织 ID 查找银行账户
    account = mongo.db.BANK_ACCOUNT.find_one({
        "organization_id": org_id,
        "password": password
    })

    if not account:
        return jsonify({"error": "BANK_AUTH_FAILED"}), 403

    if account.get("balance", 0) < price:
        return jsonify({"error": "INSUFFICIENT_FUNDS"}), 402

    # ✅ 5. 扣款
    mongo.db.BANK_ACCOUNT.update_one(
        {"_id": account["_id"]},
        {"$inc": {"balance": -price}}
    )

    # ✅ 6. 记录购买
    mongo.db.THESIS_PURCHASE.insert_one({
        "user_email": email,
        "thesis_id": thesis_id,
        "title": title,
        "price": price,
        "time": datetime.now(timezone.utc)
    })

    # ✅ 7. 更新配额
    mongo.db.USER_QUOTA.update_one(
        {"user_email": email},
        {"$inc": {"used_today": 1}, "$set": {"last_used": datetime.now(timezone.utc)}},
        upsert=True
    )

    # ✅ 8. 返回 PDF 文件
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

# policies
@public_bp.route("/policies", methods=["GET"])
def list_policies():
    folder = os.path.abspath("src/uploads/policies")
    if not os.path.exists(folder):
        return jsonify([])

    files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    return jsonify(files)


@public_bp.route("/policies/download/<filename>", methods=["GET"])
def download_policy(filename):
    folder = os.path.abspath("src/uploads/policies")
    try:
        return send_from_directory(folder, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "FILE_NOT_FOUND"}), 404
