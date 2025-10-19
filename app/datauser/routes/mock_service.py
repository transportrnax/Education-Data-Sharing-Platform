from flask import Blueprint, request, jsonify, send_file
from pymongo import MongoClient
from flask import Blueprint, request, jsonify
import os

mock_bp = Blueprint("mock", __name__, url_prefix="/mock")

client = MongoClient("mongodb://localhost:27017/")
db = client["EDBA"]

@mock_bp.route("/thesis/search", methods=["POST"])
def search_thesis():
    try:
        data = request.json
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "MISSING_TITLE"}), 400

        thesis = db["THESIS"].find_one({"title": {"$regex": title, "$options": "i"}})
        if not thesis:
            return jsonify({"message": "PDF not found for given title."})

        return jsonify({
            "title": thesis["title"],
            "abstract": thesis["abstract"]
        })
    except Exception as e:
        return jsonify({"error": "INTERNAL_ERROR", "detail": str(e)}), 500


# 1️⃣ Identity Authenticate
@mock_bp.route("/student/authenticate", methods=["POST"])
def student_authenticate():
    data = request.get_json()
    results = []

    if isinstance(data, list):
        for item in data:
            name = item.get("name", "").strip()
            student_id = item.get("id", "").strip()
            record = db["STUDENT_AUTH"].find_one({"name": name, "id": student_id})
            results.append({
                "name": name,
                "id": student_id,
                "status": record.get("status", "verified") if record else "invalid"
            })
        return jsonify(results)

    # 单个对象处理
    name = data.get("name", "").strip()
    student_id = data.get("id", "").strip()
    record = db["STUDENT_AUTH"].find_one({"name": name, "id": student_id})
    return jsonify({
        "name": name,
        "id": student_id,
        "status": record.get("status", "verified") if record else "invalid"
    })

# 2️⃣ Student Record
@mock_bp.route("/student/record", methods=["POST"])
def student_record():
    data = request.get_json()
    results = []

    if isinstance(data, list):
        for item in data:
            name = item.get("name", "").strip()
            student_id = item.get("id", "").strip()
            record = db["STUDENT_RECORD"].find_one({"name": name, "id": student_id})
            if record:
                results.append({
                    "name": record["name"],
                    "id": student_id,
                    "enroll_year": record["enroll_year"],
                    "graduation_year": record["graduation_year"],
                    "gpa": record["gpa"]
                })
            else:
                results.append({
                    "name": name,
                    "id": student_id,
                    "error": "NOT_FOUND"
                })
        return jsonify(results)

    # 单个对象处理
    name = data.get("name", "").strip()
    student_id = data.get("id", "").strip()
    record = db["STUDENT_RECORD"].find_one({"name": name, "id": student_id})
    if record:
        return jsonify({
            "name": record["name"],
            "id": student_id,
            "enroll_year": record["enroll_year"],
            "graduation_year": record["graduation_year"],
            "gpa": record["gpa"]
        })
    return jsonify({"error": "NOT_FOUND"}), 404


# ✅ 4. Thesis Title → PDF file
@mock_bp.route("/thesis/pdf", methods=["POST"])
def thesis_pdf():
    data = request.get_json()
    title = data.get("title", "").strip().lower()

    match = db["THESIS_FILES"].find_one({
        "title": {"$regex": title, "$options": "i"}
    })

    if not match:
        return jsonify({"message": "PDF not found for given title."}), 404

    relative_path = match.get("pdf_path")
    if not relative_path:
        return jsonify({"error": "No pdf_path provided"}), 400

    full_path = os.path.join(os.getcwd(), relative_path)

    try:
        return send_file(
            full_path,
            mimetype='application/pdf',
            as_attachment=True,  # ✅ 强制下载
            download_name=f"{title.replace(' ', '_')}.pdf"
        )
    except Exception as e:
        return jsonify({"error": "Failed to read file", "detail": str(e)}), 500


# ✅ 5. Bank Authenticate
@mock_bp.route("/bank/auth", methods=["POST"])
def bank_auth():
    data = request.get_json()
    if data.get("account_number") == "123456" and data.get("password") == "pass":
        return jsonify({"status": "success"})
    return jsonify({"status": "fail"})

# ✅ 6. Bank Transfer
@mock_bp.route("/bank/transfer", methods=["POST"])
def bank_transfer():
    data = request.get_json()
    if data.get("from_account") and data.get("to_account") and data.get("amount", 0) > 0:
        return jsonify({"status": "success"})
    return jsonify({
        "status": "fail",
        "reason": "Invalid transfer request"
    })

@mock_bp.route("/bank/balance", methods=["POST"])
def bank_balance():
    data = request.get_json()
    account = db["BANK_ACCOUNTS"].find_one({
        "bank": data.get("bank"),
        "account_number": data.get("account_number"),
        "password": data.get("password")
    })
    if not account:
        return jsonify({"status": "fail", "reason": "auth_failed"}), 403
    return jsonify({
        "status": "success",
        "balance": account.get("balance", 0.0)
    })

@mock_bp.route("/bank/withdraw", methods=["POST"])
def bank_withdraw():
    data = request.get_json()
    amount = float(data.get("amount", 0))
    account = db["BANK_ACCOUNTS"].find_one({
        "bank": data.get("bank"),
        "account_number": data.get("account_number"),
        "password": data.get("password")
    })

    if not account or account["balance"] < amount:
        return jsonify({"status": "fail", "reason": "insufficient_funds"}), 403

    new_balance = account["balance"] - amount
    db["BANK_ACCOUNTS"].update_one(
        {"_id": account["_id"]},
        {"$set": {"balance": new_balance}}
    )
    return jsonify({"status": "success", "new_balance": new_balance})

@mock_bp.route("/quota/check", methods=["POST"])
def quota_check():
    email = request.json.get("email")
    record = db["USER_QUOTA"].find_one({"user_email": email})
    if not record:
        return jsonify({"status": "ok", "remaining": 10})

    used = record.get("used_today", 0)
    max_allowed = record.get("max_daily", 5)
    if used >= max_allowed:
        return jsonify({"status": "fail", "reason": "quota_exceeded"})

    return jsonify({"status": "ok", "remaining": max_allowed - used})

@mock_bp.route("/course/info", methods=["POST"])
def mock_course_info():
    data = request.get_json()
    title = data.get("title", "").strip()

    if not title:
        return jsonify({"error": "TITLE_REQUIRED"}), 400

    course = db["COURSE_INFO"].find_one({
        "title": {"$regex": title, "$options": "i"}
    })

    if not course:
        return jsonify({"error": "COURSE_NOT_FOUND"}), 404

    return jsonify({
        "title": course["title"],
        "units": course["units"],
        "description": course["description"]
    })

