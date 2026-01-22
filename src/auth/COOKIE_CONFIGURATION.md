# Cookie Configuration for Cross-Application Authentication

## Overview

This Privy authentication middleware is designed to work across multiple applications by reading cookies set by other applications (e.g., your frontend or another backend service).

## Current Configuration

The FastAPI application is already configured to support cross-origin cookies:

### CORS Middleware (in `src/main.py`)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # From ALLOWED_ORIGINS env var
    allow_credentials=True,          # ✅ Required for cookies
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

**Key Setting**: `allow_credentials=True` enables the server to receive cookies from cross-origin requests.

## How the Middleware Reads Cookies

The Privy auth middleware reads the `privy-id-token` cookie in three ways:

1. **Header** - Checks for `privy-id-token` header
2. **Cookie** - Checks for `privy-id-token` cookie (parsed by FastAPI)
3. **Manual parsing** - Fallback that manually parses the `Cookie` header

This ensures maximum compatibility regardless of how the cookie is sent.

## Cookie Requirements for Cross-Origin Use

For cookies to work across different applications/domains, the **application that SETS the cookie** (typically your frontend or auth service) must configure the cookie with:

### Required Cookie Attributes

```javascript
// Example: Setting cookie in frontend/other application
document.cookie = "privy-id-token=<token>; SameSite=None; Secure; Domain=.example.com; Path=/";
```

| Attribute | Value | Purpose |
|-----------|-------|---------|
| `SameSite` | `None` | Allows cookie to be sent with cross-site requests |
| `Secure` | `true` | Required when `SameSite=None`; cookie only sent over HTTPS |
| `Domain` | `.example.com` | Makes cookie available to all subdomains |
| `Path` | `/` | Makes cookie available to all paths |

### Important Notes

1. **HTTPS Required**: Cross-origin cookies with `SameSite=None` MUST be sent over HTTPS in production.

2. **Domain Configuration**: 
   - For cookies to work across `app1.example.com` and `app2.example.com`, set `Domain=.example.com`
   - For cookies to work across completely different domains (e.g., `example.com` and `other.com`), you cannot use cookies - use headers instead

3. **This Backend Only READS Cookies**: This FastAPI application does not set the `privy-id-token` cookie. It only reads it. The cookie must be set by:
   - Your frontend application (after Privy login)
   - Another backend service
   - The Privy SDK in your frontend

## Configuration Checklist

### ✅ Backend (This Application)
- [x] CORS middleware with `allow_credentials=True`
- [x] CORS `allow_origins` includes the frontend domain
- [x] Middleware reads cookies from headers and Cookie header
- [x] No cookie-setting logic (read-only)

### ⚠️ Frontend/Cookie-Setting Application

Ensure your frontend or the application that sets the cookie:

- [ ] Sets `SameSite=None` on the cookie
- [ ] Sets `Secure=true` on the cookie
- [ ] Sets appropriate `Domain` (e.g., `.example.com` for subdomain sharing)
- [ ] Sets `Path=/` to make cookie available everywhere
- [ ] Uses HTTPS in production (required for `SameSite=None`)

### ⚠️ Frontend API Calls

When making requests from frontend to this backend:

- [ ] Include `credentials: 'include'` in fetch/axios calls
- [ ] Set `withCredentials: true` for axios
- [ ] Ensure frontend domain is in `ALLOWED_ORIGINS` env var

## Example Frontend Configuration

### Fetch API
```javascript
fetch('https://api.example.com/api/endpoint', {
  method: 'GET',
  credentials: 'include',  // ✅ Required to send cookies
  headers: {
    'Content-Type': 'application/json'
  }
})
```

### Axios
```javascript
axios.get('https://api.example.com/api/endpoint', {
  withCredentials: true  // ✅ Required to send cookies
})
```

### Setting the Cookie After Privy Login
```javascript
// After successful Privy authentication
const privyToken = await privy.getAccessToken();

// Option 1: Let Privy SDK handle it (recommended)
// The Privy SDK usually sets the cookie automatically

// Option 2: Manually set the cookie
document.cookie = `privy-id-token=${privyToken}; SameSite=None; Secure; Domain=.example.com; Path=/; Max-Age=86400`;

// Option 3: Send in header instead
// If cross-domain cookies don't work, send as header
fetch('https://api.example.com/api/endpoint', {
  headers: {
    'privy-id-token': privyToken  // ✅ Alternative to cookies
  }
})
```

## Debugging Cookie Issues

### Check if Cookie is Being Sent

In your browser's Developer Tools:
1. Go to Network tab
2. Click on a request to your API
3. Look at Request Headers
4. Check if `Cookie: privy-id-token=...` is present

### Common Issues

#### Cookie Not Sent
- Check `SameSite=None` and `Secure` are set when creating cookie
- Verify you're using HTTPS
- Verify `credentials: 'include'` in fetch calls
- Check if cookie domain matches

#### Cookie Rejected
- Verify `allow_credentials=True` in CORS middleware
- Check `ALLOWED_ORIGINS` includes the frontend domain
- Don't use `allow_origins=["*"]` with credentials

#### Token Invalid
- Check `PRIVY_APP_ID` and `PRIVY_APP_SECRET` are correct
- Verify token hasn't expired
- Check network connectivity to auth.privy.io

## Alternative: Header-Based Authentication

If cookies are problematic, you can use header-based authentication instead:

```javascript
// Frontend sends token in header
const token = await privy.getAccessToken();

fetch('https://api.example.com/api/endpoint', {
  headers: {
    'privy-id-token': token  // ✅ Works without cookie configuration
  }
})
```

The middleware checks headers first, so this works without any backend changes.

## Environment Variables

Make sure these are set:

```bash
# Frontend domain(s) that will send requests
ALLOWED_ORIGINS=https://app.example.com,https://admin.example.com

# Privy configuration
PRIVY_APP_ID=your_app_id
PRIVY_APP_SECRET=your_app_secret
```

## Testing Cross-Origin Cookies Locally

For local development with cross-origin cookies:

1. **Use HTTPS locally** (required for `SameSite=None`)
   - Use tools like `mkcert` to create local SSL certificates
   - Or use a tunneling service like ngrok

2. **Use different subdomains**
   - Add to `/etc/hosts`: `127.0.0.1 frontend.local backend.local`
   - Access via `https://frontend.local:3000` and `https://backend.local:8000`

3. **Or use header-based auth in development**
   - Simpler for local development
   - Switch to cookies in production

## Summary

**No changes needed to this backend** for cross-origin cookie support. The CORS configuration with `allow_credentials=True` already supports it.

**Action required in frontend/cookie-setting application**:
1. Set cookies with `SameSite=None; Secure`
2. Use appropriate `Domain` for sharing across subdomains
3. Include `credentials: 'include'` in API calls
4. Ensure HTTPS in production

The middleware will automatically read cookies regardless of their configuration, but cross-origin functionality requires the cookie to be set correctly by the application that creates it.

