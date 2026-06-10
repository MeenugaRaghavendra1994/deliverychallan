import { useEffect, useState } from "react";

// Basic styling to replace Excel feel with a modern UI
const styles = `
  :root {
    --primary: #0f766e;
    --primary-hover: #0d9488;
    --bg: #f8fafc;
    --card: #ffffff;
    --text: #1e293b;
    --border: #e2e8f0;
  }
  body { 
    font-family: 'Inter', system-ui, sans-serif; 
    background: var(--bg); 
    color: var(--text); 
    margin: 0; 
    line-height: 1.5;
  }
  .app-shell { max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem; }
  .hero-card { 
    background: var(--primary); 
    color: white; 
    padding: 2.5rem; 
    border-radius: 16px; 
    margin-bottom: 2rem;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
  }
  .hero-card h1 { margin: 0.5rem 0; font-size: 1.8rem; }
  .eyebrow { text-transform: uppercase; font-weight: 700; font-size: 0.8rem; opacity: 0.9; letter-spacing: 0.05em; }
  .status-pill { 
    display: inline-block; 
    background: rgba(255,255,255,0.2); 
    padding: 0.4rem 1rem; 
    border-radius: 99px; 
    font-size: 0.85rem; 
    margin-top: 1rem;
  }
  .card { 
    background: var(--card); 
    border: 1px solid var(--border); 
    padding: 1.5rem; 
    border-radius: 12px; 
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); 
    margin-bottom: 1.5rem; 
  }
  .grid { display: grid; grid-template-columns: 1fr 1.5fr; gap: 1.5rem; }
  .stack { display: flex; flex-direction: column; gap: 0.8rem; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; }
  .item-row { 
    display: grid; 
    grid-template-columns: 2fr 1fr 1fr 1fr; 
    gap: 0.8rem; 
    align-items: center; 
    padding: 0.5rem 0;
  }
  input, select, textarea { 
    padding: 0.7rem; 
    border: 1px solid var(--border); 
    border-radius: 8px; 
    font-size: 0.95rem; 
    width: 100%;
    box-sizing: border-box;
  }
  button { 
    background: var(--primary); 
    color: white; 
    border: none; 
    padding: 0.7rem 1.2rem;
    border-radius: 8px; 
    cursor: pointer; 
    font-weight: 600; 
    transition: background 0.2s;
  }
  .helper-text { font-size: 0.9rem; opacity: 0.8; margin-top: 0.5rem; }
  .list-row { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 0; border-bottom: 1px solid var(--border); }
  .list-row:last-child { border-bottom: none; }
  button:hover { background: var(--primary-hover); }
  button.secondary { background: white; border: 1px solid var(--primary); color: var(--primary); }
`;

const API_BASE = "/api";

const emptyPlantForm = {
  name: "",
  code: "",
  address: "",
  contact_person: "",
  phone: "",
  status: "Active",
};

const emptyProductForm = {
  name: "",
  code: "",
  hsn_code: "",
  unit: "Nos",
  rate: "",
  description: "",
};

const emptyItem = () => ({
  product_id: "",
  product_name: "",
  quantity: "",
  rate: "",
  amount: 0,
});

export default function App() {
  const [plants, setPlants] = useState([]);
  const [products, setProducts] = useState([]);
  const [challans, setChallans] = useState([]);
  const [plantForm, setPlantForm] = useState(emptyPlantForm);
  const [productForm, setProductForm] = useState(emptyProductForm);
  const [challanForm, setChallanForm] = useState({
    challan_number: "",
    challan_date: new Date().toISOString().slice(0, 10),
    plant_id: "",
    customer_name: "",
    customer_address: "",
    vehicle_no: "",
    lr_no: "",
    notes: "",
  });
  const [itemRows, setItemRows] = useState([emptyItem()]);
  const [status, setStatus] = useState("Ready to create delivery challans.");

  const requestJson = async (path, options = {}) => {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    return response.json();
  };

  const loadPlants = async () => {
    try {
      const data = await requestJson("/plants");
      setPlants(data);
    } catch (error) {
      setStatus(error.message);
    }
  };

  const loadProducts = async () => {
    try {
      const data = await requestJson("/products");
      setProducts(data);
    } catch (error) {
      setStatus(error.message);
    }
  };

  const loadChallans = async () => {
    try {
      const data = await requestJson("/challans");
      setChallans(data);
    } catch (error) {
      setStatus(error.message);
    }
  };

  useEffect(() => {
    loadPlants();
    loadProducts();
    loadChallans();
  }, []);

  const handlePlantSubmit = async (event) => {
    event.preventDefault();
    try {
      const plant = await requestJson("/plants", {
        method: "POST",
        body: JSON.stringify(plantForm),
      });
      setPlants((current) => [plant, ...current]);
      setPlantForm(emptyPlantForm);
      setStatus(`Plant ${plant.name} saved.`);
    } catch (error) {
      setStatus(error.message);
    }
  };

  const handleProductSubmit = async (event) => {
    event.preventDefault();
    try {
      const product = await requestJson("/products", {
        method: "POST",
        body: JSON.stringify({ ...productForm, rate: Number(productForm.rate || 0) }),
      });
      setProducts((current) => [product, ...current]);
      setProductForm(emptyProductForm);
      setStatus(`Product ${product.name} saved.`);
    } catch (error) {
      setStatus(error.message);
    }
  };

  const handleItemChange = (index, field, value) => {
    setItemRows((current) =>
      current.map((row, rowIndex) => {
        if (rowIndex !== index) return row;
        if (field === "product_id") {
          const selectedProduct = products.find((product) => product.id === value);
          return {
            ...row,
            product_id: value,
            product_name: selectedProduct?.name || "",
            rate: selectedProduct?.rate ?? row.rate,
            amount: Number(row.quantity || 0) * Number((selectedProduct?.rate ?? row.rate) || 0),
          };
        }
        const nextRow = { ...row, [field]: value };
        const quantity = Number(nextRow.quantity || 0);
        const rate = Number(nextRow.rate || 0);
        nextRow.amount = quantity * rate;
        return nextRow;
      }),
    );
  };

  const addItemRow = () => setItemRows((current) => [...current, emptyItem()]);

  const handleChallanSubmit = async (event) => {
    event.preventDefault();
    try {
      const payload = {
        ...challanForm,
        items: itemRows.map((row) => ({
          product_id: row.product_id,
          product_name: row.product_name,
          quantity: Number(row.quantity || 0),
          rate: Number(row.rate || 0),
          amount: Number(row.amount || 0),
        })),
      };
      const challan = await requestJson("/challans", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setChallans((current) => [challan, ...current]);
      setStatus(`Challan ${challan.challan_number} created.`);
      setChallanForm({
        challan_number: "",
        challan_date: new Date().toISOString().slice(0, 10),
        plant_id: "",
        customer_name: "",
        customer_address: "",
        vehicle_no: "",
        lr_no: "",
        notes: "",
      });
      setItemRows([emptyItem()]);
    } catch (error) {
      setStatus(error.message);
    }
  };

  const openPdf = (challanId) => {
    window.open(`${API_BASE}/challans/${challanId}/pdf`, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="app-shell">
      <style>{styles}</style>
      <header className="hero-card">
        <div>
          <p className="eyebrow">Delivery Challan System</p>
          <h1>Create challans and manage plants and products from one place.</h1>
          <p className="helper-text">This UI mirrors the workbook flow while storing master data in the backend and generating PDF challans.</p>
        </div>
        <div className="status-pill">{status}</div>
      </header>

      <section className="grid">
        <article className="card">
          <h2>Plant Master</h2>
          <form onSubmit={handlePlantSubmit} className="stack">
            {/* Input fields for Plant Form */}
            <input value={plantForm.name} onChange={(event) => setPlantForm({ ...plantForm, name: event.target.value })} placeholder="Plant name" required />
            <input value={plantForm.code} onChange={(event) => setPlantForm({ ...plantForm, code: event.target.value })} placeholder="Plant code" required />
            <input value={plantForm.address} onChange={(event) => setPlantForm({ ...plantForm, address: event.target.value })} placeholder="Address" />
            <input value={plantForm.contact_person} onChange={(event) => setPlantForm({ ...plantForm, contact_person: event.target.value })} placeholder="Contact person" />
            <input value={plantForm.phone} onChange={(event) => setPlantForm({ ...plantForm, phone: event.target.value })} placeholder="Phone" />
            <button type="submit">Save Plant</button>
          </form>
          <ul className="stack" style={{ marginTop: '1.5rem' }}> {/* Added stack class and margin for spacing */}
            {plants.map((plant) => (
              <li key={plant.id}>
                <strong>{plant.name}</strong> <span>({plant.code})</span>
              </li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h2>Product Master</h2>
          <form onSubmit={handleProductSubmit} className="stack">
            {/* Input fields for Product Form */}
            <input value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} placeholder="Product name" required />
            <input value={productForm.code} onChange={(event) => setProductForm({ ...productForm, code: event.target.value })} placeholder="Product code" required />
            <input value={productForm.hsn_code} onChange={(event) => setProductForm({ ...productForm, hsn_code: event.target.value })} placeholder="HSN code" />
            <input value={productForm.unit} onChange={(event) => setProductForm({ ...productForm, unit: event.target.value })} placeholder="Unit" />
            <input type="number" value={productForm.rate} onChange={(event) => setProductForm({ ...productForm, rate: event.target.value })} placeholder="Rate" />
            <input value={productForm.description} onChange={(event) => setProductForm({ ...productForm, description: event.target.value })} placeholder="Description" />
            <button type="submit">Save Product</button>
          </form>
          <ul className="stack" style={{ marginTop: '1.5rem' }}> {/* Added stack class and margin for spacing */}
            {products.map((product) => (
              <li key={product.id}>
                <strong>{product.name}</strong> <span>₹{product.rate}</span>
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="card wide-card">
        <h2>Create Delivery Challan</h2>
        <form onSubmit={handleChallanSubmit} className="stack">
          {/* Challan Header Fields */}
          <div className="row">
            <input value={challanForm.challan_number} onChange={(event) => setChallanForm({ ...challanForm, challan_number: event.target.value })} placeholder="Challan number" required />
            <input type="date" value={challanForm.challan_date} onChange={(event) => setChallanForm({ ...challanForm, challan_date: event.target.value })} required />
            <select value={challanForm.plant_id} onChange={(event) => setChallanForm({ ...challanForm, plant_id: event.target.value })} required>
              <option value="">Select plant</option>
              {plants.map((plant) => (
                <option value={plant.id} key={plant.id}>{plant.name}</option>
              ))}
            </select>
          </div>
          <div className="row">
            <input value={challanForm.customer_name} onChange={(event) => setChallanForm({ ...challanForm, customer_name: event.target.value })} placeholder="Customer name" required />
            <input value={challanForm.customer_address} onChange={(event) => setChallanForm({ ...challanForm, customer_address: event.target.value })} placeholder="Customer address" />
            <input value={challanForm.vehicle_no} onChange={(event) => setChallanForm({ ...challanForm, vehicle_no: event.target.value })} placeholder="Vehicle no" />
          </div>
          <div className="row">
            <input value={challanForm.lr_no} onChange={(event) => setChallanForm({ ...challanForm, lr_no: event.target.value })} placeholder="LR no" />
            <input value={challanForm.notes} onChange={(event) => setChallanForm({ ...challanForm, notes: event.target.value })} placeholder="Notes" />
          </div>

          <h3>Items</h3>
          {/* Challan Items */}
          {itemRows.map((row, index) => (
            <div className="item-row" key={`${row.product_id || "new"}-${index}`}>
              <select value={row.product_id} onChange={(event) => handleItemChange(index, "product_id", event.target.value)} required>
                <option value="">Select product</option>
                {products.map((product) => (
                  <option value={product.id} key={product.id}>{product.name}</option>
                ))}
              </select>
              <input type="number" value={row.quantity} onChange={(event) => handleItemChange(index, "quantity", event.target.value)} placeholder="Qty" required />
              <input type="number" value={row.rate} onChange={(event) => handleItemChange(index, "rate", event.target.value)} placeholder="Rate" required />
              <input type="number" value={row.amount} readOnly />
            </div>
          ))}

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '1rem' }}> {/* Replaced row-between with inline style for clarity */}
            <button type="button" className="secondary" onClick={addItemRow}>Add item</button>
            <button type="submit">Create challan</button>
          </div>
        </form>
      </section>

      <section className="card wide-card">
        <h2>Recent Challans</h2>
        <ul className="stack"> {/* Changed to stack for consistent spacing */}
          {challans.map((challan) => (
            <li key={challan.id} className="list-row">
              <div>
                <strong>{challan.challan_number}</strong> <span>{challan.customer_name}</span>
              </div>
              <div>
                <span>₹{challan.total_amount}</span>
                <button type="button" className="secondary" onClick={() => openPdf(challan.id)}>PDF</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
