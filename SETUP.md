# ⚡ CellRoute - Quick Setup Guide

**For hackathon judges and evaluators**

---

## 🚀 5-Minute Setup

### Step 1: Install Dependencies (1 minute)

```bash
cd routing-project
pip install -r requirements.txt
```

---

### Step 2: Start Services (3 terminals)

**Terminal 1: Module 2 (Connectivity)**
```bash
cd module2_mahemobility
python server.py
```
✅ Wait for: `✅ Connectivity grid ready`

**Terminal 2: Module 1 (Routing)**
```bash
cd cellroute-routing
uvicorn main:app --port 8000
```
✅ Wait for: `Uvicorn running on http://0.0.0.0:8000`

**Terminal 3: Frontend**
```bash
python3 -m http.server 8080
```
✅ Wait for: `Serving HTTP on 0.0.0.0 port 8080`

---

### Step 3: Open Browser

Navigate to: **http://localhost:8080/cellroute_final.html**

---

## 🎯 Test Route

**Try this example:**
- **Origin:** `MG Road, Bengaluru`
- **Destination:** `Electronic City, Bengaluru`
- Click **"Route"** button
- Wait ~3 seconds

**You should see:**
✅ 3 different routes on the map
✅ Signal timeline chart
✅ Trade-off visualization
✅ Drop zone markers

---

## 🎮 Demo Features

### 1. Route Comparison
- Click **SHORTEST** / **FASTEST** / **CONNECTED** tabs
- Watch timeline chart update

### 2. Journey Simulator
- Click **"▶ Start"** button
- Watch signal gauge change in real-time
- Try different speeds (1x - 10x)

### 3. Drop Zones
- Red markers show poor signal areas
- Click markers for details

---

## ✅ Health Checks

**Verify all modules are running:**

```bash
# Module 2
curl http://localhost:8001/health

# Module 1
curl http://localhost:8000/health
```

---

## 🐛 Common Issues

### Map shows "Access blocked"
**Fixed!** Frontend uses CartoDB tiles (no action needed)

### Routes fail for some locations
**Add ", Bengaluru"** to all location names

### Shortest & Connected routes look the same
**Use updated main.py** with improved routing diversity

---

## 📊 What to Look For

### Key Differentiators
1. **Real connectivity data** (4,000 towers, 3,907 grid cells)
2. **3 distinct route options** (not just fastest/shortest)
3. **Live journey simulation** (signal changes dynamically)
4. **Drop zone prediction** (identifies dead zones)

### Technical Highlights
- **Microservices architecture** (3 independent components)
- **Real-time scoring** (OpenCellID integration)
- **Async processing** (FastAPI + httpx)
- **Zero-dependency frontend** (vanilla JS, no npm/build)

---

## 📝 Evaluation Checklist

- [ ] All 3 services start without errors
- [ ] Frontend loads and displays map
- [ ] Can calculate routes for Bangalore locations
- [ ] All 3 route types show different paths
- [ ] Signal timeline shows variation (not flat line)
- [ ] Journey simulator animates signal gauge
- [ ] Drop zones appear as red markers
- [ ] Browser console (F12) shows no errors

---

## 🆘 Emergency Contact

**If something breaks during demo:**

1. **Check browser console** (F12) - detailed error logs
2. **Check terminal outputs** - Module 1 & 2 logs
3. **Restart services** - Ctrl+C and restart in order:
   - Module 2 → Module 1 → Frontend

---

## 🏆 Judging Criteria Coverage

| Criterion | Feature |
|-----------|---------|
| **Innovation** | First routing app to prioritize connectivity |
| **Technical** | 3-tier microservices, real data integration |
| **Impact** | Solves dropped calls during commutes |
| **UX** | Interactive simulator, clear visualizations |
| **Scalability** | City-agnostic, expandable to any region |

---

**Questions during evaluation?** Open browser console (F12) for detailed logs!

**Thank you for evaluating CellRoute! 🚀**
