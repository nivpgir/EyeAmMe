"""
Pydantic models for request/response validation.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# User models
class UserCreate(BaseModel):
    """Model for user registration."""

    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: str = Field(..., min_length=1, description="Full name is required")


class UserLogin(BaseModel):
    """Model for user login."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Model for user data in responses."""

    user_id: str
    email: EmailStr
    full_name: str
    created_at: str


# File models
class FileMetadata(BaseModel):
    """Model for file metadata."""

    file_id: str
    filename: str
    user_id: str
    upload_date: str
    file_size: int
    status: str  # "processing", "completed", "failed"
    file_key: str
    analysis_date: Optional[str] = None
    error: Optional[str] = None


class FileUploadResponse(BaseModel):
    """Model for file upload response."""

    message: str
    file_id: str
    filename: str
    status: str


class FileListResponse(BaseModel):
    """Model for file list response."""

    files: List[FileMetadata]


# Analysis models
class AnalysisReport(BaseModel):
    """Model for analysis report."""

    file_id: str
    filename: str
    analysis_date: str
    results: Dict[str, Any]


# Auth models
class Token(BaseModel):
    """Model for authentication token."""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Model for token payload data."""

    user_id: Optional[str] = None
