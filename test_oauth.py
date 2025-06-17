#!/usr/bin/env python3
"""
OAuth 2.0 Test Script
Demonstrates how to use the OAuth 2.0 endpoints for authentication
"""

import asyncio
import httpx
import json
from typing import Dict, Any


class OAuth2Client:
    """Simple OAuth 2.0 client for testing"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.access_token = None
        self.refresh_token = None
    
    async def register_user(self, email: str, password: str, username: str = None) -> Dict[str, Any]:
        """Register a new user"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/oauth/register",
                json={
                    "email": email,
                    "password": password,
                    "username": username
                }
            )
            if response.status_code == 201:
                data = response.json()
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                return data
            else:
                raise Exception(f"Registration failed: {response.text}")
    
    async def get_token_password_grant(self, username: str, password: str, scopes: list = None) -> Dict[str, Any]:
        """Get token using password grant type"""
        if scopes is None:
            scopes = ["read", "write", "upload", "youtube"]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/oauth/token",
                data={
                    "grant_type": "password",
                    "username": username,
                    "password": password,
                    "scope": " ".join(scopes)
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                return data
            else:
                raise Exception(f"Token request failed: {response.text}")
    
    async def refresh_access_token(self) -> Dict[str, Any]:
        """Refresh access token using refresh token"""
        if not self.refresh_token:
            raise Exception("No refresh token available")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/oauth/token/refresh",
                json={"refresh_token": self.refresh_token}
            )
            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get("access_token")
                if "refresh_token" in data:
                    self.refresh_token = data.get("refresh_token")
                return data
            else:
                raise Exception(f"Token refresh failed: {response.text}")
    
    async def get_user_info(self) -> Dict[str, Any]:
        """Get user information using access token"""
        if not self.access_token:
            raise Exception("No access token available")
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/oauth/userinfo",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"User info request failed: {response.text}")
    
    async def introspect_token(self, token: str = None) -> Dict[str, Any]:
        """Introspect a token"""
        token_to_check = token or self.access_token
        if not token_to_check:
            raise Exception("No token to introspect")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/oauth/introspect",
                data={"token": token_to_check},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Token introspection failed: {response.text}")
    
    async def revoke_token(self, token: str = None) -> Dict[str, Any]:
        """Revoke a token"""
        token_to_revoke = token or self.access_token
        if not token_to_revoke:
            raise Exception("No token to revoke")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/oauth/revoke",
                data={"token": token_to_revoke},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Token revocation failed: {response.text}")


async def main():
    """Test the OAuth 2.0 functionality"""
    client = OAuth2Client()
    
    print("🔐 OAuth 2.0 Authentication Test")
    print("=" * 50)
    
    try:
        # Test user registration
        print("\n1. Registering a new user...")
        user_data = await client.register_user(
            email="test@example.com",
            password="testpassword123",
            username="testuser"
        )
        print(f"✅ User registered successfully!")
        print(f"   User ID: {user_data['user']['id']}")
        print(f"   Email: {user_data['user']['email']}")
        print(f"   Access Token: {user_data['access_token'][:20]}...")
        
        # Test token introspection
        print("\n2. Introspecting access token...")
        introspection = await client.introspect_token()
        print(f"✅ Token is active: {introspection['active']}")
        print(f"   Scopes: {introspection.get('scope', 'N/A')}")
        print(f"   Subject: {introspection.get('sub', 'N/A')}")
        
        # Test user info endpoint
        print("\n3. Getting user information...")
        user_info = await client.get_user_info()
        print(f"✅ User info retrieved!")
        print(f"   Username: {user_info.get('username', 'N/A')}")
        print(f"   Email: {user_info['email']}")
        print(f"   Active: {user_info['is_active']}")
        
        # Test token refresh
        print("\n4. Refreshing access token...")
        refresh_data = await client.refresh_access_token()
        print(f"✅ Token refreshed successfully!")
        print(f"   New Access Token: {refresh_data['access_token'][:20]}...")
        
        # Test OAuth 2.0 password grant (alternative login)
        print("\n5. Testing OAuth 2.0 password grant...")
        token_data = await client.get_token_password_grant(
            username="test@example.com",
            password="testpassword123",
            scopes=["read", "write", "upload"]
        )
        print(f"✅ OAuth token obtained!")
        print(f"   Token Type: {token_data['token_type']}")
        print(f"   Expires In: {token_data['expires_in']} seconds")
        print(f"   Scopes: {token_data.get('scope', 'N/A')}")
        
        # Test token revocation
        print("\n6. Revoking access token...")
        revoke_response = await client.revoke_token()
        print(f"✅ Token revoked: {revoke_response['message']}")
        
        print("\n🎉 All OAuth 2.0 tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code) 