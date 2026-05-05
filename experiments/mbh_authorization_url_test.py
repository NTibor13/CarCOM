from services.mbh_service.auth import build_authorization_url

consent_id = input("ConsentId: ").strip()

url = build_authorization_url(consent_id)

print("\nNyisd meg ezt a linket böngészőben:\n")
print(url)