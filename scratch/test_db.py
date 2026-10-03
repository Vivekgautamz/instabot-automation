import requests

SUPABASE_URL = "https://ocnpefagfqbjviurgkeb.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9jbnBlZmFnZnFianZpdXJna2ViIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MDk2MzA2NCwiZXhwIjoyMTA2NTM5MDY0fQ.RHg7_CuDelW4fio8EwUI6Q8oXUNTCKxDHT5cjB0vLCI"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=representation"
}

payload = {
    "username": "gautammmmm20",
    "display_name": "gautammmmm20",
    "auth_type": "Direct Login",
    "status": "connected",
    "is_active": True
}

r = requests.post(f"{SUPABASE_URL}/rest/v1/instagram_accounts", headers=headers, json=payload)
print("Upsert gautammmmm20 Status:", r.status_code)
print("Upsert Response:", r.json())

r_sel = requests.get(f"{SUPABASE_URL}/rest/v1/instagram_accounts?select=*", headers=headers)
print("Total accounts in Supabase DB:", len(r_sel.json()))
for acc in r_sel.json():
    print(" - Account:", acc["username"], "| Status:", acc["status"], "| Active:", acc["is_active"])
