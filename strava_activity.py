import requests
import json
from datetime import datetime
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading
import os
import time

class StravaAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse the query parameters
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authentication successful! You can close this window.")
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authentication failed. No code received.")

    def log_message(self, format, *args):
        # Suppress logging
        pass

def load_tokens():
    """Load stored tokens from file if they exist"""
    try:
        with open('strava_tokens.json', 'r') as f:
            tokens = json.load(f)
            # Check if token is expired
            if time.time() < tokens['expires_at']:
                return tokens
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None

def save_tokens(tokens):
    """Save tokens to file"""
    with open('strava_tokens.json', 'w') as f:
        json.dump(tokens, f)

def get_access_token(client_id, client_secret):
    """
    Get an access token using OAuth flow, reusing existing token if valid
    
    Args:
        client_id (str): Your Strava application client ID
        client_secret (str): Your Strava application client secret
        
    Returns:
        str: The access token
    """
    # Try to load existing tokens
    tokens = load_tokens()
    if tokens:
        print("Using existing access token...")
        return tokens['access_token']
    
    print("No valid token found. Starting OAuth flow...")
    
    # Start a local server to receive the OAuth callback
    server = HTTPServer(('localhost', 8000), StravaAuthHandler)
    server.auth_code = None
    
    # Start the server in a separate thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    # Open the authorization URL in the browser
    auth_url = (
        f"https://www.strava.com/oauth/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri=http://localhost:8000&"
        f"approval_prompt=force&"
        f"scope=activity:read_all,activity:write"
    )
    webbrowser.open(auth_url)
    
    # Wait for the authorization code
    while server.auth_code is None:
        pass
    
    # Stop the server
    server.shutdown()
    server.server_close()
    
    # Exchange the authorization code for tokens
    token_url = "https://www.strava.com/oauth/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": server.auth_code,
        "grant_type": "authorization_code"
    }
    
    response = requests.post(token_url, data=data)
    response.raise_for_status()
    
    # Save the tokens
    tokens = response.json()
    tokens['expires_at'] = time.time() + tokens['expires_in']
    save_tokens(tokens)
    
    return tokens['access_token']

def get_recent_activity(access_token, athlete_id):
    """
    Fetch the most recent activity for a specific Strava athlete
    
    Args:
        access_token (str): Your Strava API access token
        athlete_id (int): The Strava athlete ID
        
    Returns:
        dict: The most recent activity data
    """
    # Strava API endpoint for athlete activities
    url = f"https://www.strava.com/api/v3/athletes/{athlete_id}/activities"
    
    # Headers with authorization
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    # Parameters to get the most recent activity
    params = {
        'per_page': 1,  # Get only the most recent activity
        'page': 1
    }
    
    try:
        # Make the GET request
        response = requests.get(url, headers=headers, params=params)
        
        # If token is expired, remove the token file and retry
        if response.status_code == 401:
            print("Token expired. Removing token file...")
            os.remove('strava_tokens.json')
            return None
            
        response.raise_for_status()  # Raise an exception for other bad status codes
        
        # Parse the response
        activities = response.json()
        
        if not activities:
            print(f"No activities found for athlete {athlete_id}")
            return None
            
        # Get the most recent activity
        return activities[0]
        
    except requests.exceptions.RequestException as e:
        print(f"Error making request: {e}")
        return None

def update_activity_description(access_token, activity_id, description):
    """
    Update an activity's description
    
    Args:
        access_token (str): Your Strava API access token
        activity_id (int): The activity ID to update
        description (str): The new description
        
    Returns:
        bool: True if successful, False otherwise
    """
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    data = {
        'description': description
    }
    
    try:
        response = requests.put(url, headers=headers, data=data)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error updating activity: {e}")
        return False

def count_words(text):
    """
    Count the number of words in a string
    
    Args:
        text (str): The text to count words in
        
    Returns:
        int: The number of words
    """
    return len(text.split())

if __name__ == "__main__":
    # Replace these with your Strava application credentials
    CLIENT_ID = "53125"
    CLIENT_SECRET = "427e02289db9cea08b79d7c325e8f21a36b1624e"
    
    # The athlete ID you provided
    ATHLETE_ID = 32922412
    
    print("Getting access token...")
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)
    print("Access token received!")
    
    print("\nFetching most recent activity...")
    activity = get_recent_activity(access_token, ATHLETE_ID)
    
    if activity:
        print("\nUpdating activity description...")
        current_description = activity.get('description', '')
        title = activity.get('name', '')
        word_count = count_words(title)
        
        # Remove any existing yap score from the description
        if "yap score:" in current_description:
            current_description = current_description.split("yap score:")[0].strip()
        
        new_description = f"{current_description}\n\nyap score: {word_count}"
        
        if update_activity_description(access_token, activity['id'], new_description):
            print(f"Activity description updated successfully! Yap score: {word_count}")
        else:
            print("Failed to update activity description.") 