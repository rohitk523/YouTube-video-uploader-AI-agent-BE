"""
OAuth Callback Handler
Handles OAuth redirects from Google and processes authorization codes
"""

from fastapi import APIRouter, Request, Query, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.database import get_db
from app.services.secret_service import SecretService
from app.schemas.secret import YouTubeOAuthCallbackRequest

router = APIRouter()

@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None)
):
    """
    OAuth callback endpoint that handles the redirect from Google.
    
    This endpoint:
    1. Receives the authorization code from Google
    2. Processes it via the backend API
    3. Shows success/error message to user
    """
    
    if error:
        # OAuth error occurred
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Error</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 50px auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-align: center;
                }}
                .container {{
                    background: rgba(255, 255, 255, 0.1);
                    padding: 40px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                }}
                .error {{
                    color: #ff6b6b;
                    font-size: 18px;
                    margin: 20px 0;
                }}
                .btn {{
                    background: #4CAF50;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 8px;
                    display: inline-block;
                    margin: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ OAuth Error</h1>
                <div class="error">Error: {error}</div>
                <p>There was an error during the OAuth process. Please try again.</p>
                <a href="http://localhost:3000" class="btn">Return to App</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    if not code:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Error</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 50px auto;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-align: center;
                }
                .container {
                    background: rgba(255, 255, 255, 0.1);
                    padding: 40px;
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                }
                .error {
                    color: #ff6b6b;
                    font-size: 18px;
                    margin: 20px 0;
                }
                .btn {
                    background: #4CAF50;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 8px;
                    display: inline-block;
                    margin: 10px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ OAuth Error</h1>
                <div class="error">No authorization code received</div>
                <p>Please try the OAuth process again.</p>
                <a href="http://localhost:3000" class="btn">Return to App</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    
    # Success - show processing page
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth Success</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: 50px auto;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-align: center;
            }}
            .container {{
                background: rgba(255, 255, 255, 0.1);
                padding: 40px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }}
            .success {{
                color: #4CAF50;
                font-size: 18px;
                margin: 20px 0;
            }}
            .spinner {{
                border: 4px solid rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                border-top: 4px solid white;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            .btn {{
                background: #4CAF50;
                color: white;
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 8px;
                display: inline-block;
                margin: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ OAuth Success</h1>
            <div class="success">Authorization code received successfully!</div>
            <div class="spinner"></div>
            <p>Processing your authentication...</p>
            <p>You can close this window and return to the app.</p>
            <a href="http://localhost:3000" class="btn">Return to App</a>
        </div>
        
        <script>
            // Send the authorization code to the backend
            async function processOAuth() {{
                try {{
                    const response = await fetch('/oauth/callback/process', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            code: '{code}',
                            state: '{state or ""}'
                        }})
                    }});
                    
                    const result = await response.json();
                    console.log('OAuth callback result:', result);
                    
                    if (result.success) {{
                        // Show success message
                        document.querySelector('.success').textContent = 'Authentication completed successfully!';
                        document.querySelector('.spinner').style.display = 'none';
                        
                        // Try to notify the Flutter app (if it's listening)
                        try {{
                            if (window.opener) {{
                                window.opener.postMessage({{
                                    type: 'YOUTUBE_OAUTH_SUCCESS',
                                    authenticated: result.authenticated,
                                    user_id: result.user_id
                                }}, '*');
                            }}
                        }} catch (e) {{
                            console.log('Could not notify parent window:', e);
                        }}
                        
                        // Auto-close after 3 seconds
                        setTimeout(() => {{
                            window.close();
                        }}, 3000);
                        
                    }} else {{
                        // Show error message
                        document.querySelector('.success').textContent = 'Error: ' + (result.message || 'Authentication failed');
                        document.querySelector('.success').style.color = '#ff6b6b';
                        document.querySelector('.spinner').style.display = 'none';
                        
                        // Try to notify the Flutter app of the error
                        try {{
                            if (window.opener) {{
                                window.opener.postMessage({{
                                    type: 'YOUTUBE_OAUTH_ERROR',
                                    error: result.message || 'Authentication failed'
                                }}, '*');
                            }}
                        }} catch (e) {{
                            console.log('Could not notify parent window:', e);
                        }}
                    }}
                    
                }} catch (error) {{
                    console.error('Error processing OAuth:', error);
                    document.querySelector('.success').textContent = 'Error processing authentication';
                    document.querySelector('.success').style.color = '#ff6b6b';
                    document.querySelector('.spinner').style.display = 'none';
                }}
            }}
            
            // Process OAuth when page loads
            window.onload = processOAuth;
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@router.post("/oauth/callback/process")
async def process_oauth_callback(
    request: YouTubeOAuthCallbackRequest,
    db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    """
    Process OAuth callback and associate with the correct user.
    
    This endpoint processes the authorization code and stores tokens
    for the user who initiated the OAuth flow.
    """
    try:
        secret_service = SecretService(db)
        
        # In a production system, you would decode the state parameter to identify the user
        # For now, we'll use a simpler approach but still improved from the previous version
        
        from app.models.secret import Secret
        from sqlalchemy import select
        
        # Find all active secrets that could potentially match
        result = await db.execute(
            select(Secret).where(Secret.is_active == True).order_by(Secret.created_at.desc())
        )
        secrets = result.scalars().all()
        
        if not secrets:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "No active OAuth credentials found. Please upload credentials first."
                }
            )
        
        # Try to process OAuth for each potential user until we find one that works
        # This is a fallback approach - in production you'd use the state parameter properly
        last_error = None
        
        for secret in secrets:
            try:
                # Attempt to process the OAuth callback for this user
                callback_response = await secret_service.handle_youtube_oauth_callback(
                    user_id=secret.user_id,
                    code=request.code,
                    state=request.state
                )
                
                # If successful, return the result
                if callback_response.success:
                    return JSONResponse(
                        content={
                            "success": True,
                            "message": f"YouTube OAuth completed successfully for user {secret.user_id}",
                            "authenticated": callback_response.youtube_authenticated,
                            "user_id": str(secret.user_id)
                        }
                    )
                    
            except Exception as e:
                last_error = str(e)
                continue
        
        # If we get here, none of the users could process the OAuth callback
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": f"OAuth callback processing failed for all users. Last error: {last_error}"
            }
        )
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"OAuth processing failed: {str(e)}"
            }
        ) 