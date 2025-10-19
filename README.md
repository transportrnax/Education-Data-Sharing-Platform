# Education-Data-Sharing-Platform
Enables secure, role-based data sharing between universities, including student verification, course information, thesis access, and payment services.  Built with Flask + MongoDB, featuring a modular design for private/public data providers and consumers.

# 🎓 Education Data Bay Area (E-DBA)

A lightweight educational data-sharing platform inspired by the International Data Space (IDS) architecture.

> Designed and implemented as part of *Software Engineering* and *Advanced Software Development Workshop* courses at UIC.

---

## 🚀 Features

### 🧩 Core Modules
- **Role-based Access Control**
  - Admins (T-Admin, E-Admin, Senior E-Admin)
  - Organization Conveners (O-Convener)
  - Data Providers / Data Consumers (Levels 1–3)
- **Service Configuration**
  - Course Information (Public)
  - Student Authentication (Private)
  - Student Record Access (Private)
  - Thesis Access (Private)
- **Payment Integration**
  - Bank Account & Transfer API (Mock)
- **Policies**
  - Upload and manage PDF-based policies
  - View and download organization policies

---

## 🧱 Tech Stack

| Layer | Technology |
|-------|-------------|
| Backend | Flask (Python) |
| Database | MongoDB |
| Frontend | HTML, JavaScript, Bootstrap-styled |
| Authentication | Flask-Login / Mock Email OTP |
| File Handling | `send_from_directory` (for policy PDFs) |

---

## 🗂 Directory Structure

