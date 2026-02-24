"""
Database models for DropSync SaaS
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class PlanType(enum.Enum):
    FREE_TRIAL = "free_trial"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class SyncStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    
    # Subscription
    plan = Column(Enum(PlanType), default=PlanType.FREE_TRIAL)
    stripe_customer_id = Column(String(255), unique=True)
    stripe_subscription_id = Column(String(255))
    subscription_expires_at = Column(DateTime)
    
    # Limits based on plan
    max_accounts = Column(Integer, default=1)
    max_listings = Column(Integer, default=10000)
    max_feeds = Column(Integer, default=2)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    ebay_accounts = relationship("EbayAccount", back_populates="user", cascade="all, delete-orphan")
    supplier_feeds = relationship("SupplierFeed", back_populates="user", cascade="all, delete-orphan")


class EbayAccount(Base):
    __tablename__ = "ebay_accounts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # eBay credentials
    store_name = Column(String(255))
    ebay_user_id = Column(String(255))
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    
    # eBay API keys (from user's eBay developer account)
    app_id = Column(String(255), nullable=False)
    dev_id = Column(String(255), nullable=False)
    cert_id = Column(String(255), nullable=False)
    
    # Settings
    sync_enabled = Column(Boolean, default=True)
    sync_frequency = Column(String(50), default="daily")  # daily, hourly, manual
    sync_time = Column(String(10), default="06:00")  # HH:MM format
    quantity_mode = Column(String(20), default="binary")  # binary or exact
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_sync_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    user = relationship("User", back_populates="ebay_accounts")
    sync_jobs = relationship("SyncJob", back_populates="account", cascade="all, delete-orphan")


class SupplierFeed(Base):
    __tablename__ = "supplier_feeds"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Feed details
    name = Column(String(255), nullable=False)
    feed_url = Column(Text, nullable=False)
    feed_type = Column(String(50), nullable=False)  # azuregreen, diecast, custom
    
    # Column mapping for custom feeds
    sku_column = Column(String(100), default="NUMBER")
    quantity_column = Column(String(100), default="UNITS")
    discontinued_column = Column(String(100))
    cant_sell_column = Column(String(100))
    
    # Settings
    is_active = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_fetched_at = Column(DateTime)
    total_skus = Column(Integer, default=0)
    
    # Relationships
    user = relationship("User", back_populates="supplier_feeds")


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("ebay_accounts.id"), nullable=False)
    
    # Job details
    status = Column(Enum(SyncStatus), default=SyncStatus.PENDING)
    triggered_by = Column(String(50))  # manual, scheduled, webhook
    
    # Results
    total_listings_checked = Column(Integer, default=0)
    items_updated = Column(Integer, default=0)
    items_failed = Column(Integer, default=0)
    items_out_of_stock = Column(Integer, default=0)
    
    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)
    
    # Logs
    error_message = Column(Text)
    log_summary = Column(Text)  # JSON with details
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    account = relationship("EbayAccount", back_populates="sync_jobs")


class SKUMapping(Base):
    """Optional: For users whose eBay SKU != Supplier SKU"""
    __tablename__ = "sku_mappings"
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("ebay_accounts.id"), nullable=False)
    feed_id = Column(Integer, ForeignKey("supplier_feeds.id"), nullable=False)
    
    ebay_sku = Column(String(255), nullable=False)
    supplier_sku = Column(String(255), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Indexes for fast lookup
    __table_args__ = (
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )
