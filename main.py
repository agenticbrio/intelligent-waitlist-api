import os
import sqlite3
import uuid
import time
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from openai import AsyncOpenAI

# --- INITIALIZATION ---
app = FastAPI(title="BRIO Waitlist API", version="1.0.0")
client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# In-memory fraud tracker (IP subnet -> list of timestamps)
fraud_tracker = {}

# --- DATABASE SETUP ---
def get_db():
    conn = sqlite3.connect("brio_waitlist.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            referral_code TEXT UNIQUE,
            position REAL,
            status TEXT DEFAULT 'pending',
            source TEXT,
            industry TEXT,
            referral_text TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key TEXT PRIMARY KEY,
            tokens_remaining INTEGER
        )
    """)
    # Seed a free test key with 10,000 tokens if it doesn't exist
    if not conn.execute("SELECT 1 FROM api_keys WHERE key = 'brio_test_key'").fetchone():
        conn.execute("INSERT INTO api_keys (key, tokens_remaining) VALUES ('brio_test_key', 10000)")
    conn.commit()
    conn.close()

@app.on_event("startup")
def on_startup():
    init_db()

# --- MODELS ---
class SignupRequest(BaseModel):
    email: str
    source: str = "direct"
    industry: str = "general"
    ip_address: str = "127.0.0.1"

# --- DEPENDENCIES (TOKEN ARCHITECTURE) ---
def verify_api_key(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")
    key = auth.split(" ")[1]
    
    conn = get_db()
    row = conn.execute("SELECT tokens_remaining FROM api_keys WHERE key = ?", (key,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=403, detail="Invalid API key")
    if row["tokens_remaining"] <= 0:
        raise HTTPException(status_code=402, detail="Out of tokens")
    
    # Deduct 1 token per call
    conn = get_db()
    conn.execute("UPDATE api_keys SET tokens_remaining = tokens_remaining - 1 WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    
    return key

# --- CORE LOGIC ---
def get_ip_subnet(ip: str) -> str:
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}"
    return ip

def check_fraud(ip_address: str) -> bool:
    subnet = get_ip_subnet(ip_address)
    current_time = time.time()
    
    if subnet not in fraud_tracker:
        fraud_tracker[subnet] = []
    
    # Clean old timestamps (older than 60 seconds)
    fraud_tracker[subnet] = [t for t in fraud_tracker[subnet] if current_time - t < 60]
    
    # If 3 signups from same subnet in 60 seconds, flag as fraud
    if len(fraud_tracker[subnet]) >= 2:
        return True
        
    fraud_tracker[subnet].append(current_time)
    return False

def calculate_weight(email: str) -> int:
    if ".com" in email and "gmail" not in email and "yahoo" not in email:
        return 10 # Enterprise weight
    return 1 # Standard weight

async def generate_llm_referral_text(source: str, industry: str, referral_code: str) -> str:
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "system", 
                "content": "You write extremely short, casual 15-word referral messages for users to send to colleagues."
            }, {
                "role": "user", 
                "content": f"Source: {source}. Industry: {industry}. Referral code: {referral_code}. Write the message."
            }],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception:
        return f"Join me on the waitlist using my code: {referral_code}"

# --- ENDPOINTS ---
@app.post("/v1/signup")
async def signup(data: SignupRequest, api_key: str = Depends(verify_api_key)):
    # 1. Check Fraud Graph
    if check_fraud(data.ip_address):
        raise HTTPException(status_code=429, detail="Suspicious activity detected (Fraud cluster)")
    
    # 2. Calculate Position
    weight = calculate_weight(data.email)
    conn = get_db()
    max_pos = conn.execute("SELECT MAX(position) as max_p FROM users WHERE status != 'fraud'").fetchone()["max_p"] or 0
    new_position = max_pos + (weight * 0.1)
    
    # 3. Create User
    referral_code = str(uuid.uuid4())[:8]
    try:
        conn.execute(
            "INSERT INTO users (email, referral_code, position, status, source, industry) VALUES (?, ?, ?, 'pending', ?, ?)",
            (data.email, referral_code, new_position, data.source, data.industry)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="Email already exists")
        
    conn.close()

    # 4. Generate LLM text
    text = await generate_llm_referral_text(data.source, data.industry, referral_code)
    conn = get_db()
    conn.execute("UPDATE users SET referral_text = ? WHERE email = ?", (text, data.email))
    conn.commit()
    conn.close()

    return {"message": "Signup successful", "referral_code": referral_code, "position": new_position}

@app.get("/v1/position")
def get_position(email: str, api_key: str = Depends(verify_api_key)):
    conn = get_db()
    user = conn.execute("SELECT position, status FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"email": email, "position": user["position"], "status": user["status"]}

@app.get("/v1/referral-text")
def get_referral_text(email: str, api_key: str = Depends(verify_api_key)):
    conn = get_db()
    user = conn.execute("SELECT referral_text FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user["referral_text"]:
        return {"status": "generating", "message": "LLM is writing your custom text... check back in 2 seconds."}
        
    return {"status": "ready", "referral_text": user["referral_text"]}
