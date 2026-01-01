"""
Excel Analysis System - Main FastAPI Application
"""
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import os
from datetime import datetime
import uuid

from .auth import (
    create_user,
    authenticate_user,
    create_access_token,
    decode_access_token,
    get_password_hash,
)
from .storage import (
    upload_file_to_r2,
    download_file_from_r2,
    delete_file_from_r2,
    list_user_files,
    save_json_to_r2,
    load_json_from_r2,
)
from .analysis import analyze_excel
from .scheduler import start_scheduler
from .models import UserCreate, UserLogin, FileMetadata, AnalysisReport

# Initialize FastAPI app
app = FastAPI(
    title="Excel Analysis System",
    description="Secure Excel file analysis with automated data retention",
    version="1.0.0",
)

# CORS configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()


# Dependency to get current user from JWT token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Extract and validate user ID from JWT token."""
    token = credentials.credentials
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return user_id


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
    }


# Authentication endpoints
@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """Register a new user."""
    try:
        user_id = await create_user(user.email, user.password, user.full_name)
        return {
            "message": "User created successfully",
            "user_id": user_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        )


@app.post("/api/auth/login")
async def login(user: UserLogin):
    """Authenticate user and return JWT token."""
    user_data = await authenticate_user(user.email, user.password)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(data={"sub": user_data["user_id"]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user_data["user_id"],
            "email": user_data["email"],
            "full_name": user_data["full_name"],
        },
    }


@app.get("/api/auth/me")
async def get_current_user_info(user_id: str = Depends(get_current_user)):
    """Get current user information."""
    try:
        user_data = await load_json_from_r2(f"users/{user_id}/profile.json")
        if not user_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        return {
            "user_id": user_data["user_id"],
            "email": user_data["email"],
            "full_name": user_data["full_name"],
            "created_at": user_data["created_at"],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user information",
        )


# File management endpoints
@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    Upload an Excel file for analysis.
    
    The file is encrypted and stored in R2, then analyzed automatically.
    """
    # Validate file type
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Excel files (.xlsx, .xls) are allowed",
        )

    try:
        # Generate unique file ID
        file_id = str(uuid.uuid4())
        file_key = f"users/{user_id}/files/{file_id}/{file.filename}"

        # Read file content
        file_content = await file.read()

        # Upload encrypted file to R2
        await upload_file_to_r2(file_key, file_content)

        # Create metadata
        metadata = {
            "file_id": file_id,
            "filename": file.filename,
            "user_id": user_id,
            "upload_date": datetime.utcnow().isoformat(),
            "file_size": len(file_content),
            "status": "processing",
            "file_key": file_key,
        }

        # Save metadata
        metadata_key = f"users/{user_id}/files/{file_id}/metadata.json"
        await save_json_to_r2(metadata_key, metadata)

        # Analyze file
        try:
            # Download file to temporary location for analysis
            temp_file_path = f"/tmp/{file_id}_{file.filename}"
            decrypted_content = await download_file_from_r2(file_key)
            with open(temp_file_path, "wb") as f:
                f.write(decrypted_content)

            # Run analysis
            analysis_result = analyze_excel(temp_file_path)

            # Clean up temp file
            os.remove(temp_file_path)

            # Create report
            report = {
                "file_id": file_id,
                "filename": file.filename,
                "analysis_date": datetime.utcnow().isoformat(),
                "results": analysis_result,
            }

            # Save report
            report_key = f"users/{user_id}/files/{file_id}/report.json"
            await save_json_to_r2(report_key, report)

            # Update metadata status
            metadata["status"] = "completed"
            metadata["analysis_date"] = report["analysis_date"]
            await save_json_to_r2(metadata_key, metadata)

            return {
                "message": "File uploaded and analyzed successfully",
                "file_id": file_id,
                "filename": file.filename,
                "status": "completed",
            }

        except Exception as e:
            # Update metadata status to failed
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            await save_json_to_r2(metadata_key, metadata)

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Analysis failed: {str(e)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}",
        )


@app.get("/api/files")
async def list_files(user_id: str = Depends(get_current_user)):
    """List all files uploaded by the current user."""
    try:
        files = await list_user_files(user_id)
        return {"files": files}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list files",
        )


@app.get("/api/files/{file_id}")
async def get_file_info(file_id: str, user_id: str = Depends(get_current_user)):
    """Get metadata for a specific file."""
    try:
        metadata_key = f"users/{user_id}/files/{file_id}/metadata.json"
        metadata = await load_json_from_r2(metadata_key)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
            )

        return metadata
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch file information",
        )


@app.get("/api/files/{file_id}/report")
async def get_analysis_report(file_id: str, user_id: str = Depends(get_current_user)):
    """Get the analysis report for a specific file."""
    try:
        report_key = f"users/{user_id}/files/{file_id}/report.json"
        report = await load_json_from_r2(report_key)

        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
            )

        return report
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch analysis report",
        )


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str, user_id: str = Depends(get_current_user)):
    """Delete a file and its associated data."""
    try:
        # Get metadata first to check if file exists
        metadata_key = f"users/{user_id}/files/{file_id}/metadata.json"
        metadata = await load_json_from_r2(metadata_key)

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
            )

        # Delete all associated files
        file_key = metadata["file_key"]
        report_key = f"users/{user_id}/files/{file_id}/report.json"

        await delete_file_from_r2(file_key)
        await delete_file_from_r2(metadata_key)
        await delete_file_from_r2(report_key)

        return {"message": "File deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file",
        )


# Start the scheduler for data retention cleanup
@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    start_scheduler()
    print("✅ Scheduler started - Data retention cleanup active")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
