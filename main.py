"""
DropSync FastAPI Backend
"""
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from datetime import datetime, timedelta
import jwt
import os
from typing import List, Optional

from models import Base, User, EbayAccount, SupplierFeed, SyncJob, PlanType, SyncStatus
from sync_engine import EbaySyncEngine

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dropsync.db")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# FastAPI app
app = FastAPI(title="DropSync API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# ============================================================================
# Pydantic Models
# ============================================================================

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EbayAccountCreate(BaseModel):
    store_name: str
    app_id: str
    dev_id: str
    cert_id: str
    user_token: str
    sync_frequency: str = "daily"
    sync_time: str = "06:00"


class SupplierFeedCreate(BaseModel):
    name: str
    feed_url: str
    feed_type: str  # azuregreen, diecast, custom
    sku_column: Optional[str] = "NUMBER"
    quantity_column: Optional[str] = "UNITS"


class TriggerSyncRequest(BaseModel):
    account_id: int
    feed_id: int


# ============================================================================
# Dependencies
# ============================================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user


# ============================================================================
# Auth Endpoints
# ============================================================================

@app.post("/api/auth/register", response_model=Token)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    # Check if user exists
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user = User(
        email=user_data.email,
        password_hash=pwd_context.hash(user_data.password),
        full_name=user_data.full_name,
        plan=PlanType.FREE_TRIAL,
        max_accounts=1,
        max_listings=10000,
        max_feeds=2,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create token
    token = create_access_token({"user_id": user.id})
    
    return {"access_token": token}


@app.post("/api/auth/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user or not pwd_context.verify(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    token = create_access_token({"user_id": user.id})
    
    return {"access_token": token}


@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "plan": current_user.plan.value,
        "max_accounts": current_user.max_accounts,
        "max_listings": current_user.max_listings,
        "max_feeds": current_user.max_feeds,
        "created_at": current_user.created_at,
    }


# ============================================================================
# eBay Account Endpoints
# ============================================================================

@app.get("/api/accounts")
def list_accounts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    accounts = db.query(EbayAccount).filter(
        EbayAccount.user_id == current_user.id,
        EbayAccount.is_active == True
    ).all()
    
    return [{
        "id": acc.id,
        "store_name": acc.store_name,
        "sync_enabled": acc.sync_enabled,
        "sync_frequency": acc.sync_frequency,
        "last_sync_at": acc.last_sync_at,
        "created_at": acc.created_at,
    } for acc in accounts]


@app.post("/api/accounts")
def create_account(
    account_data: EbayAccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check limits
    existing_count = db.query(EbayAccount).filter(
        EbayAccount.user_id == current_user.id,
        EbayAccount.is_active == True
    ).count()
    
    if existing_count >= current_user.max_accounts:
        raise HTTPException(
            status_code=403,
            detail=f"Account limit reached ({current_user.max_accounts}). Upgrade your plan."
        )
    
    # Create account
    account = EbayAccount(
        user_id=current_user.id,
        store_name=account_data.store_name,
        app_id=account_data.app_id,
        dev_id=account_data.dev_id,
        cert_id=account_data.cert_id,
        access_token=account_data.user_token,
        sync_frequency=account_data.sync_frequency,
        sync_time=account_data.sync_time,
    )
    
    db.add(account)
    db.commit()
    db.refresh(account)
    
    return {"id": account.id, "message": "eBay account connected successfully"}


@app.delete("/api/accounts/{account_id}")
def delete_account(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    account = db.query(EbayAccount).filter(
        EbayAccount.id == account_id,
        EbayAccount.user_id == current_user.id
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    account.is_active = False
    db.commit()
    
    return {"message": "Account deleted"}


# ============================================================================
# Supplier Feed Endpoints
# ============================================================================

@app.get("/api/feeds")
def list_feeds(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    feeds = db.query(SupplierFeed).filter(
        SupplierFeed.user_id == current_user.id,
        SupplierFeed.is_active == True
    ).all()
    
    return [{
        "id": feed.id,
        "name": feed.name,
        "feed_type": feed.feed_type,
        "feed_url": feed.feed_url,
        "total_skus": feed.total_skus,
        "last_fetched_at": feed.last_fetched_at,
        "created_at": feed.created_at,
    } for feed in feeds]


@app.post("/api/feeds")
def create_feed(
    feed_data: SupplierFeedCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check limits
    existing_count = db.query(SupplierFeed).filter(
        SupplierFeed.user_id == current_user.id,
        SupplierFeed.is_active == True
    ).count()
    
    if existing_count >= current_user.max_feeds:
        raise HTTPException(
            status_code=403,
            detail=f"Feed limit reached ({current_user.max_feeds}). Upgrade your plan."
        )
    
    # Create feed
    feed = SupplierFeed(
        user_id=current_user.id,
        name=feed_data.name,
        feed_url=feed_data.feed_url,
        feed_type=feed_data.feed_type,
        sku_column=feed_data.sku_column,
        quantity_column=feed_data.quantity_column,
    )
    
    db.add(feed)
    db.commit()
    db.refresh(feed)
    
    return {"id": feed.id, "message": "Supplier feed added successfully"}


@app.delete("/api/feeds/{feed_id}")
def delete_feed(
    feed_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    feed = db.query(SupplierFeed).filter(
        SupplierFeed.id == feed_id,
        SupplierFeed.user_id == current_user.id
    ).first()
    
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    
    feed.is_active = False
    db.commit()
    
    return {"message": "Feed deleted"}


# ============================================================================
# Sync Endpoints
# ============================================================================

def run_sync_job(account_id: int, feed_id: int, db: Session):
    """Background task to run sync"""
    # Get account and feed
    account = db.query(EbayAccount).filter(EbayAccount.id == account_id).first()
    feed = db.query(SupplierFeed).filter(SupplierFeed.id == feed_id).first()
    
    if not account or not feed:
        return
    
    # Create sync job
    job = SyncJob(
        account_id=account_id,
        status=SyncStatus.RUNNING,
        triggered_by="manual",
        started_at=datetime.utcnow()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    try:
        # Run sync
        engine = EbaySyncEngine({
            "app_id": account.app_id,
            "dev_id": account.dev_id,
            "cert_id": account.cert_id,
            "user_token": account.access_token,
            "api_url": "https://api.ebay.com/ws/api.dll",
            "site_id": "0",
        })
        
        column_mapping = {
            "sku_column": feed.sku_column,
            "quantity_column": feed.quantity_column,
        }
        
        result = engine.run_sync(feed.feed_url, feed.feed_type, column_mapping)
        
        # Update job
        job.status = SyncStatus.COMPLETED if result["status"] == "completed" else SyncStatus.FAILED
        job.total_listings_checked = result["total_listings_checked"]
        job.items_updated = result["items_updated"]
        job.items_failed = result["items_failed"]
        job.items_out_of_stock = result["items_out_of_stock"]
        job.completed_at = datetime.utcnow()
        job.duration_seconds = result["duration_seconds"]
        job.error_message = result.get("error_message")
        
        # Update account
        account.last_sync_at = datetime.utcnow()
        
        db.commit()
        
    except Exception as e:
        job.status = SyncStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()


@app.post("/api/sync/trigger")
def trigger_sync(
    sync_request: TriggerSyncRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify ownership
    account = db.query(EbayAccount).filter(
        EbayAccount.id == sync_request.account_id,
        EbayAccount.user_id == current_user.id
    ).first()
    
    feed = db.query(SupplierFeed).filter(
        SupplierFeed.id == sync_request.feed_id,
        SupplierFeed.user_id == current_user.id
    ).first()
    
    if not account or not feed:
        raise HTTPException(status_code=404, detail="Account or feed not found")
    
    # Add to background tasks
    background_tasks.add_task(run_sync_job, sync_request.account_id, sync_request.feed_id, db)
    
    return {"message": "Sync triggered successfully", "status": "running"}


@app.get("/api/sync/jobs")
def list_sync_jobs(
    account_id: Optional[int] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(SyncJob).join(EbayAccount).filter(
        EbayAccount.user_id == current_user.id
    )
    
    if account_id:
        query = query.filter(SyncJob.account_id == account_id)
    
    jobs = query.order_by(SyncJob.created_at.desc()).limit(limit).all()
    
    return [{
        "id": job.id,
        "account_id": job.account_id,
        "status": job.status.value,
        "triggered_by": job.triggered_by,
        "total_listings_checked": job.total_listings_checked,
        "items_updated": job.items_updated,
        "items_failed": job.items_failed,
        "items_out_of_stock": job.items_out_of_stock,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "duration_seconds": job.duration_seconds,
        "error_message": job.error_message,
    } for job in jobs]


@app.get("/api/sync/jobs/{job_id}")
def get_sync_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    job = db.query(SyncJob).join(EbayAccount).filter(
        SyncJob.id == job_id,
        EbayAccount.user_id == current_user.id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "id": job.id,
        "account_id": job.account_id,
        "status": job.status.value,
        "triggered_by": job.triggered_by,
        "total_listings_checked": job.total_listings_checked,
        "items_updated": job.items_updated,
        "items_failed": job.items_failed,
        "items_out_of_stock": job.items_out_of_stock,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "duration_seconds": job.duration_seconds,
        "error_message": job.error_message,
        "log_summary": job.log_summary,
    }


# ============================================================================
# Dashboard Stats
# ============================================================================

@app.get("/api/dashboard/stats")
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Count accounts and feeds
    total_accounts = db.query(EbayAccount).filter(
        EbayAccount.user_id == current_user.id,
        EbayAccount.is_active == True
    ).count()
    
    total_feeds = db.query(SupplierFeed).filter(
        SupplierFeed.user_id == current_user.id,
        SupplierFeed.is_active == True
    ).count()
    
    # Latest sync job
    latest_job = db.query(SyncJob).join(EbayAccount).filter(
        EbayAccount.user_id == current_user.id
    ).order_by(SyncJob.created_at.desc()).first()
    
    return {
        "total_accounts": total_accounts,
        "total_feeds": total_feeds,
        "last_sync_at": latest_job.completed_at if latest_job else None,
        "last_sync_status": latest_job.status.value if latest_job else None,
        "last_sync_items_updated": latest_job.items_updated if latest_job else 0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
