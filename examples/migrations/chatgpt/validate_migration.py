#!/usr/bin/env python3
import sys

# Ensure memanto is in path if running from source
sys.path.append("../../..")

try:
    from memanto.app.clients.sdk_client import SdkClient
except ImportError:
    print("Error: memanto SDK not found. Make sure it is installed or run from the repo root.")
    sys.exit(1)

def validate():
    print("Testing recall parity after migration...")
    try:
        client = SdkClient()
    except Exception as e:
        print(f"Failed to initialize SdkClient. Make sure MOORCHEH_API_KEY is set or backend is running. {e}")
        return

    # Golden Q&A set test
    results = client.search_memory("Does the user know Python?")
    
    found = False
    for r in results:
        if "beginner" in r.content.lower() or "python" in r.content.lower():
            found = True
            break
            
    if found:
        print("✅ SUCCESS: Found the migrated Python memory.")
    else:
        print("❌ FAILED: Could not recall Python memory.")
        
    results = client.search_memory("What allergies does the user have?")
    found = False
    for r in results:
        if "peanuts" in r.content.lower() or "vegan" in r.content.lower():
            found = True
            break
            
    if found:
        print("✅ SUCCESS: Found the migrated allergy memory.")
    else:
        print("❌ FAILED: Could not recall allergy memory.")
        
if __name__ == "__main__":
    validate()
