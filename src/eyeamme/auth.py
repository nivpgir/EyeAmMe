"""
Authentication module for user management and JWT tokens.
"""
from datetime import datetime, timedelta
from typing import Optional
import os
import uuid

from jose import JWTError, jwt
from passlib.context import CryptContext

from .storage import save_json_to_r2, load_json_from_r2

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Dictionary containing claims (must include 'sub' for user_id)
        expires_delta: Optional custom expiration time
        
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[str]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        User ID if token is valid, None otherwise
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        return None


async def create_user(email: str, password: str, full_name: str) -> str:
    """
    Create a new user account.
    
    Args:
        email: User's email address
        password: Plain text password (will be hashed)
        full_name: User's full name
        
    Returns:
        User ID
        
    Raises:
        ValueError: If user already exists
    """
    # Check if user already exists
    # We'll use a simple approach: try to load users index
    users_index_key = "users/index.json"
    users_index = await load_json_from_r2(users_index_key)

    if users_index is None:
        users_index = {"users": {}}

    # Check if email already exists
    if email in users_index["users"]:
        raise ValueError("User with this email already exists")

    # Generate user ID
    user_id = str(uuid.uuid4())

    # Create user profile
    user_data = {
        "user_id": user_id,
        "email": email,
        "full_name": full_name,
        "hashed_password": get_password_hash(password),
        "created_at": datetime.utcnow().isoformat(),
    }

    # Save user profile
    user_profile_key = f"users/{user_id}/profile.json"
    await save_json_to_r2(user_profile_key, user_data)

    # Update users index
    users_index["users"][email] = user_id
    await save_json_to_r2(users_index_key, users_index)

    return user_id


async def authenticate_user(email: str, password: str) -> Optional[dict]:
    """
    Authenticate a user with email and password.
    
    Args:
        email: User's email address
        password: Plain text password
        
    Returns:
        User data dictionary if authentication successful, None otherwise
    """
    # Load users index
    users_index_key = "users/index.json"
    users_index = await load_json_from_r2(users_index_key)

    if users_index is None or email not in users_index["users"]:
        return None

    user_id = users_index["users"][email]

    # Load user profile
    user_profile_key = f"users/{user_id}/profile.json"
    user_data = await load_json_from_r2(user_profile_key)

    if user_data is None:
        return None

    # Verify password
    if not verify_password(password, user_data["hashed_password"]):
        return None

    # Return user data (without password hash)
    return {
        "user_id": user_data["user_id"],
        "email": user_data["email"],
        "full_name": user_data["full_name"],
        "created_at": user_data["created_at"],
    }


async def get_user_by_id(user_id: str) -> Optional[dict]:
    """
    Get user data by user ID.
    
    Args:
        user_id: User's unique identifier
        
    Returns:
        User data dictionary if found, None otherwise
    """
    user_profile_key = f"users/{user_id}/profile.json"
    user_data = await load_json_from_r2(user_profile_key)

    if user_data is None:
        return None

    # Return user data (without password hash)
    return {
        "user_id": user_data["user_id"],
        "email": user_data["email"],
        "full_name": user_data["full_name"],
        "created_at": user_data["created_at"],
    }
