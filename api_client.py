import requests

# This is the address of our Librarian
MOCK_SERVER_URL = "http://127.0.0.1:5001/api/v1/all_users"
# This is the secret password we set in mock_server.py
API_KEY = "sk_everdash_test_123"

def fetch_all_participants():
    """
    This function walks over to the mock server, 
    shows the ID card, and brings back the user data.
    """
    headers = {"X-API-KEY": API_KEY}
    
    try:
        # We 'GET' the data from the server
        response = requests.get(MOCK_SERVER_URL, headers=headers)
        
        # If the librarian says 'OK' (status 200), we return the list of people
        if response.status_code == 200:
            data = response.json()
            return data.get("participants", [])
        else:
            print(f"Librarian said no: {response.status_code}")
            return []
            
    except Exception as e:
        print(f"The bridge broke: {e}")
        return []
    
    