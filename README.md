# SafeSpeak 🎙️🛡️

> **An AI-Secured, Female-Only Peer Voice Communication Platform**  
> SafeSpeak combines real-time WebRTC audio calling with a multi-layered biometric security pipeline to provide a verified, private, and safe environment for female English learners to practice speaking.

---

## 🌟 Key Capabilities

* **Biometric Identity Verification:** Mandatory pre-onboarding facial and voice verification ensuring community authenticity.
* **Deep Anti-Spoofing:** Graph-attention neural networks (AASIST-L) detecting synthetic AI voices, text-to-speech clones, and replay attacks.
* **Dual-Model Acoustic Gender Analysis:** Independent evaluation using **Wav2Vec2** Transformer and **ECAPA-TDNN** deep speaker embeddings.
* **Atomic Real-Time Matchmaking:** High-throughput matchmaking engine with database row locking (`select_for_update`) to eliminate call collision race conditions.
* **Sub-Second Audio Transmission:** Powered by Agora RTC's software-defined real-time network with token-authenticated channel encryption.
* **Asynchronous Push Signaling:** High-priority Firebase Cloud Messaging (FCM) wakeup notifications for call ringing even when the client is backgrounded.

---

## 🏗️ System Architecture

SafeSpeak utilizes a decoupled two-service microservice pattern deployed on **Microsoft Azure App Service**:

```
[ Flutter Mobile Client ]
           │
           │ HTTPS / REST (Port 8000)
           ▼
┌─────────────────────────────────────────────────────────────┐
│  Django REST Framework API Gateway                          │
│  - Authentication & JWT Issuance (SimpleJWT)                │
│  - Real-Time Heartbeat & Presence Locking (Azure SQL Server)│
│  - Agora RTC Cryptographic Token Builder                    │
│  - Firebase Cloud Messaging (FCM) Push Service              │
└──────────────┬──────────────────────────────────────────────┘
               │
               │ Internal Gateway Proxy (HTTP 127.0.0.1:8001)
               ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI AI Microservice                                    │
│  ├── Face Engine: RetinaFace Landmark Detection + DeepFace  │
│  └── Voice Engine (5-Gate Sequential AI Pipeline):          │
│       ├── Gate 1: Librosa Signal Quality & Silence Filter   │
│       ├── Gate 2: Wav2Vec2 Acoustic Gender Recognition      │
│       ├── Gate 3: ECAPA-TDNN Vocal Tract Gender Validation  │
│       ├── Gate 4: AASIST-L Anti-Spoof AI Voice Detection    │
│       └── Gate 5: Dual-Model Conservative Decision Policy   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

| Domain | Technologies & Libraries |
| :--- | :--- |
| **API Gateway** | Python 3.11, Django 5.x, Django REST Framework, SimpleJWT |
| **AI Microservice** | FastAPI, Uvicorn, PyTorch, TensorFlow, Transformers (Hugging Face) |
| **Computer Vision** | DeepFace, RetinaFace, OpenCV Headless, Pillow |
| **Audio Intelligence** | Librosa, SoundFile, AASIST-L (Graph Attention), ECAPA-TDNN, Wav2Vec2 |
| **Signaling & RTC** | Agora RTC Engine, Firebase Admin SDK (Cloud Messaging) |
| **Data & Cloud** | Azure SQL Server (ODBC Driver 17), Microsoft Azure App Service |



## ⚡ Quickstart & Local Setup

### 1. Prerequisites
* Python 3.10+
* Git
* Microsoft ODBC Driver 17 for SQL Server (or SQLite for local mock)

### 2. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/humayoon8180/SafeSpeakH.git
cd SafeSpeakH

python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the project root:
```env
SECRET_KEY=your-django-secret-key
DEBUG=True

# Azure SQL / SQL Server Configuration
DB_NAME=safespeak_db
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_server.database.windows.net

# Agora Real-Time RTC Credentials
AGORA_APP_ID=your_agora_app_id
AGORA_APP_CERTIFICATE=your_agora_app_certificate

# Firebase Configuration
FIREBASE_CREDENTIALS_JSON={"type": "service_account", ...}
```

### 4. Database Migrations
```bash
cd backend
python manage.py makemigrations
python manage.py migrate
```

### 5. Start Application Services
In terminal 1 (FastAPI AI Microservice):
```bash
cd fastapi_app
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In terminal 2 (Django REST API Gateway):
```bash
cd backend
python manage.py runserver 8000
```

---

## 🔒 Security & Privacy Notice
* **Environment Isolation:** Zero private keys, connection strings, or cloud tokens are tracked in source control.
* **Defensive Gateway:** The AI microservice binds strictly to `127.0.0.1` and is never exposed to the public internet; all requests are authenticated and reverse-proxied through the Django API gateway.
* **Audio Ephemerality:** Audio clips processed during verification are held in memory buffers for inference and discarded immediately; user call conversations are fully encrypted point-to-point via Agora RTC.

---

## 📄 License
This project is developed as a Final Year Project (FYP). All rights reserved.
