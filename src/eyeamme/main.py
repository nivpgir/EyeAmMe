"""
Excel Analysis System - Main FastAPI Application
"""
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import os
from datetime import datetime
import uuid

from .auth import (
    create_user,
    authenticate_user,
    create_access_token,
    decode_access_token,
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

# Initialize FastAPI app
app = FastAPI(
    title="Excel Analysis System",
    description="Simple Excel file analysis",
    version="1.0.0",
)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

security = HTTPBearer(auto_error=False)


# Helper function to get user from cookie
def get_user_from_cookie(request: Request) -> Optional[str]:
    """Extract user ID from session cookie."""
    token = request.cookies.get("session_token")
    if not token:
        return None
    return decode_access_token(token)


def require_auth(request: Request):
    """Dependency to require authentication."""
    user_id = get_user_from_cookie(request)
    if not user_id:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user_id


# ============================================================================
# HTML PAGES
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Redirect to dashboard or login."""
    user_id = get_user_from_cookie(request)
    if user_id:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login/Register page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user_id: str = Depends(require_auth)):
    """Dashboard with file upload and list."""
    try:
        # Get user info
        user_data = await load_json_from_r2(f"users/{user_id}/profile.json")
        
        # Get user's files
        files = await list_user_files(user_id)
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "user": user_data,
                "files": files,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/report/{file_id}", response_class=HTMLResponse)
async def report_page(
    request: Request, file_id: str, user_id: str = Depends(require_auth)
):
    """View analysis report."""
    try:
        # Get report
        report_key = f"users/{user_id}/files/{file_id}/report.json"
        report = await load_json_from_r2(report_key)

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return templates.TemplateResponse(
            "report.html", {"request": request, "report": report}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.post("/api/register")
async def register(request: Request, email: str = Form(...), password: str = Form(...), full_name: str = Form(...)):
    """Register a new user."""
    try:
        user_id = await create_user(email, password, full_name)
        
        # Create session token
        token = create_access_token(data={"sub": user_id})
        
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
        return response
    except ValueError as e:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": str(e), "tab": "register"},
            status_code=400,
        )


@app.post("/api/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    """Authenticate user."""
    user_data = await authenticate_user(email, password)
    if not user_data:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=401,
        )

    # Create session token
    token = create_access_token(data={"sub": user_data["user_id"]})
    
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
    return response


@app.get("/api/logout")
async def logout():
    """Logout user."""
    response = RedirectResponse(url="/login")
    response.delete_cookie(key="session_token")
    return response


@app.post("/api/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Depends(require_auth),
):
    """Upload and analyze Excel file."""
    # Validate file type
    if not file.filename.endswith((".xlsx", ".xls")):
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "error": "Only Excel files (.xlsx, .xls) are allowed",
                "files": await list_user_files(user_id),
            },
            status_code=400,
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

        except Exception as e:
            # Update metadata status to failed
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            await save_json_to_r2(metadata_key, metadata)

        # Redirect back to dashboard
        return RedirectResponse(url="/dashboard", status_code=302)

    except Exception as e:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "error": f"Upload failed: {str(e)}",
                "files": await list_user_files(user_id),
            },
            status_code=500,
        )


@app.post("/api/delete/{file_id}")
async def delete_file_endpoint(
    request: Request, file_id: str, user_id: str = Depends(require_auth)
):
    """Delete a file."""
    try:
        # Get metadata first
        metadata_key = f"users/{user_id}/files/{file_id}/metadata.json"
        metadata = await load_json_from_r2(metadata_key)

        if not metadata:
            raise HTTPException(status_code=404, detail="File not found")

        # Delete all associated files
        file_key = metadata["file_key"]
        report_key = f"users/{user_id}/files/{file_id}/report.json"

        await delete_file_from_r2(file_key)
        await delete_file_from_r2(metadata_key)
        await delete_file_from_r2(report_key)

        return RedirectResponse(url="/dashboard", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }


# Start scheduler on startup
@app.on_event("startup")
async def startup_event():
    """Start background tasks."""
    start_scheduler()
    print("✅ Scheduler started - Data retention cleanup active")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
