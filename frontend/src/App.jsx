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
  button:disabled { opacity: 0.6; cursor: not-allowed; }
  .helper-text { font-size: 0.9rem; opacity: 0.8; margin-top: 0.5rem; }
  .list-row { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 0; border-bottom: 1px solid var(--border); }
  .list-row:last-child { border-bottom: none; }
  button:hover { background: var(--primary-hover); }
  button.secondary { background: white; border: 1px solid var(--primary); color: var(--primary); }
  
  .nav-bar { display: flex; gap: 1rem; margin-bottom: 2rem; background: var(--card); padding: 1rem; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .nav-bar button { flex: 1; }
  .search-input { margin-bottom: 1rem; }

  .loading-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    z-index: 10000;
    color: white;
  }
  .spinner {
    border: 4px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top: 4px solid white;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin-bottom: 10px;
  }
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
`;

const API_BASE = "/api";

const emptyPlantForm = {
  name: "",
  code: "",
  address: "",
  state: "",
  city: "",
  pincode: "",
  gstin: "",
  contact_person: "",
  phone: "",
  status: "Active",
};

const emptyProductForm = {
  name: "",
  code: "",
  hsn_code: "",
  unit: "Nos",
  description: "",
};

const emptyItem = () => ({
  product_id: "",
  product_name: "",
  product_code: "",
  unit: "",
  quantity: "",
  rate: "",
  amount: 0,
});

export default function App() {
  const [activeTab, setActiveTab] = useState("create-challan"); // masters, create-challan, dashboard, reports
  const [plants, setPlants] = useState([]);
  const [products, setProducts] = useState([]);
  const [challans, setChallans] = useState([]);
  const [plantForm, setPlantForm] = useState(emptyPlantForm);
  const [productForm, setProductForm] = useState(emptyProductForm);
  const [challanForm, setChallanForm] = useState({
    challan_date: new Date().toISOString().slice(0, 10),
    from_plant_id: "",
    from_plant_name: "",
    from_plant_address: "",
    from_plant_state: "",
    from_plant_city: "",
    from_plant_pincode: "",
    from_plant_gstin: "",
    from_plant_branch: "",
    plant_id: "",
    customer_name: "",
    customer_address: "",
    customer_state: "",
    customer_city: "",
    customer_pincode: "",
    customer_gstin: "",
    vehicle_no: "",
    order_ref: "",
    docket_no: "",
    reason_for_dc: "",
  });
  const [isLoading, setIsLoading] = useState(false);
  const [itemRows, setItemRows] = useState([emptyItem()]);
  const [status, setStatus] = useState("Ready to create delivery challans.");
  const [selectedFile, setSelectedFile] = useState(null); // New state for bulk upload file
  const [bulkUploadErrors, setBulkUploadErrors] = useState([]); // New state for bulk upload errors
  const [plantFile, setPlantFile] = useState(null);
  const [productFile, setProductFile] = useState(null);
  const [plantErrors, setPlantErrors] = useState([]);
  const [productErrors, setProductErrors] = useState([]);
  const [challanSearch, setChallanSearch] = useState("");
  const [reportDates, setReportDates] = useState({ start: "", end: "" });

  // Manage Data search and selection states
  const [plantManageSearch, setPlantManageSearch] = useState("");
  const [productManageSearch, setProductManageSearch] = useState("");
  const [challanManageSearch, setChallanManageSearch] = useState("");
  const [selectedPlants, setSelectedPlants] = useState(new Set());
  const [selectedProducts, setSelectedProducts] = useState(new Set());
  const [selectedChallans, setSelectedChallans] = useState(new Set());


  // --- Login/Signup States ---
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [userRole, setUserRole] = useState("User");
  const [showSignupForm, setShowSignupForm] = useState(false);
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [showForgotPasswordForm, setShowForgotPasswordForm] = useState(false);
  const [showResetPasswordForm, setShowResetPasswordForm] = useState(false);
  const [resetEmail, setResetEmail] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [loggedInUserEmail, setLoggedInUserEmail] = useState(""); // New state
  const [loginTime, setLoginTime] = useState(""); // New state
  const [users, setUsers] = useState([]);

  const requestJson = async (path, options = {}) => {
    const url = `${API_BASE}${path}`;
    console.log(`[API Request] ${options.method || 'GET'} ${url}`);
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }

    if (!response.ok) {
      let msg = response.statusText || "Request failed";
      const detail = data.detail;
      if (detail) {
        msg = (typeof detail === 'object') ? (detail.message || msg) : detail;
      }
      throw new Error(msg);
    }
    return data;
  };

  const loadPlants = async () => {
    setIsLoading(true);
    try {
      const data = await requestJson("/plants");
      setPlants(data);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const loadProducts = async () => {
    setIsLoading(true);
    try {
      const data = await requestJson("/products");
      setProducts(data);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const loadChallans = async () => {
    setIsLoading(true);
    try {
      const data = await requestJson("/challans");
      setChallans(data);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const loadUsers = async () => {
    if (userRole !== "Admin") return;
    setIsLoading(true);
    try {
      const data = await requestJson("/users");
      setUsers(data);
    } catch (error) { setStatus(error.message); }
    finally { setIsLoading(false); }
  };

  // --- Diagnostic Logs ---
  useEffect(() => {
    console.log("--- Frontend Diagnostic Start ---");
    console.log("Current API_BASE:", API_BASE);
    console.log("Window Location:", window.location.href);
    
    // Immediate connectivity test
    fetch(`${API_BASE}/health`)
      .then(res => res.json())
      .then(data => console.log("Backend Health Check Result:", data))
      .catch(err => console.error("Backend Health Check Failed:", err))
      .finally(() => console.log("--- Frontend Diagnostic End ---"));
  }, []);

  useEffect(() => {
    // Only load data if logged in
    if (isLoggedIn) {
      const fetchData = async () => {
        setIsLoading(true);
        const tasks = [loadPlants(), loadProducts(), loadChallans()];
        if (userRole === "Admin") tasks.push(loadUsers());
        await Promise.all(tasks);
        setIsLoading(false);
      };
      fetchData();
    }
  }, [isLoggedIn, userRole]); // Re-run when login status or role changes

  const handlePlantSubmit = async (event) => {
    event.preventDefault();
    setIsLoading(true);
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
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeletePlant = async (id) => {
    if (!window.confirm("Are you sure you want to delete this plant?")) return;
    setIsLoading(true);
    try {
      await requestJson(`/plants/${id}`, { method: "DELETE" });
      setPlants((current) => current.filter((p) => p.id !== id));
      setStatus("Plant deleted.");
    } catch (error) { setStatus(error.message); }
    finally { setIsLoading(false); }
  };

  const handleBulkDelete = async (type, selectedIds, setter, selectionSetter) => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`Are you sure you want to delete ${selectedIds.size} ${type}(s)? This action cannot be undone.`)) return;
    setIsLoading(true);
    try {
      await requestJson(`/${type}s/bulk-delete`, {
        method: "POST",
        body: JSON.stringify({ ids: Array.from(selectedIds) }),
      });
      setter((current) => current.filter((item) => !selectedIds.has(item.id)));
      selectionSetter(new Set());
      setStatus(`${selectedIds.size} ${type}(s) deleted.`);
    } catch (error) { setStatus(error.message); }
    finally { setIsLoading(false); }
  };

  const toggleSelect = (id, currentSet, setter) => {
    const next = new Set(currentSet);
    if (next.has(id)) next.delete(id); else next.add(id);
    setter(next);
  };

  const handleUpdateRole = async (userId, newRole) => {
    if (!window.confirm(`Change user role to ${newRole}?`)) return;
    setIsLoading(true);
    try {
      await requestJson(`/users/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole }),
      });
      setUsers(current => current.map(u => u.id === userId ? { ...u, role: newRole } : u));
      setStatus(`Updated role for user.`);
    } catch (error) { setStatus(error.message); }
    finally { setIsLoading(false); }
  };

  const handleDeleteProduct = async (id) => {
    if (!window.confirm("Are you sure you want to delete this product?")) return;
    setIsLoading(true);
    try {
      await requestJson(`/products/${id}`, { method: "DELETE" });
      setProducts((current) => current.filter((p) => p.id !== id));
      setStatus("Product deleted.");
    } catch (error) { setStatus(error.message); }
    finally { setIsLoading(false); }
  };

  const handleDeleteChallan = async (id) => {
    if (!window.confirm("Are you sure you want to delete this challan? This action cannot be undone.")) return;
    setIsLoading(true);
    try {
      await requestJson(`/challans/${id}`, { method: "DELETE" });
      setChallans((current) => current.filter((c) => c.id !== id));
      setStatus("Challan deleted.");
    } catch (error) { setStatus(error.message); }
    finally { setIsLoading(false); }
  };

  const handleProductSubmit = async (event) => {
    event.preventDefault();
    setIsLoading(true);
    try {
      const product = await requestJson("/products", {
        method: "POST",
        body: JSON.stringify(productForm),
      });
      setProducts((current) => [product, ...current]);
      setProductForm(emptyProductForm);
      setStatus(`Product ${product.name} saved.`);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setIsLoading(false);
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
            product_code: selectedProduct?.code || "",
            unit: selectedProduct?.unit || "Nos",
            rate: row.rate,
            amount: Number(row.quantity || 0) * Number(row.rate || 0),
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

  const handleFromPlantChange = (plantId) => {
    const selectedPlant = plants.find((p) => p.id === plantId);
    setChallanForm((prev) => ({
      ...prev,
      from_plant_id: plantId,
      from_plant_name: selectedPlant ? selectedPlant.name : "",
      from_plant_address: selectedPlant ? (selectedPlant.address || "") : "",
      from_plant_state: selectedPlant ? (selectedPlant.state || "") : "",
      from_plant_city: selectedPlant ? (selectedPlant.city || "") : "",
      from_plant_pincode: selectedPlant ? (selectedPlant.pincode || "") : "",
      from_plant_gstin: selectedPlant ? (selectedPlant.gstin || "") : "",
      from_plant_branch: selectedPlant ? (selectedPlant.name || "") : "",
    }));
  };

  const handleChallanPlantChange = (plantId) => {
    const selectedPlant = plants.find((p) => p.id === plantId);
    setChallanForm((prev) => ({
      ...prev,
      plant_id: plantId,
      customer_name: selectedPlant ? selectedPlant.name : "",
      customer_address: selectedPlant ? (selectedPlant.address || "") : "",
      customer_state: selectedPlant ? (selectedPlant.state || "") : "",
      customer_city: selectedPlant ? (selectedPlant.city || "") : "",
      customer_pincode: selectedPlant ? (selectedPlant.pincode || "") : "",
      customer_gstin: selectedPlant ? (selectedPlant.gstin || "") : "",
    }));
  };

  const addItemRow = () => setItemRows((current) => [...current, emptyItem()]);

  const handleChallanSubmit = async (event) => {
    event.preventDefault();
    setIsLoading(true);
    try {
      const payload = {
        ...challanForm,
        items: itemRows.map((row) => ({
          product_id: row.product_id,
          product_name: row.product_name,
          product_code: row.product_code,
          unit: row.unit,
          quantity: Number(row.quantity || 0),
          rate: Number(row.rate || 0),
          amount: Number(row.amount || 0),
        })), // Auto-populate created_by
        created_by: loggedInUserEmail,
      };
      const challan = await requestJson("/challans", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setChallans((current) => [challan, ...current]);
      setStatus(`Challan ${challan.challan_number} created.`);
      setChallanForm({
        challan_date: new Date().toISOString().slice(0, 10),
        from_plant_id: "",
        from_plant_name: "",
        from_plant_address: "",
        from_plant_state: "",
        from_plant_city: "",
        from_plant_pincode: "",
        from_plant_gstin: "",
        from_plant_branch: "",
        plant_id: "",
        customer_name: "",
        customer_address: "",
        customer_state: "",
        customer_city: "",
        customer_pincode: "",
        customer_gstin: "",
        vehicle_no: "",
        order_ref: "",
        docket_no: "",
        reason_for_dc: "",
        created_by: "",

      });
      setItemRows([emptyItem()]);
    } catch (error) {
      setStatus(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleBulkUpload = async (file, path, setter, errorSetter, successMsg) => {
    if (!file) return;
    setIsLoading(true);
    errorSetter([]);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        body: formData,
      });

      const text = await response.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }

      if (!response.ok) {
        const detail = data.detail || {};
        const msg = (typeof detail === 'object') ? (detail.message || response.statusText) : (detail || response.statusText);
        const errs = detail.errors || [msg];
        errorSetter(errs);
        setStatus(msg);
      } else {
        setter((current) => [...data, ...current]);
        setStatus(`${successMsg}: ${data.length} records added.`);
      }
    } catch (error) {
      errorSetter([error.message]);
      setStatus("Upload error.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
    setBulkUploadErrors([]); // Clear previous errors
  };

  const handleBulkUploadSubmit = async (event) => {
    event.preventDefault();
    if (!selectedFile) {
      setBulkUploadErrors(["Please select a file to upload."]);
      return;
    }

    setIsLoading(true);
    setBulkUploadErrors([]);
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${API_BASE}/challans/bulk-upload`, {
        method: "POST",
        body: formData,
      });

      const text = await response.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }

      if (!response.ok) {
        const detail = data.detail || {};
        const msg = (typeof detail === 'object') ? (detail.message || response.statusText) : (detail || response.statusText);
        const errs = detail.errors || [msg];
        setBulkUploadErrors(errs);
        setStatus(`Bulk upload failed: ${msg}`);
      } else {
        setChallans((current) => [...data, ...current]);
        setStatus(`Successfully created ${data.length} challans from bulk upload.`);
        setSelectedFile(null); // Clear selected file
        document.getElementById("bulk-upload-file-input").value = ""; // Clear file input
      }
    } catch (error) {
      setBulkUploadErrors([error.message]);
      setStatus(`Bulk upload failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const openPdf = (challanId) => {
    window.open(`${API_BASE}/challans/${challanId}/pdf`, "_blank", "noopener,noreferrer");
  };

  const downloadTemplate = (name) => {
    window.open(`${API_BASE}/templates/${name}`, "_blank");
  };

  const downloadReport = () => {
    const params = new URLSearchParams();
    if (reportDates.start) params.append("start_date", reportDates.start);
    if (reportDates.end) params.append("end_date", reportDates.end);
    window.open(`${API_BASE}/reports/product-wise/csv?${params.toString()}`, "_blank");
  };

  // --- Auth Handlers ---
  const handleAuthSubmit = async (event) => {
    event.preventDefault();
    setIsLoading(true);
    setAuthError("");

    const endpoint = showSignupForm ? "/auth/signup" : "/auth/login";
    try {
      const data = await requestJson(endpoint, {
        method: "POST",
        body: JSON.stringify({ email: authEmail, password: authPassword }),
      });

      setIsLoggedIn(true);
      setUserRole(data.role || "User");
      setLoggedInUserEmail(authEmail);
      setLoginTime(new Date().toLocaleString());
      setAuthEmail("");
      setAuthPassword("");
      setAuthError("");
      setStatus(data.message || (showSignupForm ? "Signup successful! Please log in." : "Login successful!"));
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    setUserRole("User");
    setLoggedInUserEmail("");
    setLoginTime("");
    setStatus("Logged out successfully.");
  };

  const handleForgotPasswordRequest = async (event) => {
    event.preventDefault();
    setIsLoading(true);
    setAuthError("");
    try {
      const data = await requestJson("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email: resetEmail }),
      });
      if (data.token) setResetToken(data.token);
      setStatus(data.message);
      setShowForgotPasswordForm(false);
      setShowResetPasswordForm(true);
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordReset = async (event) => {
    event.preventDefault();
    setIsLoading(true);
    setAuthError("");
    try {
      const data = await requestJson("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ email: resetEmail, token: resetToken, new_password: newPassword }),
      });
      setStatus(data.message);
      setShowResetPasswordForm(false);
      setAuthEmail(resetEmail); // Pre-fill email for login
    } catch (error) {
      setAuthError(error.message);
    } finally {
      setIsLoading(false);
    }
  };
  // --- Password Complexity Validation (Frontend) ---
  const validatePassword = (password) => {
    const errors = [];
    if (password.length < 8) {
      errors.push("Password must be at least 8 characters long.");
    }
    if (new TextEncoder().encode(password).length > 72) {
      errors.push("Password cannot be longer than 72 bytes (characters).");
    }
    if (!/[a-z]/.test(password)) {
      errors.push("Password must contain at least one lowercase letter.");
    }
    if (!/[A-Z]/.test(password)) {
      errors.push("Password must contain at least one uppercase letter.");
    }
    if (!/[0-9]/.test(password)) {
      errors.push("Password must contain at least one digit.");
    }
    if (!/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?]/.test(password)) {
      errors.push("Password must contain at least one special character.");
    }
    return errors;
  };

  const passwordValidationErrors = (showSignupForm || showResetPasswordForm) ? validatePassword(showSignupForm ? authPassword : newPassword) : [];


  if (!isLoggedIn) {
    return (
      <div className="app-shell" style={{ maxWidth: '500px' }}>
        <style>{styles}</style>
        {isLoading && (
          <div className="loading-overlay">
            <div className="spinner"></div>
            <p>Please wait...</p>
          </div>
        )}
        <header className="hero-card">
          <div>
            <p className="eyebrow">Delivery Challan System</p>
            <h1>
              {showSignupForm ? "Sign Up" : ""}
              {!showSignupForm && !showForgotPasswordForm && !showResetPasswordForm ? "Login" : ""}
              {showForgotPasswordForm ? "Forgot Password" : ""}
              {showResetPasswordForm ? "Reset Password" : ""}
            </h1>
            <p className="helper-text">
              {showSignupForm ? "Create an account to get started." : ""}
              {!showSignupForm && !showForgotPasswordForm && !showResetPasswordForm ? "Please log in to access the system." : ""}
              {showForgotPasswordForm ? "Enter your email to receive a password reset link." : ""}
              {showResetPasswordForm ? "Enter your new password." : ""}
            </p>
          </div>
          <div className="status-pill">
            {isLoading && <span>Loading... </span>}
            {authError || status}
          </div>
        </header>
        
        {!showForgotPasswordForm && !showResetPasswordForm && (
          <section className="card wide-card">
            <form onSubmit={handleAuthSubmit} className="stack">
              <input
                type="email"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                placeholder="Email"
                required
              />
              <input
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                placeholder="Password"
                required
              />
              {showSignupForm && passwordValidationErrors.length > 0 && (
                <ul style={{ color: 'red', fontSize: '0.8rem', listStyleType: 'disc', marginLeft: '1.2rem' }}>
                  {passwordValidationErrors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              )}
              <button type="submit" disabled={isLoading || (showSignupForm && passwordValidationErrors.length > 0)}>
                {showSignupForm ? "Sign Up" : "Login"}
              </button>
            </form>
            <p style={{ textAlign: 'center', marginTop: '1rem' }}>
              {!showSignupForm && (
                <button type="button" className="secondary" onClick={() => setShowForgotPasswordForm(true)}>
                  Forgot Password?
                </button>
              )}
              {showSignupForm ? (
                <>
                  Already have an account?{" "}
                  <button type="button" className="secondary" onClick={() => setShowSignupForm(false)}>
                    Login
                  </button>
                </>
              ) : (
                <>
                  Don't have an account?{" "}
                  <button type="button" className="secondary" onClick={() => setShowSignupForm(true)}>
                    Sign Up
                  </button>
                </>
              )}
            </p>
          </section>
        )}

        {showForgotPasswordForm && (
          <section className="card wide-card">
            <form onSubmit={handleForgotPasswordRequest} className="stack">
              <input
                type="email"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                placeholder="Enter your email"
                required
              />
              <button type="submit" disabled={isLoading}>Send Reset Link</button>
            </form>
            <p style={{ textAlign: 'center', marginTop: '1rem' }}>
              <button type="button" className="secondary" onClick={() => setShowForgotPasswordForm(false)}>
                Back to Login
              </button>
              {showSignupForm ? (
                <>
                  Already have an account?{" "}
                  <button type="button" className="secondary" onClick={() => setShowSignupForm(false)}>
                    Login
                  </button>
                </>
              ) : (
                <>
                  Don't have an account?{" "}
                  <button type="button" className="secondary" onClick={() => setShowSignupForm(true)}>
                    Sign Up
                  </button>
                </>
              )}
            </p>
          </section>
        )}

        {showResetPasswordForm && (
          <section className="card wide-card">
            <form onSubmit={handlePasswordReset} className="stack">
              <input
                type="email"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                placeholder="Your email"
                required
                readOnly // Email should be pre-filled or not editable here
              />
              <input
                type="text"
                value={resetToken}
                onChange={(event) => setResetToken(event.target.value)}
                placeholder="Reset Token"
                required
              />
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="New Password"
                required
              />
              {passwordValidationErrors.length > 0 && (
                <ul style={{ color: 'red', fontSize: '0.8rem', listStyleType: 'disc', marginLeft: '1.2rem' }}>
                  {passwordValidationErrors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              )}
              <button type="submit" disabled={isLoading || passwordValidationErrors.length > 0}>Reset Password</button>
            </form>
            <p style={{ textAlign: 'center', marginTop: '1rem' }}>
              <button type="button" className="secondary" onClick={() => setShowResetPasswordForm(false)}>
                Back to Login
              </button>
            </p>
          </section>
        )}
      </div>
    );
  }

  const filteredChallans = challans.filter(c => 
    c.challan_number?.toLowerCase().includes(challanSearch.toLowerCase()) ||
    c.customer_name?.toLowerCase().includes(challanSearch.toLowerCase())
  );

  return (
    <div className="app-shell">
      <style>{styles}</style>
      {isLoading && (
        <div className="loading-overlay">
          <div className="spinner"></div>
          <p>Please wait...</p>
        </div>
      )}
      <header className="hero-card">
        <div>
          <p className="eyebrow">Delivery Challan System</p>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h1>Create challans and manage plants and products from one place.</h1>            
          </div>
          <p className="helper-text">This UI mirrors the workbook flow while storing master data in the backend and generating PDF challans.</p>
        </div>
        <div style={{ textAlign: 'right' }}>
          {loggedInUserEmail && (
            <p className="eyebrow" style={{ marginBottom: '0.5rem' }}>
              Logged in as: {loggedInUserEmail}
              <br />
              Login Time: {loginTime} | Role: {userRole}
            </p>
          )}
          <button className="secondary" onClick={handleLogout} disabled={isLoading}>Logout</button>
        </div>
        <div className="status-pill">
          {isLoading && <span>Loading... </span>}
          {status}
        </div>
      </header>

      <nav className="nav-bar">
        <button className={activeTab === "masters" ? "" : "secondary"} onClick={() => setActiveTab("masters")}>Masters</button>
        <button className={activeTab === "create-challan" ? "" : "secondary"} onClick={() => setActiveTab("create-challan")}>Create Challan</button>
        <button className={activeTab === "dashboard" ? "" : "secondary"} onClick={() => setActiveTab("dashboard")}>Dashboard</button>
        <button className={activeTab === "reports" ? "" : "secondary"} onClick={() => setActiveTab("reports")}>Reports</button>
        {userRole === "Admin" && (
          <>
            <button className={activeTab === "manage-data" ? "" : "secondary"} onClick={() => setActiveTab("manage-data")}>Manage Data</button>
            <button className={activeTab === "user-management" ? "" : "secondary"} onClick={() => setActiveTab("user-management")}>User Management</button>
          </>
        )}
      </nav>

      {activeTab === "masters" && (
      <section className="grid">
        <article className="card">
          <h2>Plant Master</h2>
          <form onSubmit={handlePlantSubmit} className="stack">
            {/* Input fields for Plant Form */}
            <input value={plantForm.name} onChange={(event) => setPlantForm({ ...plantForm, name: event.target.value })} placeholder="Plant name" required />
            <input value={plantForm.code} onChange={(event) => setPlantForm({ ...plantForm, code: event.target.value })} placeholder="Plant code" required />
            <input value={plantForm.address} onChange={(event) => setPlantForm({ ...plantForm, address: event.target.value })} placeholder="Address" />
            <div className="row">
              <input value={plantForm.city} onChange={(event) => setPlantForm({ ...plantForm, city: event.target.value })} placeholder="City" />
              <input value={plantForm.state} onChange={(event) => setPlantForm({ ...plantForm, state: event.target.value })} placeholder="State" />
            </div>
            <input value={plantForm.pincode} onChange={(event) => setPlantForm({ ...plantForm, pincode: event.target.value })} placeholder="Pincode" />
            <input value={plantForm.gstin} onChange={(event) => setPlantForm({ ...plantForm, gstin: event.target.value })} placeholder="GSTIN" />
            <input value={plantForm.contact_person} onChange={(event) => setPlantForm({ ...plantForm, contact_person: event.target.value })} placeholder="Contact person" />
            <input value={plantForm.phone} onChange={(event) => setPlantForm({ ...plantForm, phone: event.target.value })} placeholder="Phone" />
            <button type="submit" disabled={isLoading}>Save Plant</button>
          </form>
          
          <div className="stack" style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
            <p className="eyebrow">Bulk Upload Plants</p>
            <input type="file" accept=".csv" onChange={(e) => setPlantFile(e.target.files[0])} />
            <div className="row" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <button className="secondary" onClick={() => handleBulkUpload(plantFile, "/plants/bulk-upload", setPlants, setPlantErrors, "Plants uploaded")} disabled={isLoading || !plantFile}>Upload CSV</button>
              <button className="secondary" onClick={() => downloadTemplate("plants")}>Download Template</button>
            </div>
            {plantErrors.length > 0 && <ul style={{ color: 'red', fontSize: '0.8rem' }}>{plantErrors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
          </div>
        </article>

        <article className="card">
          <h2>Product Master</h2>
          <form onSubmit={handleProductSubmit} className="stack">
            {/* Input fields for Product Form */}
            <input value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} placeholder="Product name" required />
            <input value={productForm.code} onChange={(event) => setProductForm({ ...productForm, code: event.target.value })} placeholder="Product code" required />
            <input value={productForm.hsn_code} onChange={(event) => setProductForm({ ...productForm, hsn_code: event.target.value })} placeholder="HSN code" />
            <input value={productForm.unit} onChange={(event) => setProductForm({ ...productForm, unit: event.target.value })} placeholder="Unit" />
            <input value={productForm.description} onChange={(event) => setProductForm({ ...productForm, description: event.target.value })} placeholder="Description" />
            <button type="submit" disabled={isLoading}>Save Product</button>
          </form>

          <div className="stack" style={{ marginTop: '1.5rem', borderTop: '1px solid var(--border)', paddingTop: '1rem' }}>
            <p className="eyebrow">Bulk Upload Products</p>
            <input type="file" accept=".csv" onChange={(e) => setProductFile(e.target.files[0])} />
            <div className="row" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <button className="secondary" onClick={() => handleBulkUpload(productFile, "/products/bulk-upload", setProducts, setProductErrors, "Products uploaded")} disabled={isLoading || !productFile}>Upload CSV</button>
              <button className="secondary" onClick={() => downloadTemplate("products")}>Download Template</button>
            </div>
            {productErrors.length > 0 && <ul style={{ color: 'red', fontSize: '0.8rem' }}>{productErrors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
          </div>
        </article>
      </section>
      )}

      {activeTab === "create-challan" && (
        <>
      <section className="card wide-card">
        <h2>Create Delivery Challan</h2>
        <form onSubmit={handleChallanSubmit} className="stack">
          {/* Challan Header Fields */}
          <div className="row">
            <input type="date" value={challanForm.challan_date} onChange={(event) => setChallanForm({ ...challanForm, challan_date: event.target.value })} required />
          </div>
          <div className="row">
            <select value={challanForm.from_plant_id} onChange={(event) => handleFromPlantChange(event.target.value)} required>
              <option value="">Select From Plant</option>
              {plants.map((plant) => (
                <option value={plant.id} key={plant.id}>{plant.name}</option>
              ))}
            </select>
            <select value={challanForm.plant_id} onChange={(event) => handleChallanPlantChange(event.target.value)} required>
              <option value="">Select To Plant</option>
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
            <input value={challanForm.order_ref} onChange={(event) => setChallanForm({ ...challanForm, order_ref: event.target.value })} placeholder="Order Ref" />
            <input value={challanForm.docket_no} onChange={(event) => setChallanForm({ ...challanForm, docket_no: event.target.value })} placeholder="Docket No" />
            <input value={challanForm.reason_for_dc} onChange={(event) => setChallanForm({ ...challanForm, reason_for_dc: event.target.value })} placeholder="Reason for DC" />
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
            <button type="button" className="secondary" onClick={addItemRow} disabled={isLoading}>Add item</button>
            <button type="submit" disabled={isLoading}>Create challan</button>
          </div>
        </form>
      </section>

      <section className="card wide-card">
        <h2>Bulk Upload Challans (CSV)</h2>
        <form onSubmit={handleBulkUploadSubmit} className="stack">
          <input type="file" id="bulk-upload-file-input" accept=".csv" onChange={handleFileChange} />
          <p className="helper-text">Upload a CSV file with columns: `from_plant_code,to_plant_code,sku,item_name,quantity,rate,order_ref,docket_no,reason_for_dc`</p>
          <div className="row" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <button type="submit" disabled={isLoading || !selectedFile}>Upload CSV</button>
            <button type="button" className="secondary" onClick={() => downloadTemplate("challans")}>Download Template</button>
          </div>
          {bulkUploadErrors.length > 0 && (
            <div style={{ color: 'red', marginTop: '1rem' }}>
              <h4>Bulk Upload Errors:</h4>
              <ul>
                {bulkUploadErrors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </div>
          )}
        </form>
      </section>
        </>
      )}

      {activeTab === "dashboard" && (
      <section className="card wide-card">
        <h2>All Delivery Challans</h2>
        <input 
          className="search-input"
          value={challanSearch} 
          onChange={(e) => setChallanSearch(e.target.value)} 
          placeholder="Search by Challan No or Customer..." 
        />
        <ul className="stack"> {/* Changed to stack for consistent spacing */}
          {filteredChallans.map((challan) => (
            <li key={challan.id} className="list-row">
              <div>
                <strong>{challan.challan_number}</strong> <span>{challan.customer_name}</span>
              </div>
              <div>
                <span>₹{challan.total_amount} </span>
                <button type="button" className="secondary" onClick={() => openPdf(challan.id)}>PDF</button>
              </div>
            </li>
          ))}
        </ul>
      </section>
      )}

      {activeTab === "reports" && (
        <section className="card wide-card">
          <h2>Reports</h2>
          <p className="helper-text">Export detailed product-wise transaction data to CSV.</p>
          <div className="row" style={{ marginTop: '1.5rem' }}>
            <div>
              <label className="eyebrow">Start Date</label>
              <input type="date" value={reportDates.start} onChange={(e) => setReportDates({...reportDates, start: e.target.value})} />
            </div>
            <div>
              <label className="eyebrow">End Date</label>
              <input type="date" value={reportDates.end} onChange={(e) => setReportDates({...reportDates, end: e.target.value})} />
            </div>
          </div>
          <button style={{ marginTop: '1.5rem' }} onClick={downloadReport}>Export Product-wise CSV</button>
          
          <h3 style={{ marginTop: '2rem' }}>Master Data Reports</h3>
          <div className="row">
            <button className="secondary" onClick={() => window.open(`${API_BASE}/reports/masters/plants/csv`, "_blank")}>Export Plant Master</button>
            <button className="secondary" onClick={() => window.open(`${API_BASE}/reports/masters/products/csv`, "_blank")}>Export Product Master</button>
          </div>
        </section>
      )}

      {activeTab === "manage-data" && userRole === "Admin" && (
        <section className="stack">
          <article className="card">
            <h2>Manage Plants</h2>
            <div className="stack" style={{ marginBottom: '1rem' }}>
              <input 
                placeholder="Search Plants by name or code..." 
                value={plantManageSearch} 
                onChange={(e) => setPlantManageSearch(e.target.value)} 
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <p className="helper-text">{selectedPlants.size} selected</p>
                <button 
                  className="secondary" 
                  style={{ color: 'red', borderColor: 'red' }}
                  onClick={() => handleBulkDelete('plant', selectedPlants, setPlants, setSelectedPlants)}
                  disabled={selectedPlants.size === 0}
                >Delete Selected</button>
              </div>
            </div>
            <div className="stack">
              {plants
                .filter(p => p.name.toLowerCase().includes(plantManageSearch.toLowerCase()) || p.code.toLowerCase().includes(plantManageSearch.toLowerCase()))
                .map(p => (
                  <div key={p.id} className="list-row">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <input 
                        type="checkbox" 
                        style={{ width: 'auto' }} 
                        checked={selectedPlants.has(p.id)} 
                        onChange={() => toggleSelect(p.id, selectedPlants, setSelectedPlants)}
                      />
                      <span>{p.name} (Code: {p.code})</span>
                    </div>
                    <button className="secondary" onClick={() => handleDeletePlant(p.id)}>Delete</button>
                  </div>
                ))}
            </div>
          </article>

          <article className="card">
            <h2>Manage Products</h2>
            <div className="stack" style={{ marginBottom: '1rem' }}>
              <input 
                placeholder="Search Products by name or SKU..." 
                value={productManageSearch} 
                onChange={(e) => setProductManageSearch(e.target.value)} 
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <p className="helper-text">{selectedProducts.size} selected</p>
                <button 
                  className="secondary" 
                  style={{ color: 'red', borderColor: 'red' }}
                  onClick={() => handleBulkDelete('product', selectedProducts, setProducts, setSelectedProducts)}
                  disabled={selectedProducts.size === 0}
                >Delete Selected</button>
              </div>
            </div>
            <div className="stack">
              {products
                .filter(p => p.name.toLowerCase().includes(productManageSearch.toLowerCase()) || p.code.toLowerCase().includes(productManageSearch.toLowerCase()))
                .map(p => (
                  <div key={p.id} className="list-row">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <input 
                        type="checkbox" 
                        style={{ width: 'auto' }} 
                        checked={selectedProducts.has(p.id)} 
                        onChange={() => toggleSelect(p.id, selectedProducts, setSelectedProducts)}
                      />
                      <span>{p.name} (SKU: {p.code})</span>
                    </div>
                    <button className="secondary" onClick={() => handleDeleteProduct(p.id)}>Delete</button>
                  </div>
                ))}
            </div>
          </article>

          <article className="card">
            <h2>Manage Challans</h2>
            <div className="stack" style={{ marginBottom: '1rem' }}>
              <input 
                placeholder="Search Challans by Number or Customer..." 
                value={challanManageSearch} 
                onChange={(e) => setChallanManageSearch(e.target.value)} 
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <p className="helper-text">{selectedChallans.size} selected</p>
                <button 
                  className="secondary" 
                  style={{ color: 'red', borderColor: 'red' }}
                  onClick={() => handleBulkDelete('challan', selectedChallans, setChallans, setSelectedChallans)}
                  disabled={selectedChallans.size === 0}
                >Delete Selected</button>
              </div>
            </div>
            <div className="stack">
              {challans
                .filter(c => c.challan_number?.toLowerCase().includes(challanManageSearch.toLowerCase()) || c.customer_name?.toLowerCase().includes(challanManageSearch.toLowerCase()))
                .map(c => (
                  <div key={c.id} className="list-row">
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <input 
                        type="checkbox" 
                        style={{ width: 'auto' }} 
                        checked={selectedChallans.has(c.id)} 
                        onChange={() => toggleSelect(c.id, selectedChallans, setSelectedChallans)}
                      />
                      <span>{c.challan_number} - {c.customer_name} ({c.challan_date})</span>
                    </div>
                    <button className="secondary" onClick={() => handleDeleteChallan(c.id)}>Delete</button>
                  </div>
                ))}
            </div>
          </article>
        </section>
      )}

      
      {activeTab === "user-management" && userRole === "Admin" && (
        <section className="card wide-card">
          <h2>User Management</h2>
          <p className="helper-text">
            Change user permissions by updating their roles.
          </p>

          <div className="stack" style={{ marginTop: "1.5rem" }}>
            {users.map((u) => (
              <div key={u.id} className="list-row">
                <span>{u.email}</span>
                <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
                  <select
                    value={u.role}
                    onChange={(e) => handleUpdateRole(u.id, e.target.value)}
                    style={{ width: "auto", padding: "0.4rem" }}
                    disabled={u.email === loggedInUserEmail}
                  >
                    <option value="User">User</option>
                    <option value="Admin">Admin</option>
                  </select>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
