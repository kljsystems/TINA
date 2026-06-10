"""Quick smoke test for Supabase connection and conversations table."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from config import SUPABASE_URL, SUPABASE_KEY

if not SUPABASE_URL or not SUPABASE_KEY:
    print("FAIL: SUPABASE_URL or SUPABASE_KEY not set in .env")
    sys.exit(1)

print(f"Connecting to {SUPABASE_URL} ...")

from supabase import create_client
client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Insert a test row
print("Inserting test row...")
client.table("conversations").insert({
    "agent":      "test",
    "session_id": "smoke-test",
    "role":       "user",
    "content":    "hello from test script",
}).execute()

# Read it back
print("Reading it back...")
result = client.table("conversations").select("*").eq("agent", "test").execute()
print(f"Rows found: {len(result.data)}")
for row in result.data:
    print(f"  [{row['agent']}] {row['role']}: {row['content']}")

# Clean up
print("Cleaning up...")
client.table("conversations").delete().eq("agent", "test").execute()

print("\nSUCCESS — Supabase is wired up correctly.")
