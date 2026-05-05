from services.mbh_service.client import MBHClient

client = MBHClient()

data, status = client.get_accounts()

print("STATUS:", status)
print("DATA:", data)