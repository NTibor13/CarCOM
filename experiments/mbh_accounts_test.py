from services.mbh_service.account_information import get_accounts

status, text, headers = get_accounts()

print("ACCOUNTS STATUS:", status)
print("ACCOUNTS TEXT:", text)