from __future__ import annotations

import io
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

app = FastAPI(title="Delivery Challan API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlantCreate(BaseModel):
    name: str
    code: str
    address: Optional[str] = None
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
    rate: float = 0.0
    description: Optional[str] = None


class ProductOut(ProductCreate):
    id: str
    created_at: Optional[str] = None


class ChallanItem(BaseModel):
    product_id: str
    product_name: str
    quantity: float
    rate: float
    amount: float


class ChallanCreate(BaseModel):
    challan_number: str
    challan_date: str
    plant_id: str
    customer_name: str
    customer_address: Optional[str] = None
    vehicle_no: Optional[str] = None
    lr_no: Optional[str] = None
    items: List[ChallanItem]
    notes: Optional[str] = None


class ChallanOut(ChallanCreate):
    id: str
    total_amount: float
    created_at: Optional[str] = None


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
    if SUPABASE_URL and SUPABASE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(record)
    payload.setdefault("created_at", now_iso())
    return payload


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/plants", response_model=List[PlantOut])
def read_plants() -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if client:
        try:
            response = client.table("plants").select("*").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase Fetch Error: {str(e)}")
    return memory_store.list_plants()


@app.post("/plants", response_model=PlantOut)
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


@app.get("/products", response_model=List[ProductOut])
def read_products() -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if client:
        try:
            response = client.table("products").select("*").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase Fetch Error: {str(e)}")
    return memory_store.list_products()


@app.post("/products", response_model=ProductOut)
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


@app.get("/challans", response_model=List[ChallanOut])
def read_challans() -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if client:
        try:
            response = client.table("challans").select("*").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Supabase Fetch Error: {str(e)}")
    return memory_store.list_challans()


@app.post("/challans", response_model=ChallanOut)
def create_challan(payload: ChallanCreate) -> Dict[str, Any]:
    challan_payload = payload.model_dump()
    challan_payload["id"] = str(uuid.uuid4())
    challan_payload["created_at"] = now_iso()
    challan_payload["total_amount"] = round(sum(item.quantity * item.rate for item in payload.items), 2)
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


@app.get("/challans/{challan_id}/pdf")
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
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=12)
    normal_style = styles["BodyText"]

    story = []
    story.append(Paragraph("Delivery Challan", title_style))
    story.append(Paragraph(f"Challan No: {challan.get('challan_number', '')}", normal_style))
    story.append(Paragraph(f"Date: {challan.get('challan_date', '')}", normal_style))
    story.append(Paragraph(f"Customer: {challan.get('customer_name', '')}", normal_style))
    story.append(Paragraph(f"Plant ID: {challan.get('plant_id', '')}", normal_style))
    story.append(Spacer(1, 6 * mm))

    item_rows = [["Product", "Qty", "Rate", "Amount"]]
    for item in challan.get("items", []):
        item_rows.append([
            item.get("product_name", ""),
            str(item.get("quantity", 0)),
            str(item.get("rate", 0)),
            str(item.get("amount", 0)),
        ])

    table = Table(item_rows, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.beige]),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Total Amount: {challan.get('total_amount', 0)}", ParagraphStyle("Total", parent=styles["Heading2"])))
    story.append(Paragraph(f"Notes: {challan.get('notes', '')}", normal_style))

    doc.build(story)
    return buffer.getvalue()
