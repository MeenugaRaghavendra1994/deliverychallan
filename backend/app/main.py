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


@app.get("/challans/next-number")
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


@app.post("/challans", response_model=ChallanOut)
def create_challan(payload: ChallanCreate) -> Dict[str, Any]:
    challan_payload = payload.model_dump()
    
    # Auto-generate challan number if not provided
    if not challan_payload.get("challan_number"):
        next_num_data = get_next_challan_number()
        challan_payload["challan_number"] = next_num_data["next_number"]

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


@app.post("/challans", response_model=ChallanOut)
def create_challan(payload: ChallanCreate) -> Dict[str, Any]:
    return _create_challan_entry(payload)


# Helper to fetch plant by code
def _get_plant_by_code(client, code: str) -> Optional[Dict[str, Any]]:
    response = client.table("plants").select("*").eq("code", code).execute()
    return (response.data or [None])[0]

# Helper to fetch product by code (SKU)
def _get_product_by_code(client, code: str) -> Optional[Dict[str, Any]]:
    response = client.table("products").select("*").eq("code", code).execute()
    return (response.data or [None])[0]


@app.post("/challans/bulk-upload", response_model=List[ChallanOut])
async def bulk_upload_challans(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    csv_reader = csv.reader(io.StringIO(contents.decode('utf-8')))
    
    try:
        header = next(csv_reader) # Skip header row
    except StopIteration:
        raise HTTPException(status_code=400, detail="Uploaded CSV file is empty.")

    expected_header = ["from_plant_code", "to_plant_code", "sku", "item_name", "quantity", "rate"]
    if [h.strip().lower() for h in header] != expected_header:
        raise HTTPException(status_code=400, detail=f"CSV header must be exactly: {', '.join(expected_header)}")

    challans_grouped_by_plants: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
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
                "rate": rate
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
        
        challans_grouped_by_plants[(from_plant["id"], to_plant["id"])].append(challan_item.model_dump())

    if processing_errors:
        raise HTTPException(status_code=400, detail={"message": "Data validation errors", "errors": processing_errors})

    created_challans = []
    for (from_plant_id, to_plant_id), items_data in challans_grouped_by_plants.items():
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
            notes="Bulk Upload Challan",
            vehicle_no=None,
            lr_no=None
        )
        
        try:
            created_challan = _create_challan_entry(challan_payload)
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
    story.append(Paragraph("BANGALORE - 562162", sub_header_style))
    story.append(Paragraph("STOCK TRANSFER NOTE", ParagraphStyle("Note", fontSize=11, leading=13, alignment=1, fontName="Helvetica-Bold", spaceAfter=10)))

    # Date and Challan No Row
    date_info = [
        [Paragraph(f"Date: {challan.get('challan_date')}", table_label_style), "", Paragraph(str(challan.get('challan_number')), header_style)]
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
        [Paragraph(f"Branch: {challan.get('from_plant_branch', '')}", table_value_style), "", Paragraph(f"Branch Name: {challan.get('customer_name', '')}", table_value_style), ""],
        [Paragraph(f"Order Ref: {challan.get('notes', '')}", table_value_style), "", Paragraph(f"Docket No: {challan.get('lr_no', '')}", table_value_style), ""]
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

    doc.build(story)
    return buffer.getvalue()
