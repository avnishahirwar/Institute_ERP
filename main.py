from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from typing import Optional, List

# ---------------------------------------------------------
# 1. Database Setup (Permanent Live Save using SQLite/Postgres)
# ---------------------------------------------------------
DATABASE_URL = "sqlite:///./erp_database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Tables
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True)
    full_name = Column(String)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    role = Column(String) # STUDENT, FACULTY, STAFF, PARENT
    class_name = Column(String)
    created_at = Column(DateTime, default=datetime.now)

class FeeRecordDB(Base):
    __tablename__ = "fees"
    id = Column(Integer, primary_key=True, index=True)
    student_email = Column(String)
    amount_paid = Column(Float)
    payment_mode = Column(String) # UPI, Card, Cash
    receipt_no = Column(String)
    paid_at = Column(DateTime, default=datetime.now)

class AttendanceDB(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    student_email = Column(String)
    date = Column(String)
    status = Column(String) # PRESENT, ABSENT

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------
# 2. FastAPI Application Setup
# ---------------------------------------------------------
app = FastAPI(
    title="Universal School/College/Coaching All-in-One ERP",
    version="3.0.0",
    description="Enterprise Live ERP Cloud Backend with Permanent Storage"
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic Schemas
class UserCreate(BaseModel):
    tenant_id: str = "INSTITUTE_01"
    full_name: str
    email: EmailStr
    phone: str
    role: str # STUDENT, FACULTY, STAFF
    class_name: str

class FeePayment(BaseModel):
    student_email: EmailStr
    amount: float
    payment_mode: str

class AttendanceMark(BaseModel):
    student_email: EmailStr
    date: str
    status: str

# ---------------------------------------------------------
# 3. All ERP Core API Routes
# ---------------------------------------------------------

@app.get("/")
def serve_homepage():
    return FileResponse("index.html")

# --- 1. User & Student Admission Route ---
@app.post("/api/v3/users/register", status_code=201)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered!")
    
    new_user = UserDB(
        tenant_id=user.tenant_id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role.upper(),
        class_name=user.class_name
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"status": "SUCCESS", "message": "User registered permanently!", "data": new_user}

@app.get("/api/v3/users/list")
def list_users(db: Session = Depends(get_db)):
    users = db.query(UserDB).all()
    return {"total": len(users), "users": users}

# --- 2. Fees & Accounts Management ---
@app.post("/api/v3/fees/pay")
def pay_fees(fee: FeePayment, db: Session = Depends(get_db)):
    receipt = f"REC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    new_fee = FeeRecordDB(
        student_email=fee.student_email,
        amount_paid=fee.amount,
        payment_mode=fee.payment_mode,
        receipt_no=receipt
    )
    db.add(new_fee)
    db.commit()
    return {"status": "PAID", "receipt_number": receipt, "amount": fee.amount}

@app.get("/api/v3/fees/history")
def fee_history(db: Session = Depends(get_db)):
    return db.query(FeeRecordDB).all()

# --- 3. Attendance & Auto-Alert Engine ---
@app.post("/api/v3/attendance/mark")
def mark_attendance(att: AttendanceMark, db: Session = Depends(get_db)):
    record = AttendanceDB(
        student_email=att.student_email,
        date=att.date,
        status=att.status.upper()
    )
    db.add(record)
    db.commit()
    
    alert_message = None
    if att.status.upper() == "ABSENT":
        alert_message = f"ALERT: Student {att.student_email} was marked ABSENT on {att.date}."
    
    return {"status": "RECORDED", "alert": alert_message}

@app.get("/api/v3/attendance/report")
def attendance_report(db: Session = Depends(get_db)):
    records = db.query(AttendanceDB).all()
    return {"total_entries": len(records), "records": records}