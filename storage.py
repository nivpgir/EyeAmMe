"""
Cloudflare R2 storage module with encryption support.
"""
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import os
import json
from typing import Optional, List, Dict
from cryptography.fernet import Fernet

from .config import settings

# R2 Configuration
# R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
# R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
# R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
# R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
# R2_ENDPOINT = os.getenv("R2_ENDPOINT")

# Encryption key (generate with: Fernet.generate_key())
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not all([settings.r2_account_id, settings.r2_access_key_id, settings.r2_secret_access_key, settings.r2_bucket_name]):
    raise ValueError("R2 configuration environment variables are not set")

if not ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY environment variable is not set")

# Initialize Fernet cipher
cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)

# Initialize S3 client for R2
s3_client = boto3.client(
    "s3",
    endpoint_url=settings.r2_endpoint,
    aws_access_key_id=settings.r2_access_key_id,
    aws_secret_access_key=settings.r2_secret_access_key,
    config=Config(signature_version="s3v4"),
    region_name="auto",
)


def encrypt_data(data: bytes) -> bytes:
    """Encrypt data using Fernet encryption."""
    return cipher_suite.encrypt(data)


def decrypt_data(encrypted_data: bytes) -> bytes:
    """Decrypt data using Fernet encryption."""
    return cipher_suite.decrypt(encrypted_data)


async def upload_file_to_r2(key: str, content: bytes) -> bool:
    """
    Upload a file to R2 with encryption.

    Args:
        key: Object key in R2 bucket
        content: File content as bytes

    Returns:
        True if successful, False otherwise
    """
    try:
        # Encrypt content
        encrypted_content = encrypt_data(content)

        # Upload to R2
        s3_client.put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=encrypted_content,
        )
        return True
    except ClientError as e:
        print(f"Error uploading to R2: {e}")
        return False


async def download_file_from_r2(key: str) -> Optional[bytes]:
    """
    Download and decrypt a file from R2.

    Args:
        key: Object key in R2 bucket

    Returns:
        Decrypted file content as bytes, or None if not found
    """
    try:
        response = s3_client.get_object(Bucket=settings.r2_bucket_name, Key=key)
        encrypted_content = response["Body"].read()

        # Decrypt content
        decrypted_content = decrypt_data(encrypted_content)
        return decrypted_content
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        print(f"Error downloading from R2: {e}")
        return None


async def delete_file_from_r2(key: str) -> bool:
    """
    Delete a file from R2.

    Args:
        key: Object key in R2 bucket

    Returns:
        True if successful, False otherwise
    """
    try:
        s3_client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
        return True
    except ClientError as e:
        print(f"Error deleting from R2: {e}")
        return False


async def list_objects_with_prefix(prefix: str) -> List[str]:
    """
    List all object keys with a given prefix.

    Args:
        prefix: Prefix to filter objects

    Returns:
        List of object keys
    """
    try:
        response = s3_client.list_objects_v2(Bucket=settings.r2_bucket_name, Prefix=prefix)
        if "Contents" not in response:
            return []

        return [obj["Key"] for obj in response["Contents"]]
    except ClientError as e:
        print(f"Error listing objects in R2: {e}")
        return []


async def save_json_to_r2(key: str, data: dict) -> bool:
    """
    Save a JSON object to R2 with encryption.

    Args:
        key: Object key in R2 bucket
        data: Dictionary to save as JSON

    Returns:
        True if successful, False otherwise
    """
    try:
        json_content = json.dumps(data, indent=2).encode("utf-8")
        return await upload_file_to_r2(key, json_content)
    except Exception as e:
        print(f"Error saving JSON to R2: {e}")
        return False


async def load_json_from_r2(key: str) -> Optional[dict]:
    """
    Load a JSON object from R2 with decryption.

    Args:
        key: Object key in R2 bucket

    Returns:
        Dictionary parsed from JSON, or None if not found
    """
    try:
        content = await download_file_from_r2(key)
        if content is None:
            return None

        return json.loads(content.decode("utf-8"))
    except Exception as e:
        print(f"Error loading JSON from R2: {e}")
        return None


async def list_user_files(user_id: str) -> List[Dict]:
    """
    List all files uploaded by a specific user.

    Args:
        user_id: User's unique identifier

    Returns:
        List of file metadata dictionaries
    """
    try:
        # List all metadata files for this user
        prefix = f"users/{user_id}/files/"
        keys = await list_objects_with_prefix(prefix)

        # Filter for metadata.json files
        metadata_keys = [key for key in keys if key.endswith("/metadata.json")]

        # Load all metadata
        files = []
        for metadata_key in metadata_keys:
            metadata = await load_json_from_r2(metadata_key)
            if metadata:
                files.append(metadata)

        # Sort by upload date (most recent first)
        files.sort(key=lambda x: x.get("upload_date", ""), reverse=True)

        return files
    except Exception as e:
        print(f"Error listing user files: {e}")
        return []


async def delete_user_file(user_id: str, file_id: str) -> bool:
    """
    Delete all data associated with a file (file, metadata, report).

    Args:
        user_id: User's unique identifier
        file_id: File's unique identifier

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get metadata to find file key
        metadata_key = f"users/{user_id}/files/{file_id}/metadata.json"
        metadata = await load_json_from_r2(metadata_key)

        if metadata is None:
            return False

        # Delete all associated files
        file_key = metadata["file_key"]
        report_key = f"users/{user_id}/files/{file_id}/report.json"

        await delete_file_from_r2(file_key)
        await delete_file_from_r2(metadata_key)
        await delete_file_from_r2(report_key)

        return True
    except Exception as e:
        print(f"Error deleting user file: {e}")
        return False


async def get_all_user_ids() -> List[str]:
    """
    Get all user IDs from the users index.

    Returns:
        List of user IDs
    """
    try:
        users_index = await load_json_from_r2("users/index.json")
        if users_index is None:
            return []

        return list(users_index["users"].values())
    except Exception as e:
        print(f"Error getting user IDs: {e}")
        return []
