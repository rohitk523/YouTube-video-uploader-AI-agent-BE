# OAuth 2.0 Authentication System

This document describes the **unified OAuth 2.0 authentication system** for the YouTube Shorts Creator API.

## Overview

The API uses **OAuth 2.0 as the single authentication method** with the following features:

- **RFC 6749 compliant** OAuth 2.0 implementation
- **JWT-based tokens** with configurable expiration
- **Scope-based authorization** for fine-grained access control
- **Multiple grant types** (Password, Refresh Token, Authorization Code)
- **Complete user management** (registration, profile, password)
- **Token introspection and revocation** (RFC 7662, RFC 7009)
- **OpenID Connect compatible** UserInfo endpoint

## Endpoints

### OAuth 2.0 & User Management (`/api/v1/oauth/`)

| Endpoint | Method | Description | Scopes Required |
|----------|--------|-------------|-----------------|
| `/register` | POST | User registration | None |
| `/token` | POST | Token endpoint (password grant, refresh token) | None |
| `/userinfo` | GET | Get user information (OpenID Connect) | `read` |
| `/profile` | PUT | Update user profile | `write` |
| `/change-password` | POST | Change password | `write` |
| `/logout` | POST | User logout | Any |
| `/authorize` | POST | Authorization endpoint (code grant) | None |
| `/token/refresh` | POST | Refresh access token | None |
| `/introspect` | POST | Token introspection (RFC 7662) | None |
| `/revoke` | POST | Token revocation (RFC 7009) | None |

## Supported Grant Types

### 1. Password Grant (Resource Owner Password Credentials)

**Use Case**: First-party applications where you trust the client with user credentials.

```bash
curl -X POST "http://localhost:8000/api/v1/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=user@example.com&password=userpass&scope=read write upload"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "scope": "read write upload"
}
```

### 2. Refresh Token Grant

**Use Case**: Obtain a new access token using a refresh token.

```bash
curl -X POST "http://localhost:8000/api/v1/oauth/token/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}'
```

### 3. Authorization Code Grant (Simplified)

**Use Case**: Third-party applications (web apps, mobile apps).

```bash
# Step 1: Get authorization code
curl -X POST "http://localhost:8000/api/v1/oauth/authorize" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "response_type=code&client_id=youtube-shorts-web&redirect_uri=https://app.example.com/callback&scope=read write&state=random-state"

# Step 2: Exchange code for tokens (implementation would follow)
```

## Scopes

The API supports the following scopes:

| Scope | Description |
|-------|-------------|
| `read` | Read access to user data and content |
| `write` | Write access to user data |
| `upload` | Upload files and create content |
| `youtube` | Access to YouTube operations |
| `admin` | Administrative access (superusers only) |

## Usage Examples

### 1. Register a New User

```python
import httpx

async def register_user():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/oauth/register",
            json={
                "email": "user@example.com",
                "password": "secure_password123",
                "username": "myusername"
            }
        )
        return response.json()
```

### 2. Get Access Token

```python
async def get_access_token(email: str, password: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/oauth/token",
            data={
                "grant_type": "password",
                "username": email,
                "password": password,
                "scope": "read write upload youtube"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        return response.json()
```

### 3. Use Access Token for API Calls

```python
async def get_user_info(access_token: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/oauth/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        return response.json()
```

### 4. Refresh Access Token

```python
async def refresh_token(refresh_token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/oauth/token/refresh",
            json={"refresh_token": refresh_token}
        )
        return response.json()
```

## Configuration

### Environment Variables

Add these to your `.env.dev` or `.env.prod` file:

```bash
# Security Settings
SECRET_KEY=your-256-bit-secret-key-change-in-production
CORS_ORIGINS_STR=http://localhost:3000,http://localhost:8080

# OAuth 2.0 Settings
OAUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
OAUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
OAUTH_ALGORITHM=HS256

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/youtube_shorts
```

### JWT Token Configuration

Tokens are configured in `app/services/auth.py`:

- **Access Token**: 30 minutes expiration (configurable)
- **Refresh Token**: 7 days expiration (configurable)
- **Authorization Code**: 10 minutes expiration
- **Algorithm**: HS256 (configurable)

## Security Features

### 1. Password Hashing
- Uses `bcrypt` with salt for secure password storage
- Configurable work factor for future-proofing

### 2. JWT Security
- Cryptographically signed tokens
- Short-lived access tokens with refresh mechanism
- Scope-based access control

### 3. Input Validation
- Pydantic models for request/response validation
- Email format validation
- Password strength requirements

### 4. CORS Protection
- Configurable allowed origins
- Secure headers middleware

## Testing

### Run the Test Script

```bash
# Install test dependencies
pip install httpx

# Run OAuth 2.0 tests
python test_oauth.py
```

### Manual Testing with cURL

1. **Register User:**
```bash
curl -X POST "http://localhost:8000/api/v1/oauth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123","username":"testuser"}'
```

2. **Get Token:**
```bash
curl -X POST "http://localhost:8000/api/v1/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=test@example.com&password=testpass123&scope=read write"
```

3. **Use Token:**
```bash
curl -X GET "http://localhost:8000/api/v1/oauth/userinfo" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Integration with Frontend

### React Example

```typescript
class AuthService {
  private baseURL = 'http://localhost:8000';
  
  async login(email: string, password: string) {
    const response = await fetch(`${this.baseURL}/api/v1/oauth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'password',
        username: email,
        password: password,
        scope: 'read write upload youtube'
      })
    });
    
    return response.json();
  }
  
  async apiCall(endpoint: string, token: string) {
    const response = await fetch(`${this.baseURL}${endpoint}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });
    
    return response.json();
  }
}
```

## Production Considerations

### 1. Secret Key Management
- Use a cryptographically secure secret key (256-bit)
- Rotate secrets regularly
- Use environment variables or secret management services

### 2. HTTPS
- Always use HTTPS in production
- Configure secure cookie settings
- Implement HSTS headers

### 3. Rate Limiting
- Implement rate limiting on token endpoints
- Use Redis or similar for distributed rate limiting

### 4. Token Storage
- Store refresh tokens securely
- Implement token revocation lists
- Consider token encryption for sensitive data

### 5. Monitoring
- Log authentication attempts
- Monitor for suspicious activity
- Set up alerts for failed authentications

## Troubleshooting

### Common Issues

1. **Invalid Token Error**
   - Check token expiration
   - Verify token format and signature
   - Ensure correct Authorization header format

2. **Scope Insufficient**
   - Request appropriate scopes during token generation
   - Check user permissions in database

3. **Database Connection Issues**
   - Verify PostgreSQL is running
   - Check database credentials
   - Ensure database tables are created

### Debug Mode

Enable debug mode for detailed error messages:

```bash
export DEBUG=true
```

## API Documentation

Full API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs for error details
3. Consult the API documentation
4. Test with the provided test script 