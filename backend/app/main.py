from __future__ import annotations

import csv
import io
import os
import logging
import uuid
import re # Added for regex validation
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, UploadFile, File, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr # Added EmailStr
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from supabase import create_client

import bcrypt # Switched to direct bcrypt usage to avoid Python 3.13 compatibility issues with passlib

# Configure logging for Vercel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

app = FastAPI(title="Delivery Challan API", version="1.0.0")

# Define router without a fixed prefix so we can mount it twice
router = APIRouter()


@app.get("/")
def root():
    return {"message": "API Running at root"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- User Models ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: str
    created_at: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    token: str
    new_password: str

class RoleUpdateRequest(BaseModel):
    role: str


class BulkDeleteRequest(BaseModel):
    ids: List[str]

# --- Utility Functions for Auth ---
def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def get_password_hash(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def validate_password_complexity(password: str):
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password.encode('utf-8')) > 72: # bcrypt limit
        raise ValueError("Password cannot be longer than 72 bytes (characters).")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", password):
        raise ValueError("Password must contain at least one special character.")

# --- Auth Endpoints ---
@router.post("/auth/signup", response_model=UserOut)
async def signup_user(user: UserCreate):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")

    try:
        validate_password_complexity(user.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    hashed_password = get_password_hash(user.password)
    role = "Admin" if user.email == "meenuga.raghavendra@orchidsintl.edu.in" else "User"
    new_user_data = {
        "id": str(uuid.uuid4()), 
        "email": user.email, 
        "hashed_password": hashed_password, 
        "role": role, 
        "created_at": now_iso()
    }

    try:
        response = client.table("users").insert(new_user_data).execute()
        if not response.data:
            logger.error(f"Supabase insert returned no data for signup of {user.email}")
            raise HTTPException(status_code=500, detail="Failed to create user in Supabase.")
        logger.info(f"User created successfully: {user.email}")
        return UserOut(**response.data[0])
    except Exception as e:
        if "duplicate key value violates unique constraint" in str(e):
            raise HTTPException(status_code=409, detail="Email already registered.")
        logger.error(f"Signup error for {user.email}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Supabase Signup Error: {str(e)}")

@router.post("/auth/login")
async def login_user(user: UserLogin):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")

    try:
        response = client.table("users").select("id, email, hashed_password, role").eq("email", user.email).execute()
        user_data = (response.data or [None])[0]

        if not user_data or not verify_password(user.password, user_data["hashed_password"]):
            raise HTTPException(status_code=401, detail="Incorrect email or password.")
        
        role = user_data.get("role", "User")
        # Hardcoded override to ensure this specific user is always Admin
        if user.email == "meenuga.raghavendra@orchidsintl.edu.in":
            role = "Admin"

        return {
            "message": "Login successful!", 
            "user_id": user_data["id"], 
            "role": role
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase Login Error: {str(e)}")


@router.post("/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")

    try:
        response = client.table("users").select("id").eq("email", request.email).execute()
        user_data = (response.data or [None])[0]

        if not user_data:
            # For security, don't reveal if the email exists or not
            return {"message": "If an account with that email exists, a password reset link has been sent."}

        reset_token = str(uuid.uuid4())
        reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1) # Token valid for 1 hour

        client.table("users").update({
            "reset_token": reset_token,
            "reset_token_expires_at": reset_token_expires_at.isoformat()
        }).eq("id", user_data["id"]).execute()

        # In a real application, you would send an email here
        print(f"Password reset token for {request.email}: {reset_token}")

        return {"message": "If an account with that email exists, a password reset link has been sent."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forgot Password Error: {str(e)}")


@router.post("/auth/reset-password")
async def reset_password(request: ResetPasswordRequest):
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")

    try:
        validate_password_complexity(request.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        response = client.table("users").select("id, reset_token, reset_token_expires_at").eq("email", request.email).execute()
        user_data = (response.data or [None])[0]

        if not user_data or user_data.get("reset_token") != request.token:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

        expires_at_str = user_data.get("reset_token_expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00')) # Handle 'Z' for UTC
            if expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

        hashed_password = get_password_hash(request.new_password)
        client.table("users").update({
            "hashed_password": hashed_password,
            "reset_token": None,
            "reset_token_expires_at": None
        }).eq("id", user_data["id"]).execute()

        return {"message": "Password has been reset successfully."}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset Password Error: {str(e)}")

@router.get("/users", response_model=List[UserOut])
async def list_users():
    client = get_supabase_client()
    if client:
        try:
            response = client.table("users").select("id, email, role, created_at").execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Fetch Error: {str(e)}")
    return []


@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, payload: RoleUpdateRequest):
    client = get_supabase_client()
    if client:
        try:
            client.table("users").update({"role": payload.role}).eq("id", user_id).execute()
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Update Error: {str(e)}")
    
    raise HTTPException(status_code=501, detail="Supabase not configured.")


class PlantCreate(BaseModel):
    name: str
    code: str
    address: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    pincode: Optional[str] = None
    gstin: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = "Active"


class PlantOut(PlantCreate):
    id: str
    created_at: Optional[str] = None


class ProductCreate(BaseModel):
    name: str
    code: str
    hsn_code: Optional[str] = None
    unit: Optional[str] = "Nos"
    description: Optional[str] = None


class ProductOut(ProductCreate):
    id: str
    created_at: Optional[str] = None


class ChallanItem(BaseModel):
    product_id: str
    product_name: str
    product_code: str
    unit: str
    quantity: float
    rate: float
    amount: float


class ChallanCreate(BaseModel):
    challan_number: Optional[str] = None
    challan_date: str
    from_plant_id: str
    from_plant_name: str
    from_plant_address: Optional[str] = None
    from_plant_state: Optional[str] = None
    from_plant_city: Optional[str] = None
    from_plant_pincode: Optional[str] = None
    from_plant_gstin: Optional[str] = None
    from_plant_branch: Optional[str] = None
    plant_id: str
    customer_name: str
    customer_address: Optional[str] = None
    customer_state: Optional[str] = None
    customer_city: Optional[str] = None
    customer_pincode: Optional[str] = None
    customer_gstin: Optional[str] = None
    vehicle_no: Optional[str] = None
    order_ref: Optional[str] = None
    docket_no: Optional[str] = None
    reason_for_dc: Optional[str] = None
    items: List[ChallanItem]
    created_by: Optional[str] = None # New field


class ChallanOut(ChallanCreate):
    id: str
    total_amount: float
    created_at: Optional[str] = None
    created_by: Optional[str] = None # New field


class InMemoryStore:
    def __init__(self) -> None:
        self.plants: List[Dict[str, Any]] = []
        self.products: List[Dict[str, Any]] = []
        self.challans: List[Dict[str, Any]] = []

    def create_plant(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        plant = {"id": payload.get("id") or str(uuid.uuid4()), **payload}
        self.plants.append(plant)
        return plant

    def list_plants(self) -> List[Dict[str, Any]]:
        return sorted(self.plants, key=lambda item: item.get("created_at", ""), reverse=True)

    def create_product(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        product = {"id": payload.get("id") or str(uuid.uuid4()), **payload}
        self.products.append(product)
        return product

    def list_products(self) -> List[Dict[str, Any]]:
        return sorted(self.products, key=lambda item: item.get("created_at", ""), reverse=True)

    def create_challan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        challan = {"id": payload.get("id") or str(uuid.uuid4()), **payload}
        self.challans.append(challan)
        return challan

    def list_challans(self) -> List[Dict[str, Any]]:
        return sorted(self.challans, key=lambda item: item.get("created_at", ""), reverse=True)

    def get_challan(self, challan_id: str) -> Optional[Dict[str, Any]]:
        for challan in self.challans:
            if challan.get("id") == challan_id:
                return challan
        return None


memory_store = InMemoryStore()


def get_supabase_client():
    # Use Service Role Key for backend administrative access to bypass RLS policies
    key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
    
    if SUPABASE_URL and key:
        # Determine which key type is being used for logging purposes
        key_type = "Service Role" if SUPABASE_SERVICE_ROLE_KEY else "Anon"
        logger.info(f"Supabase Client initialized. URL: {bool(SUPABASE_URL)}, Key Type: {key_type}")
        return create_client(SUPABASE_URL, key)
    
    logger.error(
        f"Supabase initialization failed. URL Present: {bool(SUPABASE_URL)}, "
        f"Service Key Present: {bool(SUPABASE_SERVICE_ROLE_KEY)}, Anon Key Present: {bool(SUPABASE_KEY)}"
    )
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(record)
    payload.setdefault("created_at", now_iso())
    return payload


@app.get("/health")
def health():
    client = get_supabase_client()
    db_status = "Not Initialized"
    db_error = None
    
    if client:
        try:
            # Perform a simple query to verify the connection works
            client.table("users").select("id").limit(1).execute()
            db_status = "Connected"
            logger.info("Health Check: Database connection successful.")
        except Exception as e:
            db_status = "Connection Failed"
            db_error = str(e)
            logger.error(f"Health Check: Database connection error: {db_error}")
            
    return {
        "status": "ok",
        "database": db_status,
        "database_error": db_error,
        "env_url_found": bool(SUPABASE_URL),
        "env_service_key_found": bool(SUPABASE_SERVICE_ROLE_KEY),
        "using_service_role": bool(SUPABASE_SERVICE_ROLE_KEY)
    }


@router.get("/plants", response_model=List[PlantOut])
def read_plants() -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if client:
        try:
            response = client.table("plants").select("*").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase Fetch Error: {str(e)}")
    return memory_store.list_plants()


@router.post("/plants", response_model=PlantOut)
def create_plant(payload: PlantCreate) -> Dict[str, Any]:
    item = build_payload(payload.model_dump())
    item["id"] = str(uuid.uuid4())
    client = get_supabase_client()
    if client:
        try:
            response = client.table("plants").insert(item).execute()
            if not response.data:
                raise HTTPException(
                    status_code=500, 
                    detail="No data returned from Supabase. Ensure the 'plants' table exists and RLS policies allow insertion."
                )
            return response.data[0]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Supabase Insert Error: {str(e)}")
    return memory_store.create_plant(item)


@router.delete("/plants/{id}")
def delete_plant(id: str):
    client = get_supabase_client()
    if client:
        try:
            client.table("plants").delete().eq("id", id).execute()
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Delete Error: {str(e)}")
    
    memory_store.plants = [p for p in memory_store.plants if p.get("id") != id]
    return {"status": "success"}


@router.post("/plants/bulk-delete")
def bulk_delete_plants(payload: BulkDeleteRequest):
    client = get_supabase_client()
    if client:
        try:
            client.table("plants").delete().in_("id", payload.ids).execute()
            return {"status": "success", "count": len(payload.ids)}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bulk Delete Error: {str(e)}")
    
    ids_to_del = set(payload.ids)
    memory_store.plants = [p for p in memory_store.plants if p.get("id") not in ids_to_del]
    return {"status": "success", "count": len(payload.ids)}


@router.post("/plants/bulk-upload", response_model=List[PlantOut])
async def bulk_upload_plants(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    csv_reader = csv.DictReader(io.StringIO(contents.decode('utf-8')))
    
    plants_to_insert = []
    errors = []
    
    for idx, row in enumerate(csv_reader, start=2):
        try:
            # Basic validation
            if not row.get("name") or not row.get("code"):
                errors.append(f"Row {idx}: Name and Code are required.")
                continue
                
            plant = {
                "id": str(uuid.uuid4()),
                "name": row.get("name").strip(),
                "code": row.get("code").strip(),
                "address": row.get("address", "").strip(),
                "state": row.get("state", "").strip(),
                "city": row.get("city", "").strip(),
                "pincode": row.get("pincode", "").strip(),
                "gstin": row.get("gstin", "").strip(),
                "contact_person": row.get("contact_person", "").strip(),
                "phone": row.get("phone", "").strip(),
                "status": row.get("status", "Active").strip() or "Active",
                "created_at": now_iso()
            }
            plants_to_insert.append(plant)
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    if errors:
        raise HTTPException(status_code=400, detail={"message": "CSV Validation Errors", "errors": errors})

    client = get_supabase_client()
    if client and plants_to_insert:
        response = client.table("plants").insert(plants_to_insert).execute()
        return response.data
    elif not client:
        for p in plants_to_insert: memory_store.create_plant(p)
        return plants_to_insert
    return []


@router.get("/products", response_model=List[ProductOut])
def read_products() -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if client:
        try:
            response = client.table("products").select("*").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase Fetch Error: {str(e)}")
    return memory_store.list_products()


@router.post("/products", response_model=ProductOut)
def create_product(payload: ProductCreate) -> Dict[str, Any]:
    item = build_payload(payload.model_dump())
    item["id"] = str(uuid.uuid4())
    client = get_supabase_client()
    if client:
        try:
            response = client.table("products").insert(item).execute()
            if not response.data:
                raise HTTPException(status_code=500, detail="No data returned. Check RLS policies on 'products' table.")
            return response.data[0]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Supabase Insert Error: {str(e)}")
    return memory_store.create_product(item)


@router.delete("/products/{id}")
def delete_product(id: str):
    client = get_supabase_client()
    if client:
        try:
            client.table("products").delete().eq("id", id).execute()
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Delete Error: {str(e)}")

    memory_store.products = [p for p in memory_store.products if p.get("id") != id]
    return {"status": "success"}


@router.post("/products/bulk-delete")
def bulk_delete_products(payload: BulkDeleteRequest):
    client = get_supabase_client()
    if client:
        try:
            client.table("products").delete().in_("id", payload.ids).execute()
            return {"status": "success", "count": len(payload.ids)}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bulk Delete Error: {str(e)}")

    ids_to_del = set(payload.ids)
    memory_store.products = [p for p in memory_store.products if p.get("id") not in ids_to_del]
    return {"status": "success", "count": len(payload.ids)}


@router.post("/products/bulk-upload", response_model=List[ProductOut])
async def bulk_upload_products(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    csv_reader = csv.DictReader(io.StringIO(contents.decode('utf-8')))
    
    products_to_insert = []
    errors = []
    
    for idx, row in enumerate(csv_reader, start=2):
        try:
            if not row.get("name") or not row.get("code"):
                errors.append(f"Row {idx}: Name and Code are required.")
                continue
                
            product = {
                "id": str(uuid.uuid4()),
                "name": row.get("name").strip(),
                "code": row.get("code").strip(),
                "hsn_code": row.get("hsn_code", "").strip(),
                "unit": row.get("unit", "Nos").strip() or "Nos",
                "description": row.get("description", "").strip(),
                "created_at": now_iso()
            }
            products_to_insert.append(product)
        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    if errors:
        raise HTTPException(status_code=400, detail={"message": "CSV Validation Errors", "errors": errors})

    client = get_supabase_client()
    if client and products_to_insert:
        response = client.table("products").insert(products_to_insert).execute()
        return response.data
    elif not client:
        for p in products_to_insert: memory_store.create_product(p)
        return products_to_insert
    return []


@router.get("/challans", response_model=List[ChallanOut])
def read_challans() -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if client:
        try:
            response = client.table("challans").select("*").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase Fetch Error: {str(e)}")
    return memory_store.list_challans()


@router.get("/challans/next-number")
def get_next_challan_number() -> Dict[str, str]:
    """Calculates the next DC number based on SSPL prefix and starting sequence 1010767."""
    prefix = "SSPL"
    start_num = 1010767
    client = get_supabase_client()
    
    if client:
        try:
            # Fetch existing numbers to find the highest one
            response = client.table("challans").select("challan_number").ilike("challan_number", f"{prefix}%").execute()
            if response.data:
                numeric_values = []
                for row in response.data:
                    num_str = row["challan_number"][len(prefix):]
                    if num_str.isdigit():
                        numeric_values.append(int(num_str))
                
                if numeric_values:
                    next_val = max(max(numeric_values) + 1, start_num)
                    return {"next_number": f"{prefix}{next_val}"}
        except Exception:
            pass
            
    return {"next_number": f"{prefix}{start_num}"}


def _create_challan_entry(challan_payload: Dict[str, Any]) -> Dict[str, Any]:
    
    # Auto-generate challan number if not provided
    if not challan_payload.get("challan_number"):
        next_num_data = get_next_challan_number()
        challan_payload["challan_number"] = next_num_data["next_number"]

    challan_payload["id"] = str(uuid.uuid4())
    challan_payload["created_at"] = now_iso()
    challan_payload["total_amount"] = round(sum(item["quantity"] * item["rate"] for item in challan_payload.get("items", [])), 2)

    client = get_supabase_client()
    if client:
        try:
            response = client.table("challans").insert(challan_payload).execute()
            if not response.data:
                raise HTTPException(status_code=500, detail="No data returned. Check RLS policies on 'challans' table.")
            return response.data[0]
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Supabase Insert Error: {str(e)}")
    return memory_store.create_challan(challan_payload)


@router.delete("/challans/{id}")
def delete_challan(id: str):
    client = get_supabase_client()
    if client:
        try:
            client.table("challans").delete().eq("id", id).execute()
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Delete Error: {str(e)}")

    memory_store.challans = [c for c in memory_store.challans if c.get("id") != id]
    return {"status": "success"}


@router.post("/challans/bulk-delete")
def bulk_delete_challans(payload: BulkDeleteRequest):
    client = get_supabase_client()
    if client:
        try:
            client.table("challans").delete().in_("id", payload.ids).execute()
            return {"status": "success", "count": len(payload.ids)}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bulk Delete Error: {str(e)}")

    ids_to_del = set(payload.ids)
    memory_store.challans = [c for c in memory_store.challans if c.get("id") not in ids_to_del]
    return {"status": "success", "count": len(payload.ids)}


@router.post("/challans", response_model=ChallanOut, tags=["Challans"])
def create_challan(payload: ChallanCreate) -> Dict[str, Any]:
    return _create_challan_entry(payload.model_dump())


# Helper to fetch plant by code
def _get_plant_by_code(client, code: str) -> Optional[Dict[str, Any]]:
    response = client.table("plants").select("*").eq("code", code).execute()
    return (response.data or [None])[0]

# Helper to fetch product by code (SKU)
def _get_product_by_code(client, code: str) -> Optional[Dict[str, Any]]:
    response = client.table("products").select("*").eq("code", code).execute()
    return (response.data or [None])[0]


@router.post("/challans/bulk-upload", response_model=List[ChallanOut])
async def bulk_upload_challans(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    csv_reader = csv.reader(io.StringIO(contents.decode('utf-8')))
    
    try:
        header = next(csv_reader) # Skip header row
    except StopIteration:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")

    expected_header = ["from_plant_code", "to_plant_code", "sku", "item_name", "quantity", "rate", "order_ref", "docket_no", "reason_for_dc"]
    if [h.strip().lower() for h in header] != expected_header:
        raise HTTPException(status_code=400, detail=f"CSV header must be exactly: {', '.join(expected_header)}")

    challans_grouped_by_metadata: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    processing_errors = []
    line_num = 1

    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Supabase client not initialized.")

    all_plant_codes = set()
    all_product_codes = set()
    parsed_rows = []

    for row in csv_reader:
        line_num += 1
        if not row or all(not cell.strip() for cell in row): # Skip empty rows
            continue

        if len(row) != len(expected_header):
            processing_errors.append(f"Line {line_num}: Incorrect number of columns. Expected {len(expected_header)}, got {len(row)}.")
            continue
        
        try:
            from_plant_code = row[0].strip()
            to_plant_code = row[1].strip()
            sku = row[2].strip()
            item_name_csv = row[3].strip()
            quantity = float(row[4].strip())
            rate = float(row[5].strip())
            order_ref = row[6].strip() if len(row) > 6 else ""
            docket_no = row[7].strip() if len(row) > 7 else ""
            reason_for_dc = row[8].strip() if len(row) > 8 else ""

            if not from_plant_code:
                processing_errors.append(f"Line {line_num}: 'From Plant Code' is required.")
                continue
            if not to_plant_code:
                processing_errors.append(f"Line {line_num}: 'To Plant Code' is required.")
                continue
            if not sku:
                processing_errors.append(f"Line {line_num}: 'SKU' is required.")
                continue
            if quantity <= 0:
                processing_errors.append(f"Line {line_num}: Quantity must be positive.")
                continue
            if rate < 0:
                processing_errors.append(f"Line {line_num}: Rate cannot be negative.")
                continue

            all_plant_codes.add(from_plant_code)
            all_plant_codes.add(to_plant_code)
            all_product_codes.add(sku)
            parsed_rows.append({
                "line_num": line_num,
                "from_plant_code": from_plant_code,
                "to_plant_code": to_plant_code,
                "sku": sku,
                "item_name_csv": item_name_csv,
                "quantity": quantity,
                "rate": rate,
                "order_ref": order_ref,
                "docket_no": docket_no,
                "reason_for_dc": reason_for_dc
            })
        except ValueError as e:
            processing_errors.append(f"Line {line_num}: Data type error - {e}.")
        except Exception as e:
            processing_errors.append(f"Line {line_num}: Unexpected error during parsing - {e}.")

    if processing_errors:
        raise HTTPException(status_code=400, detail={"message": "CSV parsing errors", "errors": processing_errors})

    # Batch lookup for plants and products
    plants_by_code = {}
    plants_by_id = {}
    products_by_code = {}
    products_by_id = {}

    if all_plant_codes:
        try:
            plant_response = client.table("plants").select("*").in_("code", list(all_plant_codes)).execute()
            for p in plant_response.data:
                plants_by_code[p["code"]] = p
                plants_by_id[p["id"]] = p
        except Exception as e:
            processing_errors.append(f"Error fetching plants from Supabase: {e}")

    if all_product_codes:
        try:
            product_response = client.table("products").select("*").in_("code", list(all_product_codes)).execute()
            for p in product_response.data:
                products_by_code[p["code"]] = p
                products_by_id[p["id"]] = p
        except Exception as e:
            processing_errors.append(f"Error fetching products from Supabase: {e}")
    
    if processing_errors:
        raise HTTPException(status_code=500, detail={"message": "Database lookup errors", "errors": processing_errors})

    # Second pass: Build challan payloads and group items
    for row_data in parsed_rows:
        from_plant_code = row_data["from_plant_code"]
        to_plant_code = row_data["to_plant_code"]
        sku = row_data["sku"]
        item_name_csv = row_data["item_name_csv"]
        quantity = row_data["quantity"]
        rate = row_data["rate"]
        order_ref = row_data["order_ref"]
        docket_no = row_data["docket_no"]
        reason_for_dc = row_data["reason_for_dc"]
        line_num = row_data["line_num"]

        from_plant = plants_by_code.get(from_plant_code)
        to_plant = plants_by_code.get(to_plant_code)
        product = products_by_code.get(sku)

        if not from_plant:
            processing_errors.append(f"Line {line_num}: 'From Plant' with code '{from_plant_code}' not found in Plant Master.")
            continue
        if not to_plant:
            processing_errors.append(f"Line {line_num}: 'To Plant' with code '{to_plant_code}' not found in Plant Master.")
            continue
        if not product:
            processing_errors.append(f"Line {line_num}: Product with SKU '{sku}' not found in Product Master.")
            continue

        item_amount = round(quantity * rate, 2)
        challan_item = ChallanItem(
            product_id=product["id"],
            product_name=product.get("name", item_name_csv),
            product_code=product["code"],
            unit=product.get("unit", "Nos"),
            quantity=quantity,
            rate=rate,
            amount=item_amount
        )
        
        challans_grouped_by_metadata[(from_plant["id"], to_plant["id"], order_ref, docket_no, reason_for_dc)].append(challan_item.model_dump())

    if processing_errors:
        raise HTTPException(status_code=400, detail={"message": "Data validation errors", "errors": processing_errors})

    created_challans = []
    for (from_plant_id, to_plant_id, order_ref, docket_no, reason_for_dc), items_data in challans_grouped_by_metadata.items():
        from_plant = plants_by_id[from_plant_id]
        to_plant = plants_by_id[to_plant_id]

        challan_payload = ChallanCreate(
            challan_date=datetime.now(timezone.utc).isoformat().split('T')[0], # Use current date for bulk upload
            from_plant_id=from_plant["id"],
            from_plant_name=from_plant["name"],
            from_plant_address=from_plant.get("address"),
            from_plant_state=from_plant.get("state"),
            from_plant_city=from_plant.get("city"),
            from_plant_pincode=from_plant.get("pincode"),
            from_plant_gstin=from_plant.get("gstin"),
            from_plant_branch=from_plant.get("name"), # Assuming branch name is plant name
            plant_id=to_plant["id"],
            customer_name=to_plant["name"],
            customer_address=to_plant.get("address"),
            customer_state=to_plant.get("state"),
            customer_city=to_plant.get("city"),
            customer_pincode=to_plant.get("pincode"),
            customer_gstin=to_plant.get("gstin"),
            items=items_data,
            order_ref=order_ref,
            docket_no=docket_no,
            reason_for_dc=reason_for_dc,
            vehicle_no=None
        )
        
        try:
            created_challan = _create_challan_entry(challan_payload.model_dump())
            created_challans.append(created_challan)
        except HTTPException as e:
            processing_errors.append(f"Error creating challan for From Plant '{from_plant['name']}' to To Plant '{to_plant['name']}': {e.detail}")
        except Exception as e:
            processing_errors.append(f"Unexpected error creating challan: {e}")

    if processing_errors:
        # If some challans were created and some failed, return 207 Multi-Status or 200 with errors
        # For simplicity, let's raise 400 if any errors occurred during creation phase
        raise HTTPException(status_code=400, detail={"message": "Errors during challan creation", "errors": processing_errors, "created_challans_count": len(created_challans)})

    return created_challans


@router.get("/reports/product-wise/csv")
def export_product_wise_csv(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Exports all challan items in a product-wise CSV format."""
    client = get_supabase_client()
    if client:
        try:
            query = client.table("challans").select("*")
            if start_date:
                query = query.gte("challan_date", start_date)
            if end_date:
                query = query.lte("challan_date", end_date)
            response = query.order("challan_date", desc=True).execute()
            challans = response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Report Error: {str(e)}")
    else:
        challans = memory_store.list_challans()

    output = io.StringIO()
    writer = csv.writer(output) # New field
    writer.writerow(["Challan No", "Date", "From Plant", "To Plant", "SKU", "Item Name", "UOM", "Qty", "Rate", "Amount", "Order Ref", "Docket No", "Reason for DC", "Created By"])
    
    for c in challans:
        for item in c.get("items", []):
            writer.writerow([
                c.get("challan_number"),
                c.get("challan_date"),
                c.get("from_plant_name"),
                c.get("customer_name"),
                item.get("product_code"),
                item.get("product_name"),
                item.get("unit"),
                item.get("quantity"),
                item.get("rate"),
                item.get("amount"),
                c.get("order_ref"),
                c.get("docket_no"),
                c.get("reason_for_dc"),
                c.get("created_by") # New field
            ])
            
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=product_wise_challan_report.csv"}
    )


@router.get("/reports/masters/plants/csv")
def export_plants_master_csv():
    client = get_supabase_client()
    if client:
        response = client.table("plants").select("*").order("name").execute()
        data = response.data or []
    else:
        data = memory_store.list_plants()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Code", "Address", "City", "State", "Pincode", "GSTIN", "Contact", "Phone", "Status"])
    for p in data:
        writer.writerow([p.get("name"), p.get("code"), p.get("address"), p.get("city"), p.get("state"), p.get("pincode"), p.get("gstin"), p.get("contact_person"), p.get("phone"), p.get("status")])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plant_master_report.csv"}
    )


@router.get("/reports/masters/products/csv")
def export_products_master_csv():
    client = get_supabase_client()
    if client:
        response = client.table("products").select("*").order("name").execute()
        data = response.data or []
    else:
        data = memory_store.list_products()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Code", "HSN Code", "Unit", "Description"])
    for p in data:
        writer.writerow([p.get("name"), p.get("code"), p.get("hsn_code"), p.get("unit"), p.get("description")])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=product_master_report.csv"}
    )


@router.get("/templates/{template_name}")
def download_template(template_name: str):
    """Provides sample CSV templates for bulk uploads."""
    templates = {
        "plants": "name,code,address,state,city,pincode,gstin,contact_person,phone,status\nPlant A,PA001,123 Main St,Karnataka,Bangalore,560001,29ABCDE1234F1Z5,John Doe,9876543210,Active",
        "products": "name,code,hsn_code,unit,description\nProduct X,PX001,123456,Nos,Description for Product X",
        "challans": "from_plant_code,to_plant_code,sku,item_name,quantity,rate,order_ref,docket_no,reason_for_dc\nPA001,PB002,PX001,Product X,10,150.75,REF-001,DOCK-99,Stock Transfer"
    }
    if template_name not in templates:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return Response(
        content=templates[template_name],
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={template_name}_template.csv"}
    )


@router.get("/challans/{challan_id}/pdf")
def download_challan_pdf(challan_id: str) -> Response:
    client = get_supabase_client()
    if client:
        response = client.table("challans").select("*").eq("id", challan_id).execute()
        challan = (response.data or [None])[0]
    else:
        challan = memory_store.get_challan(challan_id)

    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")

    pdf_bytes = build_challan_pdf(challan)
    headers = {"Content-Disposition": f'attachment; filename="challan_{challan_id}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


def build_challan_pdf(challan: Dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    
    # Custom Styles
    header_style = ParagraphStyle("Header", fontSize=14, leading=16, alignment=1, spaceAfter=2, fontName="Helvetica-Bold")
    sub_header_style = ParagraphStyle("SubHeader", fontSize=10, leading=12, alignment=1, spaceAfter=10)
    table_label_style = ParagraphStyle("Label", fontSize=9, leading=11, fontName="Helvetica-Bold")
    table_value_style = ParagraphStyle("Value", fontSize=9, leading=11)

    story = []
    
    # Header
    story.append(Paragraph("DELIVERY CHALLAN", header_style))
    story.append(Paragraph("SCHOOL SHOP PRIVATE LIMITED", header_style))
    story.append(Paragraph("STOCK TRANSFER NOTE", ParagraphStyle("Note", fontSize=11, leading=13, alignment=1, fontName="Helvetica-Bold", spaceAfter=10)))

    # Date and Challan No Row
    date_info = [
        [Paragraph(f"Date: {challan.get('challan_date')}", table_label_style), "", Paragraph(f"Challan No: {str(challan.get('challan_number'))}", table_label_style)]
    ]
    t_date = Table(date_info, colWidths=[60*mm, 70*mm, 60*mm])
    t_date.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    story.append(t_date)
    story.append(Spacer(1, 2 * mm))

    # From / To Section
    addr_data = [
        [Paragraph("From", table_label_style), "", Paragraph("To", table_label_style), ""],
        [Paragraph(str(challan.get('from_plant_name', '')), table_value_style), "", Paragraph(str(challan.get('customer_name', '')), table_value_style), ""],
        [Paragraph(f"Address: {challan.get('from_plant_address', '')}", table_value_style), "", Paragraph(f"Address: {challan.get('customer_address', '')}", table_value_style), ""],
        [Paragraph(f"State: {challan.get('from_plant_state', '')}", table_value_style), "", Paragraph(f"State: {challan.get('customer_state', '')}", table_value_style), ""],
        [Paragraph(f"City: {challan.get('from_plant_city', '')}", table_value_style), "", Paragraph(f"City: {challan.get('customer_city', '')}", table_value_style), ""],
        [Paragraph(f"Pincode: {challan.get('from_plant_pincode', '')}", table_value_style), "", Paragraph(f"Pincode: {challan.get('customer_pincode', '')}", table_value_style), ""],
        [Paragraph(f"GSTIN: {challan.get('from_plant_gstin', '')}", table_value_style), "", Paragraph(f"GSTIN: {challan.get('customer_gstin', '')}", table_value_style), ""],
        [Paragraph(f"Branch Name: {challan.get('from_plant_branch', '')}", table_value_style), "", Paragraph(f"Branch Name: {challan.get('customer_name', '')}", table_value_style), ""],
        [Paragraph(f"Order Ref: {challan.get('order_ref', '')}", table_value_style), "", Paragraph(f"Docket No: {challan.get('docket_no', '')}", table_value_style), ""]
    ]
    t_addr = Table(addr_data, colWidths=[95*mm, 5*mm, 95*mm, 0*mm])
    t_addr.setStyle(TableStyle([
        ('GRID', (0,0), (0,-1), 0.5, colors.grey),
        ('GRID', (2,0), (2,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_addr)
    story.append(Spacer(1, 5 * mm))

    # Items Table
    item_rows = [["S.No", "SKU", "Item Name", "UOM", "QTY.", "Rate", "Amount"]]
    total_qty = 0
    for idx, item in enumerate(challan.get("items", []), 1):
        qty = item.get("quantity", 0)
        total_qty += qty
        item_rows.append([
            str(idx),
            item.get("product_code", ""),
            item.get("product_name", ""),
            item.get("unit", "Nos"),
            str(qty),
            str(item.get("rate", 0)),
            str(item.get("amount", 0)),
        ])
    
    # Total Row
    item_rows.append(["", "", "TOTAL", "", str(total_qty), "", str(challan.get("total_amount", 0))])

    table = Table(item_rows, colWidths=[12*mm, 30*mm, 70*mm, 18*mm, 18*mm, 18*mm, 24*mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10 * mm))

    # Footer
    footer_text = "The above mentioned items are Sending for Branch. It does't hold any commercial value."
    story.append(Paragraph(footer_text, table_value_style))
    story.append(Spacer(1, 15 * mm))
    story.append(Paragraph("Authorised Signatory", ParagraphStyle("Sign", fontSize=10, alignment=2, fontName="Helvetica-Bold")))

    story.append(Paragraph(f"Created By: {challan.get('created_by', 'N/A')}", table_value_style))
    doc.build(story)
    return buffer.getvalue()


# Include the router with /api prefix only to avoid ambiguous routing
app.include_router(router, prefix="/api", tags=["API"])
