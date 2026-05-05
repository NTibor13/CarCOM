from services.mbh_service.auth import get_tpp_access_token

status, text, headers = get_tpp_access_token()

print("STATUS:", status)
print("TEXT:", text)
print("HEADERS:", headers)