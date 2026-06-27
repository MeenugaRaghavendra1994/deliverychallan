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
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, UploadFile, File, APIRouter, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr # Added EmailStr
from reportlab.graphics.shapes import Drawing, Path, Line, String, Group
from reportlab.lib.colors import HexColor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@router.get("/")
def root():
    return {"message": "API Running at root"}

# 1. Set up a paragraph style for your table cells
styles = getSampleStyleSheet()
cell_text_style = ParagraphStyle(
    'TableCellStyle',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=10,
    leading=12 # Adjust leading (line spacing) to match font size
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
        hashed_token = get_password_hash(reset_token)
        reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1) # Token valid for 1 hour

        client.table("users").update({
            "reset_token": hashed_token,
            "reset_token_expires_at": reset_token_expires_at.isoformat()
        }).eq("id", user_data["id"]).execute()

        # In a real application, you would send an email here
        print(f"Password reset token for {request.email}: {reset_token}")

        return {
            "message": "If an account with that email exists, a password reset link has been sent.",
            "token": reset_token  # Returning token for auto-fill in UI
        }
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

        if not user_data or not verify_password(request.token, user_data.get("reset_token", "")):
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
    from_plant_name: Optional[str] = None
    from_plant_address: Optional[str] = None
    from_plant_state: Optional[str] = None
    from_plant_city: Optional[str] = None
    from_plant_pincode: Optional[str] = None
    from_plant_gstin: Optional[str] = None
    from_plant_branch: Optional[str] = None
    plant_id: str
    customer_name: Optional[str] = None
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
    cancelled: bool = False
    cancelled_at: Optional[str] = None
    cancel_reason: Optional[str] = None


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


@router.get("/health", tags=["System"])
def health():
    client = get_supabase_client() 
    logger.info("Health check endpoint hit via /api/health (router level)")
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
def read_plants(search: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    logger.debug(f"read_plants called. search={search!r}, limit={limit}, client_initialized={bool(client)}")
    # If we have a Supabase client, prefer DB-backed lookup but be defensive
    if client:
        try:
            query = client.table("plants").select("*")
            if search:
                # sanitize and search across multiple relevant fields -> return full matching results
                q = search.replace('%', '')
                logger.debug(f"Performing Supabase or_ ilike search across plants with query: {q!r}")
                query = query.or_(
                    f"name.ilike.%{q}%,code.ilike.%{q}%,address.ilike.%{q}%,city.ilike.%{q}%,state.ilike.%{q}%,gstin.ilike.%{q}%"
                ).order("created_at", desc=True)

                # Execute primary query and examine response closely
                try:
                    response = query.execute()
                    resp_error = getattr(response, 'error', None)
                    resp_data = getattr(response, 'data', None)
                    if resp_error:
                        logger.warning(f"Supabase primary or_ search returned an error: {resp_error}")
                    results = resp_data or []
                    logger.debug(f"Primary or_ search returned {len(results)} rows for query: {q!r}")
                except Exception as e:
                    logger.warning(f"Primary or_ search raised exception: {e}")
                    results = []

                # If primary search returned nothing, attempt safer fallbacks to help diagnose frontend issues
                if not results:
                    fallback_results = []

                    try:
                        logger.debug(f"Fallback: trying ilike on name for query '%{q}%'")
                        r1 = client.table("plants").select("*").ilike("name", f"%{q}%").order("created_at", desc=True).execute()
                        if getattr(r1, 'error', None):
                            logger.warning(f"Fallback name ilike returned error: {getattr(r1, 'error')}")
                        fallback_results.extend(getattr(r1, 'data', []) or [])
                    except Exception as e:
                        logger.warning(f"Fallback name ilike failed: {e}")

                    try:
                        logger.debug(f"Fallback: trying ilike on code for query '%{q}%'")
                        r2 = client.table("plants").select("*").ilike("code", f"%{q}%").order("created_at", desc=True).execute()
                        if getattr(r2, 'error', None):
                            logger.warning(f"Fallback code ilike returned error: {getattr(r2, 'error')}")
                        fallback_results.extend(getattr(r2, 'data', []) or [])
                    except Exception as e:
                        logger.warning(f"Fallback code ilike failed: {e}")

                    # Try or_ with smaller clauses if still empty
                    if not fallback_results:
                        try:
                            logger.debug(f"Fallback: trying or_ on code/name for query: {q!r}")
                            r3 = client.table("plants").select("*").or_(f"code.ilike.%{q}%,name.ilike.%{q}%").order("created_at", desc=True).execute()
                            if getattr(r3, 'error', None):
                                logger.warning(f"Fallback or_ code/name returned error: {getattr(r3, 'error')}")
                            fallback_results.extend(getattr(r3, 'data', []) or [])
                        except Exception as e:
                            logger.warning(f"Fallback or_ code/name failed: {e}")

                    # Deduplicate by id
                    unique = {}
                    for p in fallback_results:
                        if p and p.get("id"):
                            unique[p["id"]] = p

                    results = list(unique.values())
                    logger.debug(f"Fallback searches returned {len(results)} unique rows for query: {q!r}")

                return results

            # No search -> limit to top `limit` results
            try:
                response = query.order("created_at", desc=True).limit(limit).execute()
                if getattr(response, 'error', None):
                    logger.warning(f"read_plants: Supabase returned error for latest query: {getattr(response, 'error')}")
                    # Fall back to in-memory list when DB returns an error
                    return memory_store.list_plants()[:limit]
                logger.debug(f"read_plants returning {len(getattr(response, 'data', []) or [])} latest plants (limit={limit})")
                return getattr(response, 'data', []) or []
            except Exception as e:
                logger.error(f"read_plants: exception while fetching latest plants: {e}")
                return memory_store.list_plants()[:limit]
        except Exception as e:
            logger.error(f"Supabase Fetch Error in read_plants (outer): {e}")
            # Final fallback
            if search:
                return [p for p in memory_store.list_plants() if any(search.lower() in (p.get(k) or "").lower() for k in ("name", "code", "address", "city", "state", "gstin"))]
            return memory_store.list_plants()[:limit]

    # In-memory fallback when Supabase client not initialized
    logger.debug("Supabase client not initialized; using in-memory fallback for read_plants")
    if search:
        return [p for p in memory_store.list_plants() if any(search.lower() in (p.get(k) or "").lower() for k in ("name", "code", "address", "city", "state", "gstin"))]

    return memory_store.list_plants()[:limit]


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

    try:
        contents = await file.read()
        try:
            text = contents.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = contents.decode('latin-1')
        csv_reader = csv.DictReader(io.StringIO(text))
        if csv_reader.fieldnames:
            csv_reader.fieldnames = [h.strip().lower() for h in csv_reader.fieldnames]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV: {str(e)}")
    
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
        try:
            # Deduplicate within the file and check against existing database records
            unique_by_code = {p["code"]: p for p in plants_to_insert}
            all_codes = list(unique_by_code.keys())
            
            existing_res = client.table("plants").select("code").in_("code", all_codes).execute()
            existing_codes = {r["code"] for r in (existing_res.data or [])}
            
            final_to_insert = [p for code, p in unique_by_code.items() if code not in existing_codes]
            
            if not final_to_insert:
                return []
                
            response = client.table("plants").insert(final_to_insert).execute()
            return response.data
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Database error during bulk upload: {str(e)}")
    elif not client:
        for p in plants_to_insert: memory_store.create_plant(p)
        return plants_to_insert
    return []


@router.get("/products", response_model=List[ProductOut])
def read_products(search: Optional[str] = None, limit: Optional[int] = None):
    client = get_supabase_client()

    if client:
        try:
            query = client.table("products").select("*")

            if search:
                q = search.replace('%', '')
                query = query.or_(
                    f"name.ilike.%{q}%,code.ilike.%{q}%,hsn_code.ilike.%{q}%,description.ilike.%{q}%"
                ).order("created_at", desc=True)

                response = query.execute()
                return response.data or []

            # No search
            if limit:
                response = query.order("created_at", desc=True).limit(limit).execute()
            else:
                response = query.order("created_at", desc=True).execute()

            return response.data or []

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Supabase Fetch Error: {str(e)}"
            )

    if search:
        return [
            p for p in memory_store.list_products()
            if any(
                search.lower() in (p.get(k) or "").lower()
                for k in ("name", "code", "hsn_code", "description")
            )
        ]

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

    try:
        contents = await file.read()
        try:
            text = contents.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = contents.decode('latin-1')
        csv_reader = csv.DictReader(io.StringIO(text))
        if csv_reader.fieldnames:
            csv_reader.fieldnames = [h.strip().lower() for h in csv_reader.fieldnames]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV: {str(e)}")
    
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
        try:
            # Deduplicate within the file and check against existing database records
            unique_by_code = {p["code"]: p for p in products_to_insert}
            all_codes = list(unique_by_code.keys())
            
            existing_res = client.table("products").select("code").in_("code", all_codes).execute()
            existing_codes = {r["code"] for r in (existing_res.data or [])}
            
            final_to_insert = [p for code, p in unique_by_code.items() if code not in existing_codes]
            
            if not final_to_insert:
                return []
                
            response = client.table("products").insert(final_to_insert).execute()
            return response.data
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Database error during bulk upload: {str(e)}")
    elif not client:
        for p in products_to_insert: memory_store.create_product(p)
        return products_to_insert
    return []


@router.get("/challans", response_model=List[ChallanOut])
def read_challans(search: Optional[str] = None, limit: int = 100000) -> List[Dict[str, Any]]:
    """Return latest `limit` challans by default. If `search` is provided, search entire table (no limit)."""
    client = get_supabase_client()
    if client:
        try:
            query = client.table("challans").select("*")
            if search:
                # search across common fields
                q = search.replace('%', '')
                query = query.or_(f"challan_number.ilike.%{q}%,from_plant_name.ilike.%{q}%,customer_name.ilike.%{q}%,order_ref.ilike.%{q}%,docket_no.ilike.%{q}%")
                response = query.order("created_at", desc=True).execute()
                return response.data or []

            # Default path: limited recent challans
            response = query.order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase Fetch Error: {str(e)}")
    # In-memory fallback
    if search:
        return [c for c in memory_store.list_challans() if search.lower() in (c.get("challan_number", "") or "").lower() or search.lower() in (c.get("from_plant_name", "") or "").lower() or search.lower() in (c.get("customer_name", "") or "").lower() or search.lower() in (c.get("order_ref", "") or "").lower() or search.lower() in (c.get("docket_no", "") or "").lower()]

    return memory_store.list_challans()[:limit]


def _create_challan_entry(challan_payload: Dict[str, Any]) -> Dict[str, Any]:
    
    client = get_supabase_client()
    if client:
        try:
            # 1. Resolve From Plant (by ID, Code, or Name)
            fp_id = challan_payload.get("from_plant_id")
            fp_name = challan_payload.get("from_plant_name")
            fp = None

            # normalize inputs
            fp_id_val = str(fp_id).strip() if fp_id else None
            fp_name_val = str(fp_name).strip() if fp_name else None

            if fp_id_val:
                logger.debug(f"Resolving from plant using identifier: '{fp_id_val}'")
                # Try ID (UUID)
                try:
                    uuid.UUID(fp_id_val)
                    res = client.table("plants").select("*").eq("id", fp_id_val).execute()
                    if res.data:
                        fp = res.data[0]
                        logger.debug(f"Found from plant by id: {fp.get('id')}")
                except Exception as e:
                    logger.debug(f"from plant id check not a UUID or lookup failed: {e}")

                # Try exact Code (case-sensitive)
                if not fp:
                    try:
                        logger.debug(f"Trying exact code match for from plant: '{fp_id_val}'")
                        res = client.table("plants").select("*").eq("code", fp_id_val).execute()
                        if res.data:
                            fp = res.data[0]
                            logger.debug(f"Found from plant by exact code: {fp.get('code')}")
                    except Exception as e:
                        logger.warning(f"Error during exact code lookup for from plant: {e}")

                # Try case-insensitive exact ilike (no wildcards)
                if not fp:
                    try:
                        logger.debug(f"Trying ilike (exact) code for from plant: '{fp_id_val}'")
                        res = client.table("plants").select("*").ilike("code", fp_id_val).execute()
                        if res.data:
                            fp = res.data[0]
                            logger.debug(f"Found from plant by ilike exact code: {fp.get('code')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike exact code lookup for from plant: {e}")

                # Try ilike with wildcards
                if not fp:
                    try:
                        logger.debug(f"Trying ilike wildcard code for from plant: '%{fp_id_val}%'")
                        res = client.table("plants").select("*").ilike("code", f"%{fp_id_val}%").execute()
                        if res.data:
                            fp = res.data[0]
                            logger.debug(f"Found from plant by ilike wildcard code: {fp.get('code')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike wildcard code lookup for from plant: {e}")

                # Final fallback: try combined ilike on code and name using Supabase 'or_' which is more reliable
                if not fp:
                    try:
                        q = fp_id_val.replace('%', '')
                        logger.debug(f"Fallback search for from plant using or_ ilike with query: '{q}'")
                        res = client.table("plants").select("*").or_(f"code.ilike.%{q}%,name.ilike.%{q}%").limit(1).execute()
                        if res.data:
                            fp = res.data[0]
                            logger.debug(f"Found from plant by fallback or_ ilike: {fp.get('code')} / {fp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Fallback or_ ilike search for from plant failed: {e}")

            # If not found by id/code, try by provided name
            if not fp and fp_name_val:
                logger.debug(f"Resolving from plant by name: '{fp_name_val}'")
                try:
                    res = client.table("plants").select("*").eq("name", fp_name_val).execute()
                    if res.data:
                        fp = res.data[0]
                        logger.debug(f"Found from plant by exact name: {fp.get('name')}")
                except Exception as e:
                    logger.warning(f"Error during exact name lookup for from plant: {e}")

                if not fp:
                    try:
                        logger.debug(f"Trying ilike (exact) name for from plant: '{fp_name_val}'")
                        res = client.table("plants").select("*").ilike("name", fp_name_val).execute()
                        if res.data:
                            fp = res.data[0]
                            logger.debug(f"Found from plant by ilike exact name: {fp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike exact name lookup for from plant: {e}")

                if not fp:
                    try:
                        logger.debug(f"Trying ilike wildcard name for from plant: '%{fp_name_val}%'")
                        res = client.table("plants").select("*").ilike("name", f"%{fp_name_val}%").execute()
                        if res.data:
                            fp = res.data[0]
                            logger.debug(f"Found from plant by ilike wildcard name: {fp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike wildcard name lookup for from plant: {e}")

                # Fallback using or_ across code/name when name-based attempts fail
                if not fp:
                    try:
                        qn = fp_name_val.replace('%','')
                        logger.debug(f"Fallback search for from plant by name using or_ ilike with query: '{qn}'")
                        res = client.table("plants").select("*").or_(f"code.ilike.%{qn}%,name.ilike.%{qn}%").limit(1).execute()
                        if res.data:
                            fp = res.data[0]
                            logger.debug(f"Found from plant by fallback or_ ilike (name): {fp.get('code')} / {fp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Fallback or_ ilike search for from plant by name failed: {e}")

            if fp:
                challan_payload["from_plant_id"] = fp["id"]
                challan_payload["from_plant_name"] = fp.get("name")
                challan_payload["from_plant_address"] = fp.get("address")
                challan_payload["from_plant_state"] = fp.get("state")
                challan_payload["from_plant_city"] = fp.get("city")
                challan_payload["from_plant_pincode"] = fp.get("pincode")
                challan_payload["from_plant_gstin"] = fp.get("gstin")
                challan_payload["from_plant_branch"] = fp.get("name")

            # 2. Resolve To Plant / Customer (by ID, Code, or Name)
            tp_id = challan_payload.get("plant_id")
            tp_name = challan_payload.get("customer_name")
            tp = None

            tp_id_val = str(tp_id).strip() if tp_id else None
            tp_name_val = str(tp_name).strip() if tp_name else None

            if tp_id_val:
                logger.debug(f"Resolving to plant using identifier: '{tp_id_val}'")
                try:
                    uuid.UUID(tp_id_val)
                    res = client.table("plants").select("*").eq("id", tp_id_val).execute()
                    if res.data:
                        tp = res.data[0]
                        logger.debug(f"Found to plant by id: {tp.get('id')}")
                except Exception as e:
                    logger.debug(f"to plant id check not a UUID or lookup failed: {e}")

                if not tp:
                    try:
                        logger.debug(f"Trying exact code match for to plant: '{tp_id_val}'")
                        res = client.table("plants").select("*").eq("code", tp_id_val).execute()
                        if res.data:
                            tp = res.data[0]
                            logger.debug(f"Found to plant by exact code: {tp.get('code')}")
                    except Exception as e:
                        logger.warning(f"Error during exact code lookup for to plant: {e}")

                if not tp:
                    try:
                        logger.debug(f"Trying ilike (exact) code for to plant: '{tp_id_val}'")
                        res = client.table("plants").select("*").ilike("code", tp_id_val).execute()
                        if res.data:
                            tp = res.data[0]
                            logger.debug(f"Found to plant by ilike exact code: {tp.get('code')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike exact code lookup for to plant: {e}")

                if not tp:
                    try:
                        logger.debug(f"Trying ilike wildcard code for to plant: '%{tp_id_val}%'")
                        res = client.table("plants").select("*").ilike("code", f"%{tp_id_val}%").execute()
                        if res.data:
                            tp = res.data[0]
                            logger.debug(f"Found to plant by ilike wildcard code: {tp.get('code')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike wildcard code lookup for to plant: {e}")

                # Fallback: or_ ilike across code and name
                if not tp:
                    try:
                        qt = tp_id_val.replace('%','')
                        logger.debug(f"Fallback search for to plant using or_ ilike with query: '{qt}'")
                        res = client.table("plants").select("*").or_(f"code.ilike.%{qt}%,name.ilike.%{qt}%").limit(1).execute()
                        if res.data:
                            tp = res.data[0]
                            logger.debug(f"Found to plant by fallback or_ ilike: {tp.get('code')} / {tp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Fallback or_ ilike search for to plant failed: {e}")

            if not tp and tp_name_val:
                logger.debug(f"Resolving to plant by name: '{tp_name_val}'")
                try:
                    res = client.table("plants").select("*").eq("name", tp_name_val).execute()
                    if res.data:
                        tp = res.data[0]
                        logger.debug(f"Found to plant by exact name: {tp.get('name')}")
                except Exception as e:
                    logger.warning(f"Error during exact name lookup for to plant: {e}")

                if not tp:
                    try:
                        logger.debug(f"Trying ilike (exact) name for to plant: '{tp_name_val}'")
                        res = client.table("plants").select("*").ilike("name", tp_name_val).execute()
                        if res.data:
                            tp = res.data[0]
                            logger.debug(f"Found to plant by ilike exact name: {tp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike exact name lookup for to plant: {e}")

                if not tp:
                    try:
                        logger.debug(f"Trying ilike wildcard name for to plant: '%{tp_name_val}%'")
                        res = client.table("plants").select("*").ilike("name", f"%{tp_name_val}%").execute()
                        if res.data:
                            tp = res.data[0]
                            logger.debug(f"Found to plant by ilike wildcard name: {tp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Error during ilike wildcard name lookup for to plant: {e}")

                if not tp:
                    try:
                        qtn = tp_name_val.replace('%','')
                        logger.debug(f"Fallback search for to plant by name using or_ ilike with query: '{qtn}'")
                        res = client.table("plants").select("*").or_(f"code.ilike.%{qtn}%,name.ilike.%{qtn}%").limit(1).execute()
                        if res.data:
                            tp = res.data[0]
                            logger.debug(f"Found to plant by fallback or_ ilike (name): {tp.get('code')} / {tp.get('name')}")
                    except Exception as e:
                        logger.warning(f"Fallback or_ ilike search for to plant by name failed: {e}")

            if tp:
                challan_payload["plant_id"] = tp["id"]
                challan_payload["customer_name"] = tp.get("name")
                challan_payload["customer_address"] = tp.get("address")
                challan_payload["customer_state"] = tp.get("state")
                challan_payload["customer_city"] = tp.get("city")
                challan_payload["customer_pincode"] = tp.get("pincode")
                challan_payload["customer_gstin"] = tp.get("gstin")
        except Exception as e:
            logger.warning(f"Failed to auto-populate plant details: {str(e)}")

    # Auto-generate challan number if not provided
    if not challan_payload.get("challan_number"):
        next_num_data = get_next_challan_number()
        challan_payload["challan_number"] = next_num_data["next_number"]

    # Ensure challan_date is set for single challan creation. If caller provided one, keep it;
    # otherwise use India local date (IST) so records align with uploader's local calendar date.
    if not challan_payload.get("challan_date"):
        ist = timezone(timedelta(hours=5, minutes=30))
        challan_payload["challan_date"] = datetime.now(ist).date().isoformat()
    challan_payload["id"] = str(uuid.uuid4())
    challan_payload["created_at"] = now_iso()
    challan_payload["total_amount"] = round(sum(item["quantity"] * item["rate"] for item in challan_payload.get("items", [])), 2)
    # Ensure cancelled metadata exists and defaults to False so cancelled numbers are retained
    challan_payload.setdefault("cancelled", False)
    challan_payload.setdefault("cancelled_at", None)
    challan_payload.setdefault("cancel_reason", None)

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
def delete_challan(id: str, reason: Optional[str] = None):
    # Soft-cancel a challan instead of deleting it so we retain its number and history.
    client = get_supabase_client()
    cancel_meta = {"cancelled": True, "cancelled_at": now_iso(), "cancel_reason": reason}
    if client:
        try:
            response = client.table("challans").update(cancel_meta).eq("id", id).execute()
            # If Supabase returns the updated record, return it for frontend sync
            if response and getattr(response, 'data', None):
                return response.data[0]
            return {"status": "success", "cancelled": True}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cancel Error: {str(e)}")

    # In-memory store: mark the challan as cancelled and persist reason
    found = False
    updated = None
    for c in memory_store.challans:
        if c.get("id") == id:
            c.update({"cancelled": True, "cancelled_at": now_iso(), "cancel_reason": reason})
            updated = c
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Challan not found")

    return updated


@router.post("/challans/bulk-delete")
def bulk_delete_challans(payload: BulkDeleteRequest):
    # Bulk-cancel challans instead of removing them
    client = get_supabase_client()
    cancel_meta = {"cancelled": True, "cancelled_at": now_iso()}
    if client:
        try:
            client.table("challans").update(cancel_meta).in_("id", payload.ids).execute()
            return {"status": "success", "count": len(payload.ids)}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Bulk Cancel Error: {str(e)}")

    ids_to_cancel = set(payload.ids)
    count = 0
    for c in memory_store.challans:
        if c.get("id") in ids_to_cancel and not c.get("cancelled"):
            c.update(cancel_meta)
            count += 1
    return {"status": "success", "count": count}


@router.post("/challans", response_model=ChallanOut, tags=["Challans"])
def create_challan(payload: ChallanCreate) -> Dict[str, Any]:
    return _create_challan_entry(payload.model_dump())


# Helper to fetch plant by code
@router.get("/plants/code/{code}", tags=["Plants"])
def get_plant_by_code(code: str) -> Dict[str, Any]:
    """Fetches full plant details by its code."""
    client = get_supabase_client()
    if not client:
        raise HTTPException(status_code=500, detail="Database client not initialized.")
    
    response = client.table("plants").select("*").eq("code", code).execute()
    plant = (response.data or [None])[0]
    
    if not plant:
        raise HTTPException(status_code=404, detail=f"Plant with code '{code}' not found.")
    
    return plant


# Helper to fetch product by code (SKU)
def _get_product_by_code(client, code: str) -> Optional[Dict[str, Any]]:
    response = client.table("products").select("*").eq("code", code).execute()
    return (response.data or [None])[0]


@router.post("/challans/bulk-upload", response_model=List[ChallanOut])
async def bulk_upload_challans(
    file: UploadFile = File(...),
    x_user: Optional[str] = Header(None),
    x_challan_date: Optional[str] = Header(None, alias="x-challan-date"),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    try:
        contents = await file.read()
        try:
            text = contents.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = contents.decode('latin-1')
        csv_reader = csv.reader(io.StringIO(text))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read CSV: {str(e)}")
    
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

    # Determine uploader identity (prefer header provided by frontend / current user)
    uploader = x_user or "Bulk Upload"

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
            challan_date=datetime.now(ZoneInfo("Asia/Kolkata")).isoformat().split('T')[0], # Use current date for bulk upload
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
            vehicle_no=None,
            created_by=uploader
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
    # Include a 'Cancelled' column so reports reflect cancellation status
    writer.writerow(["Challan No", "Date", "From Plant", "To Plant", "SKU", "Item Name", "UOM", "Qty", "Rate", "Amount", "Order Ref", "Docket No", "Reason for DC", "Cancelled", "Created By"])
     
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
                str(bool(c.get("cancelled", False))),
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

    # Fetch company names for a more professional layout, as requested.
    if client:
        try:
            from_plant_res = client.table("plants").select("name").eq("id", challan.get("from_plant_id")).maybe_single().execute()
            to_plant_res = client.table("plants").select("name").eq("id", challan.get("plant_id")).maybe_single().execute()

            # The company name is assumed to be "SCHOOL SHOP PRIVATE LIMITED" for all plants.
            # The plant-specific name is already in the challan object itself.
            challan["from_company_name"] = "SCHOOL SHOP PRIVATE LIMITED"
            challan["to_company_name"] = "SCHOOL SHOP PRIVATE LIMITED"

            # We can keep the specific plant names from the challan record itself.
            # This avoids issues if a plant name was changed after the challan was created.
            # challan["from_plant_name"] is already present.
            # challan["customer_name"] is the to_plant_name.

        except Exception as e:
            logger.error(f"PDF Gen: Failed to fetch plant details for challan {challan_id}: {e}")
            # Fallback to existing names if DB query fails
            challan["from_company_name"] = challan.get("from_plant_name")
            challan["to_company_name"] = challan.get("customer_name")
            

    pdf_bytes = build_challan_pdf(challan)
    challan_number = challan.get("challan_number", challan_id)
    customer_name =  challan.get("customer_name", challan_id)
    sender_name = challan.get("from_plant_name", challan_id)
    
    safe_customer_name = str(customer_name).replace("\xa0", " ").strip()
    safe_sender_name = str(sender_name).replace("\xa0", " ").strip()
    
    file_name = f"{safe_sender_name}_ to_ {safe_customer_name}_{challan_number}.pdf"
    
    headers = {"Content-Disposition": f'attachment; filename="{file_name}"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

def create_sspl_logo():
    """Creates the SSPL logo as a ReportLab Drawing object."""
    # Original SVG size: 260 x 55. Target width: 140.
    scale = 140 / 260.0
    h = 55 * scale
    w = 140
    
    d = Drawing(w, h)
    g = Group()
    g.scale(scale, scale)
    
    # SVG y is from top, RL y is from bottom. Canvas height = 55.
    # Book Icon Left Page
    p1 = Path(fillColor=HexColor("#F97316"), strokeColor=None)
    p1.moveTo(8, 55-15)
    p1.lineTo(22, 55-11)
    p1.lineTo(22, 55-39)
    p1.lineTo(8, 55-43)
    p1.closePath()
    g.add(p1)
    
    # Book Icon Right Page
    p2 = Path(fillColor=HexColor("#FB923C"), strokeColor=None)
    p2.moveTo(22, 55-11)
    p2.lineTo(36, 55-15)
    p2.lineTo(36, 55-43)
    p2.lineTo(22, 55-39)
    p2.closePath()
    g.add(p2)
    
    # Middle line
    g.add(Line(22, 55-11, 22, 55-39, strokeColor=HexColor("#FFFFFF"), strokeWidth=1.5))
    
    # SSPL Text
    g.add(String(48, 55-26, "SSPL", fontName="Helvetica-Bold", fontSize=22, fillColor=HexColor("#F97316")))
    
    # Company Name Text
    g.add(String(48, 55-43, "SCHOOL SHOP PRIVATE LIMITED", fontName="Helvetica", fontSize=10, fillColor=HexColor("#666666")))

    d.add(g)
    return d


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
    
    # Logo (Top Left)
    story.append(create_sspl_logo())
    story.append(Spacer(1, 5 * mm))
    
    
    # Header
    story.append(Paragraph("DELIVERY CHALLAN", header_style))
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
        [
            Paragraph(
                f"{challan.get('from_company_name', challan.get('from_plant_name', ''))}",
                table_value_style
            ),
            "",
            Paragraph(
                f"{challan.get('to_company_name', challan.get('customer_name', ''))}",
                table_value_style
            ), ""],
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
        ('LEFTPADDING', (0,0), (-1, -1), 2),
        ('RIGHTPADDING', (0,0), (-1, -1), 2),
    ]))
    story.append(t_addr)
    story.append(Spacer(1, 5 * mm))

    # Items Table
    item_rows = [["S.No", "Product Code", "Item Name", "UOM", "QTY.", "Rate", "Amount"]]
    total_qty = 0
    for idx, item in enumerate(challan.get("items", []), 1):
        qty = item.get("quantity", 0)
        total_qty += qty
        
        product_name_text = item.get("product_name","")
        product_name_paragraph = Paragraph(product_name_text,cell_text_style)
        
        
        item_rows.append([
            str(idx),
            item.get("product_code", ""),
            product_name_paragraph,
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

def get_next_challan_number() -> Dict[str, str]:
    """Compute the next challan number.

    Strategy:
    - Try to fetch the most recently created challan (by created_at) from the DB (Supabase) or in-memory store.
    - If a last challan_number exists and contains a trailing integer, increment that integer preserving zero-padding.
    - If no numeric suffix is found, append "-1" to the last number.
    - If no previous challan exists, default to `DC-0001`.
    - Always return a dict {"next_number": <value>} to match existing call sites.
    """
    prefix_default = "DC-"
    client = get_supabase_client()
    try:
        last_number = None
        if client:
            try:
                res = client.table("challans").select("challan_number").order("created_at", desc=True).limit(1).execute()
                last = (res.data or [None])[0]
                last_number = last.get("challan_number") if last else None
            except Exception as e:
                logger.warning(f"get_next_challan_number: failed DB lookup: {e}")
                last_number = None
        else:
            # in-memory fallback
            items = memory_store.list_challans()
            if items:
                last_number = items[0].get("challan_number")

        if last_number:
            # find trailing numeric part
            m = re.search(r"(\d+)$", str(last_number))
            if m:
                num_part = m.group(1)
                next_num_val = int(num_part) + 1
                # preserve padding
                padded = str(next_num_val).zfill(len(num_part))
                next_number = str(last_number[: m.start(1)]) + padded
            else:
                # if no trailing digits, append a standard suffix
                next_number = f"{last_number}-1"
        else:
            next_number = f"{prefix_default}0001"

        return {"next_number": next_number}
    except Exception as e:
        logger.error(f"get_next_challan_number: unexpected error: {e}")
        # Fallback: timestamp-based unique number
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return {"next_number": f"{prefix_default}{ts}"}


@app.get("/api/health")
async def api_health_check():
    """Direct health check to verify Vercel routing."""
    logger.info("Direct health check endpoint hit via /api/health (app level)")
    return {"status": "ok", "source": "direct_app_route"}


# Mount router under /api
app.include_router(router, prefix="/api", tags=["API"])

@app.on_event("startup")
async def startup_event():
    logger.info("--- Vercel Backend Startup ---")
    # Log presence of environment variables (do not log the actual keys)
    logger.info(f"ENV CHECK: SUPABASE_URL: {'FOUND' if SUPABASE_URL else 'MISSING'}")
    logger.info(f"ENV CHECK: SUPABASE_SERVICE_ROLE_KEY: {'FOUND' if SUPABASE_SERVICE_ROLE_KEY else 'MISSING'}")
    logger.info(f"ENV CHECK: SUPABASE_KEY (Anon): {'FOUND' if SUPABASE_KEY else 'MISSING'}")
    
    client = get_supabase_client()
    if client:
        logger.info(f"Supabase Client: Initialized successfully. Target URL: {SUPABASE_URL}")
        try:
            # Perform a lightweight check to surface connection errors in deployment logs
            client.table("users").select("id").limit(1).execute()
            logger.info("Database Connection: SUCCESS - Able to query 'users' table.")
        except Exception as e:
            logger.error(f"Database Connection: FAILED - {str(e)}")
    else:
        logger.error("Supabase Client: FAILED - Missing URL or API Key. Check Vercel Environment Variables.")
    logger.info("--- Startup Event Complete ---")
@router.get("/__debug")
async def debug_request(request: Request):
    """Return minimal request scope info to help diagnose path rewriting in Vercel."""
    scope = request.scope.copy()
    raw_path = scope.get("raw_path")
    try:
        raw_path_display = raw_path.decode() if isinstance(raw_path, (bytes, bytearray)) else str(raw_path)
    except Exception:
        raw_path_display = repr(raw_path)

    info = {
        "url_path": request.url.path,
        "full_url": str(request.url),
        "scope_path": scope.get("path"),
        "root_path": scope.get("root_path"),
        "raw_path": raw_path_display,
        "method": scope.get("method"),
        "headers": {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in scope.get("headers", [])},
    }
    logger.info(f"Debug request info: {info}")
    return info


# Vercel Python runtime requires a top-level entrypoint named `app`, `application`, or `handler`.
# `app` is already defined above. Export aliases to ensure the runtime detects an ASGI app.
application = app
handler = app

# Endpoint: Resolve a single plant by id/code/name
@router.get("/plants/resolve", tags=["Plants"]) 
def resolve_plant(q: Optional[str] = None, term: Optional[str] = None):
    """Return the best matching plant for a search term. Accepts either `q` or `term` as the query param.
    Enhancements: if the term contains a parenthesized code (e.g. 'SSPL EKART BLR (2717)'), try the inner code first.
    Tries (in order): UUID id, extracted code, exact code, ilike exact code, ilike wildcard code, exact name, ilike exact name, ilike wildcard name, final or_ across code/name.
    Falls back to in-memory store when Supabase is not available.
    """
    raw = (q or term or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Query parameter `q` or `term` is required.")

    # If term looks like 'Name (CODE)' extract CODE as high-priority candidate
    candidates = [raw]
    try:
        m = re.search(r"\(([^)]+)\)", raw)
        if m:
            inner = m.group(1).strip()
            if inner and inner not in candidates:
                candidates.insert(0, inner)
    except Exception:
        pass

    client = get_supabase_client()
    q_clean = raw.replace('%', '')

    def _maybe_single(res):
        try:
            return (getattr(res, 'data', None) or [None])[0]
        except Exception:
            return None

    # If DB available, try robust lookups using candidates (prioritise extracted code)
    if client:
        try:
            # 1) Try UUID with original raw input
            try:
                uuid.UUID(raw)
                res = client.table("plants").select("*").eq("id", raw).maybe_single().execute()
                plant = _maybe_single(res)
                if plant:
                    logger.debug(f"resolve_plant: matched by id {plant.get('id')}")
                    return plant
            except Exception:
                pass

            # For each candidate, try code-based lookups first
            for cand in candidates:
                if not cand:
                    continue
                cand_clean = cand.replace('%', '')
                # exact code
                try:
                    res = client.table("plants").select("*").eq("code", cand).maybe_single().execute()
                    plant = _maybe_single(res)
                    if plant:
                        logger.debug(f"resolve_plant: matched by exact code {plant.get('code')} (candidate={cand})")
                        return plant
                except Exception:
                    pass

                # ilike exact code
                try:
                    res = client.table("plants").select("*").ilike("code", cand).maybe_single().execute()
                    plant = _maybe_single(res)
                    if plant:
                        logger.debug(f"resolve_plant: matched by ilike exact code {plant.get('code')} (candidate={cand})")
                        return plant
                except Exception:
                    pass

                # ilike wildcard code
                try:
                    res = client.table("plants").select("*").ilike("code", f"%{cand_clean}%").limit(1).execute()
                    plant = _maybe_single(res)
                    if plant:
                        logger.debug(f"resolve_plant: matched by ilike wildcard code {plant.get('code')} (candidate={cand})")
                        return plant
                except Exception:
                    pass

            # Name-based lookups (use original raw and cleaned q_clean)
            try:
                res = client.table("plants").select("*").eq("name", raw).maybe_single().execute()
                plant = _maybe_single(res)
                if plant:
                    logger.debug(f"resolve_plant: matched by exact name {plant.get('name')}")
                    return plant
            except Exception:
                pass

            try:
                res = client.table("plants").select("*").ilike("name", raw).maybe_single().execute()
                plant = _maybe_single(res)
                if plant:
                    logger.debug(f"resolve_plant: matched by ilike exact name {plant.get('name')}")
                    return plant
            except Exception:
                pass

            try:
                res = client.table("plants").select("*").ilike("name", f"%{q_clean}%").limit(1).execute()
                plant = _maybe_single(res)
                if plant:
                    logger.debug(f"resolve_plant: matched by ilike wildcard name {plant.get('name')}")
                    return plant
            except Exception:
                pass

            # final or_ fallback using cleaned raw
            try:
                res = client.table("plants").select("*").or_(f"code.ilike.%{q_clean}%,name.ilike.%{q_clean}%").limit(1).execute()
                plant = _maybe_single(res)
                if plant:
                    logger.debug(f"resolve_plant: matched by fallback or_ {plant.get('code')} / {plant.get('name')}")
                    return plant
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"resolve_plant: Supabase lookup failed: {e}")

    # In-memory fallback (mirror the same candidate priority)
    try:
        ql = raw.lower()
        for cand in candidates:
            for p in memory_store.list_plants():
                if p.get("id") == cand or p.get("code") == cand:
                    return p
        for p in memory_store.list_plants():
            if ql == (p.get("code") or "").lower() or ql == (p.get("name") or "").lower():
                return p
        for p in memory_store.list_plants():
            if ql in (p.get("code") or "").lower() or ql in (p.get("name") or "").lower():
                return p
    except Exception as e:
        logger.warning(f"resolve_plant: in-memory lookup failed: {e}")

    raise HTTPException(status_code=404, detail=f"No plant matched the query: {raw}")
