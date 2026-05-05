import requests
from shared.config.settings import settings


class MBHClient:
    def __init__(self):
        self.base_url = settings.mbh_base_url
        self.client_id = settings.mbh_client_id
        self.api_key = settings.mbh_api_key
        self.redirect_uri = settings.mbh_redirect_uri

    def _headers(self):
        return {
            "X-IBM-Client-Id": self.client_id,
            "X-IBM-Client-Secret": self.api_key,  # csak ha az MBH doksi így kéri
            "Content-Type": "application/json",
        }

    def get_accounts(self):
        url = f"{self.base_url}/accounts"
        response = requests.get(url, headers=self._headers())
        return response.json(), response.status_code