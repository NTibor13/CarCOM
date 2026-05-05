# experiments/mbh_transactions_test.py

import json
from services.mbh_service.auth import exchange_authorization_code
from services.mbh_service.account_information import get_transactions

code = input("Authorization code: ").strip()
account_id = input("AccountId: ").strip()

status, text, _ = exchange_authorization_code(code)

if status != 200:
    print("TOKEN STATUS:", status)
    print("TOKEN TEXT:", text)
    raise SystemExit(1)

access_token = json.loads(text)["access_token"]

status, text, _ = get_transactions(access_token, account_id)

print("TRANSACTIONS STATUS:", status)
print("TRANSACTIONS TEXT:", text)