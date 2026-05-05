from services.mbh_service.account_information import create_account_access_consent

status, text, headers = create_account_access_consent()

print("STATUS:", status)
print("TEXT:", text)
print("HEADERS:", headers)