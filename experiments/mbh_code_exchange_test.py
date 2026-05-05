from services.mbh_service.auth import exchange_authorization_code

code = input("Authorization code: ").strip()

status, text, headers = exchange_authorization_code(code)

print("STATUS:", status)
print("TEXT:", text)
print("HEADERS:", headers)