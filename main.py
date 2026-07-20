import os
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, declarative_base
import jwt
import uvicorn

# ---------------------------------------------------------
# 1. Database Setup (SQLite)
# ---------------------------------------------------------
DATABASE_URL = "sqlite:///./erp_database.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

SECRET_KEY = "SUPER_SECRET_ENTERPRISE_KEY_CAMPUS_ERP"
ALGORITHM = "HS256"

# --- Database Models ---
class TenantDB(Base):
    __tablename__ = "tenants"
    id = Column(String, primary_key=True, index=True)
    institution_name = Column(String, nullable=False)
    subscription_plan = Column(String, default="BASIC")
    payment_status = Column(String, default="UNPAID")
    subscription_end_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    phone = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class FeeRecordDB(Base):
    __tablename__ = "fee_records"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"))
    student_email = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    receipt_no = Column(String, unique=True)
    payment_mode = Column(String)
    status = Column(String, default="PAID")
    paid_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Auto-Seed Initial Data (for Testing)
def seed_initial_data():
    db = SessionLocal()
    try:
        tenant = db.query(TenantDB).filter(TenantDB.id == "SCH101").first()
        if not tenant:
            tenant = TenantDB(
                id="SCH101",
                institution_name="Universal High School",
                subscription_plan="ENTERPRISE_AI",
                payment_status="ACTIVE",
                subscription_end_date=datetime.utcnow() + timedelta(days=365)
            )
            db.add(tenant)
            db.commit()

        user = db.query(UserDB).filter(UserDB.email == "principal@sch101.com").first()
        if not user:
            user = UserDB(
                tenant_id="SCH101",
                full_name="Dr. Rajesh Sharma (Principal)",
                email="principal@sch101.com",
                hashed_password="admin123",
                role="PRINCIPAL",
                phone="9876543210"
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

seed_initial_data()

# ---------------------------------------------------------
# 2. FastAPI Engine & Security
# ---------------------------------------------------------
app = FastAPI(title="Enterprise Campus SaaS Platform", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_jwt_token(token: str = Header(...), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        tenant_id: str = payload.get("tenant_id")
        role: str = payload.get("role")
        
        user = db.query(UserDB).filter(UserDB.email == email, UserDB.tenant_id == tenant_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid Session User")
        return {"user": user, "tenant_id": tenant_id, "role": role}
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired or invalid token")

def check_paywall_status(current_user: dict = Depends(verify_jwt_token), db: Session = Depends(get_db)):
    if current_user["role"] == "SUPER_ADMIN":
        return current_user

    tenant = db.query(TenantDB).filter(TenantDB.id == current_user["tenant_id"]).first()
    if not tenant or tenant.payment_status != "ACTIVE":
        raise HTTPException(
            status_code=402, 
            detail="⚠️ Subscription Inactive! Payment required to access dashboard."
        )
    return current_user

# --- Request Schemas ---
class SubscriptionPaySchema(BaseModel):
    tenant_id: str
    plan_name: str
    amount_paid: float

class LoginSchema(BaseModel):
    email: str
    password: str

# ---------------------------------------------------------
# 3. API Routes
# ---------------------------------------------------------

@app.get("/")
def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "index.html file not found in directory!"}

@app.post("/api/v5/auth/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == data.email).first()
    if not user or user.hashed_password != data.password:
        raise HTTPException(status_code=400, detail="Invalid Credentials")
    
    tenant = db.query(TenantDB).filter(TenantDB.id == user.tenant_id).first()
    
    token_data = {
        "sub": user.email,
        "tenant_id": user.tenant_id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "token": token,
        "role": user.role,
        "full_name": user.full_name,
        "tenant_id": user.tenant_id,
        "institution_name": tenant.institution_name if tenant else "Super Admin",
        "payment_status": tenant.payment_status if tenant else "ACTIVE"
    }

@app.post("/api/v5/saas/subscribe-pay")
def activate_subscription(pay: SubscriptionPaySchema, db: Session = Depends(get_db)):
    tenant = db.query(TenantDB).filter(TenantDB.id == pay.tenant_id).first()
    if not tenant:
        tenant = TenantDB(
            id=pay.tenant_id,
            institution_name=f"Campus {pay.tenant_id}",
            subscription_plan=pay.plan_name,
            payment_status="ACTIVE",
            subscription_end_date=datetime.utcnow() + timedelta(days=365)
        )
        db.add(tenant)
    else:
        tenant.payment_status = "ACTIVE"
        tenant.subscription_plan = pay.plan_name
        tenant.subscription_end_date = datetime.utcnow() + timedelta(days=365)
    
    db.commit()
    return {"status": "SUCCESS", "message": f"Tenant {pay.tenant_id} Activated Successfully!"}

@app.get("/api/v5/dashboard/principal")
def principal_dashboard(user_info: dict = Depends(check_paywall_status), db: Session = Depends(get_db)):
    tenant_id = user_info["tenant_id"]
    students = db.query(UserDB).filter(UserDB.tenant_id == tenant_id, UserDB.role == "STUDENT").count()
    teachers = db.query(UserDB).filter(UserDB.tenant_id == tenant_id, UserDB.role == "TEACHER").count()
    return {"students_count": students, "teachers_count": teachers, "ai_health_score": "98.5% Active"}

@app.get("/api/v5/dashboard/student")
def student_dashboard(user_info: dict = Depends(check_paywall_status)):
    return {
        "attendance": "94%",
        "assignments_pending": 2,
        "ai_tutor_recommendation": "Focus on Quantum Physics Chapter 4"
    }

@app.get("/api/v5/dashboard/accountant")
def accountant_dashboard(user_info: dict = Depends(check_paywall_status), db: Session = Depends(get_db)):
    tenant_id = user_info["tenant_id"]
    records = db.query(FeeRecordDB).filter(FeeRecordDB.tenant_id == tenant_id).all()
    total_collected = sum([r.amount for r in records])
    return {"total_collection": total_collected, "records": records}

# ---------------------------------------------------------
# 4. Auto Server Launcher
# ---------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting Enterprise ERP Server...")
    uvicorn.run(app, host="127.0.0.1", port=8000)