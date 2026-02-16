from flask import Flask, jsonify, request

app = Flask(__name__)

# This is your "Secret Key" - only the dashboard should know this!
API_KEY = "sk_everdash_test_123"

# Load the data from the file we just made
import json
with open('mock_database.json', 'r') as f:
    mock_data = json.load(f)

@app.route('/api/v1/all_users', methods=['GET'])
def get_users():
    # Check if the "Client" sent the right API Key
    provided_key = request.headers.get("X-API-KEY")
    if provided_key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Send back the data!
    return jsonify(mock_data)

if __name__ == '__main__':
    # We run this on port 5001 so it doesn't crash into your dashboard (port 5000)
    app.run(port=5001, debug=True)

