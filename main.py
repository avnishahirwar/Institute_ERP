from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, date
from typing import Optional, List

# ---------------------------------------------------------
# 1. Database Setup (SQLite Permanent Storage)
# ---------------------------------------------------------
DATABASE_URL = "sqlite:///./erp_database.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class UserDB(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, default="SCH101")
    full_name = Column(String)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    role = Column(String) # STUDENT, FACULTY, STAFF
    class_name = Column(String, default="Class 10")
    created_at = Column(DateTime, default=datetime.now)

class FeeRecordDB(Base):
    __tablename__ = "fees"
    id = Column(Integer, primary_key=True, index=True)
    student_email = Column(String)
    amount_paid = Column(Float)
    payment_mode = Column(String) # UPI, Cash, Card
    receipt_no = Column(String)
    paid_at = Column(DateTime, default=datetime.now)

class AttendanceDB(Base):
    __tablename__ = "attendance"
    id = Column(Integer, primary_key=True, index=True)
    student_email = Column(String)
    date = Column(String) # YYYY-MM-DD
    status = Column(String) # PRESENT, ABSENT

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------
# 2. FastAPI Application
# ---------------------------------------------------------
app = FastAPI(
    title="Universal School/College All-in-One ERP",
    version="3.5.0"
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Schemas
class UserCreate(BaseModel):
    tenant_id: str = "SCH101"
    full_name: str
    email: EmailStr
    phone: str
    role: str
    class_name: Optional[str] = "Class 10"

class FeePayment(BaseModel):
    student_email: EmailStr
    amount: float
    payment_mode: str

class AttendanceMark(BaseModel):
    student_email: EmailStr
    date: str
    status: str

# ---------------------------------------------------------
# 3. API Endpoints
# ---------------------------------------------------------

@app.get("/")
def serve_homepage():
    return FileResponse("index.html")

# --- Dashboard Stats API ---
@app.get("/api/v3/dashboard/stats")
def get_stats(db: Session = Depends(get_db)):
    total_students = db.query(UserDB).filter(UserDB.role == "STUDENT").count()
    total_faculty = db.query(UserDB).filter(UserDB.role == "FACULTY").count()
    
    # Total Fees Collected
    total_fees = db.query(func.sum(FeeRecordDB.amount_paid)).scalar() or 0.0
    
    # Today's Attendance
    today_str = datetime.now().strftime("%Y-%m-%d")
    p_today = db.query(AttendanceDB).filter(AttendanceDB.date == today_str, AttendanceDB.status == "PRESENT").count()
    a_today = db.query(AttendanceDB).filter(AttendanceDB.date == today_str, AttendanceDB.status == "ABSENT").count()

    return {
        "total_students": total_students,
        "total_faculty": total_faculty,
        "total_fees": total_fees,
        "today_present": p_today,
        "today_absent": a_today
    }

# --- Users & Admissions API ---
@app.post("/api/v3/users/register", status_code=201)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(UserDB).filter(UserDB.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="ईमेल पहले से रजिस्टर्ड है!")
    
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
    return {"status": "SUCCESS", "data": new_user}

@app.get("/api/v3/users/list")
def list_users(db: Session = Depends(get_db)):
    users = db.query(UserDB).order_by(UserDB.id.desc()).all()
    return {"total": len(users), "users": users}

# --- Attendance API ---
@app.post("/api/v3/attendance/mark")
def mark_attendance(att: AttendanceMark, db: Session = Depends(get_db)):
    record = AttendanceDB(
        student_email=att.student_email,
        date=att.date,
        status=att.status.upper()
    )
    db.add(record)
    db.commit()
    return {"status": "SUCCESS", "message": f"{att.student_email} की अटेंडेंस सेव हो गई!"}

@app.get("/api/v3/attendance/report")
def attendance_report(db: Session = Depends(get_db)):
    records = db.query(AttendanceDB).order_by(AttendanceDB.id.desc()).all()
    return {"records": records}

# --- Fees Management API ---
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
    return {"status": "SUCCESS", "receipt": receipt, "amount": fee.amount}

@app.get("/api/v3/fees/history")
def fee_history(db: Session = Depends(get_db)):
    history = db.query(FeeRecordDB).order_by(FeeRecordDB.id.desc()).all()
    return {"history": history}