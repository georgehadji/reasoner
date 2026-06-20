# Phase 2 Implementation Plan — Auth Integration: Supabase Adapter + FastAPI Dependencies

> **Goal:** Secure the API with real user authentication without breaking legacy API-key support.  
> **Duration:** 5 working days (Week 2)  
> **Deliverable:** JWT-based auth on all protected routes, Supabase SSR frontend integration, legacy API-key fallback behind feature flag.  
> **Constraint:** All existing tests pass. Legacy `AuthManager` continues to work when `ENABLE_LEGACY_API_KEY=true`.

---

## 0. Pre-Flight Checklist

```bash
# 1. Verify Phase 1 is complete and green
python -m pytest tests/ --tb=short -q
# Expected: all green including test_saas_*

# 2. Install new dependencies
pip install supabase-py httpx PyJWT

# 3. Verify Supabase project exists (or create one at https://supabase.com)
# Required: Project URL + anon key + service role key

# 4. Add env vars to .env (DO NOT COMMIT)
cat >> .env << 'EOF'
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
ENABLE_LEGACY_API_KEY=true
JWT_SECRET_KEY=<64-char-random-hex-for-local-dev>
EOF
```

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI (api/__init__.py)                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  SecurityHeaders │  │  CORS           │  │  RateLimiter    │  │
│  │  Middleware      │  │  Middleware     │  │  Middleware     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                              │                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  FastAPI Dependency Injection Chain                         │  │
│  │                                                             │  │
│  │  optional_auth / require_auth ──► resolves User OR APIKey   │  │
│  │         │                                                   │  │
│  │         ▼                                                   │  │
│  │  UnifiedAuthResolver                                        │  │
│  │    ├─ Bearer token looks like JWT? ──► AuthPort (Supabase)  │  │
│  │    └─ Bearer token looks like API key? ──► AuthManager      │  │
│  │         (legacy, only if ENABLE_LEGACY_API_KEY=true)        │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │                                    │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Route: /api/run                                            │  │
│  │    user: User = Depends(get_current_user)                   │  │
│  │    quota: QuotaResult = Depends(check_quota)                │  │
│  │    ...                                                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Decision:** A single `UnifiedAuthResolver` inspects the incoming bearer token. If it looks like a JWT (contains two dots), it routes to `AuthPort` (Supabase). If it looks like an API key and `ENABLE_LEGACY_API_KEY=true`, it routes to the legacy `AuthManager`. This avoids forcing clients to change headers or auth mechanisms during migration.

⚠️ **CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 2.1–2.4):**
- 2.1: `_auth_adapter` global is not thread-safe — wrap with `threading.Lock()`
- 2.2: UUID creation from hash can overflow — use SHA-256 + slice safely
- 2.3: JWT heuristic (2 dots) is bypassable — use explicit prefix (e.g., `jwt_`) or check segment lengths
- 2.4: `create_token()` must be `async` to match AuthPort protocol — wrap sync code with `asyncio.to_thread()`
- 2.6: No JWT revocation list — add Redis-backed revocation set for logout

---

## 2. Day-by-Day Implementation Schedule

### Day 1 — Supabase Adapter + Local JWT Adapter

**Files:**
- `src/reasoner/infrastructure/auth/__init__.py`
- `src/reasoner/infrastructure/auth/supabase_adapter.py`
- `src/reasoner/infrastructure/auth/local_adapter.py`

**Task 2.1.1 — Supabase Auth Adapter**

```python
# src/reasoner/infrastructure/auth/supabase_adapter.py
"""
Supabase Auth Adapter — Implements AuthPort using supabase-py.

This is the production auth adapter. It validates JWTs against
Supabase's auth server and returns canonical User entities.
"""

from __future__ import annotations

import logging
from uuid import UUID

from reasoner.domain.saas import User
from reasoner.application.ports.auth_port import AuthPort
from reasoner.auth import AuthenticationError

logger = logging.getLogger(__name__)


class SupabaseAuthAdapter(AuthPort):
    """
    Production auth adapter using Supabase Auth.

    Features:
    - JWT validation via Supabase server-side verification
    - Caching recommendation: wrap in AuthService with Redis TTL
    """

    def __init__(self, supabase_url: str, supabase_service_key: str):
        from supabase import create_client, Client

        self._client: Client = create_client(supabase_url, supabase_service_key)

    async def authenticate(self, token: str) -> User:
        """
        Validate a Supabase JWT access token.

        Args:
            token: Bearer token from Authorization header.

        Returns:
            Canonical User entity.

        Raises:
            AuthenticationError: If token is invalid or expired.
        """
        try:
            # Supabase server-side JWT verification
            response = self._client.auth.get_user(token)
            supabase_user = response.user

            if supabase_user is None:
                raise AuthenticationError("Invalid or expired token", status_code=401)

            return User(
                id=UUID(supabase_user.id),
                email=supabase_user.email or "",
                display_name=supabase_user.user_metadata.get("full_name")
                if supabase_user.user_metadata
                else None,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.warning("Supabase auth validation failed: %s", exc)
            raise AuthenticationError(f"Auth validation failed: {exc}", status_code=401)

    async def refresh_session(self, token: str) -> str:
        """Not implemented for server-side validation."""
        raise NotImplementedError("Refresh is handled client-side with Supabase")
```

**Task 2.1.2 — Local JWT Adapter (Dev/Test)**

```python
# src/reasoner/infrastructure/auth/local_adapter.py
"""
Local Auth Adapter — Implements AuthPort using local JWT signing.

Used for:
- Development without Supabase connectivity
- Unit tests (deterministic, no network)
- CI pipelines where external auth is undesirable
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

import jwt

from reasoner.domain.saas import User
from reasoner.application.ports.auth_port import AuthPort
from reasoner.auth import AuthenticationError

logger = logging.getLogger(__name__)


class LocalAuthAdapter(AuthPort):
    """
    Development auth adapter using local HS256 JWT.

    Generates and validates tokens with a local secret.
    NEVER use in production.
    """

    def __init__(self, secret: str | None = None):
        self._secret = secret or os.environ.get("JWT_SECRET_KEY", "dev-secret-do-not-use")
        self._algorithm = "HS256"

    def create_token(
        self,
        user_id: str,
        email: str,
        display_name: str | None = None,
        expires_in_hours: int = 24,
    ) -> str:
        """Create a local JWT for testing."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "email": email,
            "name": display_name,
            "iat": now,
            "exp": now + timedelta(hours=expires_in_hours),
            "iss": "reasoner-local",
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    async def authenticate(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["sub", "exp"]},
            )
            return User(
                id=UUID(payload["sub"]),
                email=payload.get("email", ""),
                display_name=payload.get("name"),
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired", status_code=401)
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError(f"Invalid token: {exc}", status_code=401)

    async def refresh_session(self, token: str) -> str:
        raise NotImplementedError("Local adapter does not support refresh")
```

**Task 2.1.3 — Adapter Factory**

```python
# src/reasoner/infrastructure/auth/__init__.py
"""
Auth adapter factory.

Selects the appropriate auth adapter based on environment settings.
"""

from __future__ import annotations

import os
from typing import Optional

from reasoner.application.ports.auth_port import AuthPort


_auth_adapter: Optional[AuthPort] = None


def get_auth_adapter() -> AuthPort:
    """Get or create the global auth adapter."""
    global _auth_adapter
    if _auth_adapter is not None:
        return _auth_adapter

    env = os.environ.get("ENVIRONMENT", "development")
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if env == "production" and supabase_url and supabase_service_key:
        from .supabase_adapter import SupabaseAuthAdapter
        _auth_adapter = SupabaseAuthAdapter(supabase_url, supabase_service_key)
    elif env == "testing":
        from .local_adapter import LocalAuthAdapter
        _auth_adapter = LocalAuthAdapter()
    else:
        # Development fallback: try Supabase, fall back to local
        if supabase_url and supabase_service_key:
            try:
                from .supabase_adapter import SupabaseAuthAdapter
                _auth_adapter = SupabaseAuthAdapter(supabase_url, supabase_service_key)
            except Exception:
                from .local_adapter import LocalAuthAdapter
                _auth_adapter = LocalAuthAdapter()
        else:
            from .local_adapter import LocalAuthAdapter
            _auth_adapter = LocalAuthAdapter()

    return _auth_adapter


def set_auth_adapter(adapter: AuthPort) -> None:
    """Override the auth adapter (useful for tests)."""
    global _auth_adapter
    _auth_adapter = adapter
```

**Day 1 Acceptance Criteria:**
- [ ] `python -c "from reasoner.infrastructure.auth import get_auth_adapter; print(type(get_auth_adapter()))"` returns an adapter instance.
- [ ] Local adapter test: create token → authenticate → returns correct User.
- [ ] `pytest tests/test_saas_auth_adapter.py` passes.
- [ ] Full regression suite still passes.

---

### Day 2 — Unified Auth Dependencies

**Files:**
- `src/reasoner/api/dependencies.py` (new)
- `src/reasoner/api/saas_router.py` (new)
- Modifications to `src/reasoner/api/__init__.py`

**Task 2.2.1 — Create `src/reasoner/api/dependencies.py`**

```python
"""
FastAPI Dependency Injectors for SaaS Auth.

These functions are used as FastAPI Depends() callables.
They resolve authentication and authorization without
polluting route handlers with auth logic.
"""

from __future__ import annotations

import os
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from reasoner.domain.saas import User, SubscriptionTier
from reasoner.application.ports.auth_port import AuthPort
from reasoner.application.services.auth_service import AuthService
from reasoner.infrastructure.auth import get_auth_adapter
from reasoner.auth import AuthenticationError as LegacyAuthError

security = HTTPBearer(auto_error=False)


def _looks_like_jwt(token: str) -> bool:
    """Heuristic: JWTs have exactly 2 dots separating 3 base64 segments."""
    return token.count(".") == 2


async def _resolve_auth_token(token: str) -> User:
    """
    Unified token resolution.

    Strategy:
    1. If token looks like JWT → route to AuthPort (Supabase/Local)
    2. Else if ENABLE_LEGACY_API_KEY=true → route to legacy AuthManager
    3. Else → reject
    """
    if _looks_like_jwt(token):
        adapter: AuthPort = get_auth_adapter()
        service = AuthService(adapter)
        return await service.authenticate(token)

    # Legacy API key path (only if explicitly enabled)
    if os.environ.get("ENABLE_LEGACY_API_KEY", "false").lower() == "true":
        from reasoner.auth import get_auth_manager
        auth_manager = get_auth_manager()
        try:
            api_key = await auth_manager.authenticate(token)
            # Map legacy API key to canonical User
            # Use key hash as deterministic user_id
            return User(
                id=UUID(int=int(api_key.key_hash[:32], 16)),
                email=f"apikey-{api_key.key_hash[:8]}@internal",
                display_name=api_key.name,
            )
        except LegacyAuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)

    raise HTTPException(
        status_code=401,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """
    Require valid authentication (JWT or legacy API key).

    Raises HTTPException 401 if missing or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return await _resolve_auth_token(credentials.credentials)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Optional authentication — returns None if no valid credentials."""
    if not credentials:
        return None
    try:
        return await _resolve_auth_token(credentials.credentials)
    except Exception:
        return None


def require_tier(min_tier: SubscriptionTier):
    """
    Factory that returns a FastAPI dependency enforcing minimum subscription tier.

    Usage:
        @app.post("/api/premium-only")
        async def premium_route(user: User = Depends(require_tier(SubscriptionTier.PRO))):
            ...
    """
    async def checker(user: User = Depends(get_current_user)) -> User:
        # TODO: In Phase 3, fetch subscription from DB and compare tiers.
        # For Phase 2, all authenticated users pass (auth gate only).
        # Placeholder logic:
        tier_order = {SubscriptionTier.FREE: 0, SubscriptionTier.PRO: 1, SubscriptionTier.ENTERPRISE: 2}
        # user_tier = await get_user_subscription_tier(user.id)
        # if tier_order[user_tier] < tier_order[min_tier]:
        #     raise HTTPException(status_code=403, detail=f"Requires {min_tier.value} tier")
        return user

    return checker
```

**Task 2.2.2 — Create `src/reasoner/api/saas_router.py`**

```python
"""
SaaS Router — All new SaaS-related API endpoints.

This router is mounted in api/__init__.py to keep the main file
from growing uncontrollably.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from reasoner.domain.saas import User
from reasoner.api.dependencies import get_current_user, get_optional_user

router = APIRouter(prefix="/api", tags=["saas"])


@router.get("/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
    }


@router.get("/auth/me/optional")
async def get_me_optional(user: User | None = Depends(get_optional_user)):
    """Return user if authenticated, null otherwise. Useful for UI state hydration."""
    if user is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
    }
```

**Task 2.2.3 — Modify `src/reasoner/api/__init__.py`**

Add these imports near the top (after existing auth imports):

```python
# SaaS auth dependencies
from reasoner.api.dependencies import get_current_user, get_optional_user, require_tier
from reasoner.domain.saas import User

# Mount SaaS router
from reasoner.api import saas_router
app.include_router(saas_router.router)
```

Modify the `/api/run` endpoint to accept the new auth dependency:

```python
@app.post("/api/run")
async def run_pipeline(
    request: Request,
    req: RunRequest,
    user: User | None = Depends(get_optional_user),   # NEW: SaaS auth
    authenticated = Depends(optional_auth),             # OLD: legacy API key (kept for compat)
    rate_limit_checked = Depends(check_rate_limit)
):
    """
    Run pipeline with optional authentication and rate limiting.
    """
    # TODO Phase 3: if user is None and ENABLE_LEGACY_API_KEY=false → 401
    # TODO Phase 3: use user.id for rate limit bucket and quota check
    return StreamingResponse(
        run_stream_cached(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-RateLimit-Limit": str(request.state.rate_limit_info.get("limit_minute")),
            "X-RateLimit-Remaining": str(request.state.rate_limit_info.get("remaining_minute")),
        },
    )
```

**Day 2 Acceptance Criteria:**
- [ ] `GET /api/auth/me` with no token → 401.
- [ ] `GET /api/auth/me` with valid local JWT → returns `{id, email, display_name}`.
- [ ] `GET /api/auth/me/optional` with no token → `{"authenticated": false}`.
- [ ] `POST /api/run` still works without auth (legacy mode).
- [ ] Full regression suite still passes.

---

### Day 3 — Frontend Auth Integration (Next.js + Supabase SSR)

**Files:**
- `ui-next/src/lib/supabase.ts`
- `ui-next/src/lib/auth.ts`
- `ui-next/src/stores/app-store.ts` (additive changes)
- `ui-next/src/app/providers.tsx` (modification)

**Task 2.3.1 — Supabase Client Setup**

```typescript
// ui-next/src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true,
  },
});
```

**Task 2.3.2 — Auth Helpers**

```typescript
// ui-next/src/lib/auth.ts
import { supabase } from './supabase';

export async function getSession() {
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  return data.session;
}

export async function getCurrentUser() {
  const { data, error } = await supabase.auth.getUser();
  if (error) throw error;
  return data.user;
}

export async function signInWithEmail(email: string, password: string) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  return data;
}

export async function signUpWithEmail(email: string, password: string) {
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) throw error;
  return data;
}

export async function signOut() {
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

export async function getAuthToken(): Promise<string | null> {
  const session = await getSession();
  return session?.access_token ?? null;
}
```

**Task 2.3.3 — Update `ui-next/src/stores/app-store.ts`**

Add user/session state to the Zustand store (preserving existing fields):

```typescript
import { User } from '@supabase/supabase-js';

interface AppState {
  // ... existing fields ...

  // Auth (new)
  user: User | null;
  isAuthenticated: boolean;
  isAuthLoading: boolean;

  // Auth actions (new)
  setUser: (user: User | null) => void;
  setAuthLoading: (loading: boolean) => void;
  logout: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // ... existing defaults ...
      user: null,
      isAuthenticated: false,
      isAuthLoading: true,

      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setAuthLoading: (loading) => set({ isAuthLoading: loading }),
      logout: () => set({ user: null, isAuthenticated: false }),
    }),
    {
      name: 'reasoner-app-storage',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        // Persist existing fields
        tier: state.tier,
        isSequential: state.isSequential,
        isExpert: state.isExpert,
        isWebSearch: state.isWebSearch,
        isSmartSearch: state.isSmartSearch,
        isEnhancePrompt: state.isEnhancePrompt,
        sidebarCollapsed: state.sidebarCollapsed,
        // Do NOT persist user/session — let Supabase handle that
      }),
    }
  )
);
```

**Task 2.3.4 — Update `ui-next/src/app/providers.tsx`**

```tsx
'use client';

import { useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { useAppStore } from '@/stores/app-store';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const setUser = useAppStore((s) => s.setUser);
  const setAuthLoading = useAppStore((s) => s.setAuthLoading);

  useEffect(() => {
    // Initial session check
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      setAuthLoading(false);
    });

    // Listen for auth state changes
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => listener.subscription.unsubscribe();
  }, [setUser, setAuthLoading]);

  return <>{children}</>;
}
```

Wrap the app in `layout.tsx`:

```tsx
// ui-next/src/app/layout.tsx (additive)
import { AuthProvider } from './providers';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
```

**Day 3 Acceptance Criteria:**
- [ ] `npm run build` in `ui-next/` succeeds with no TypeScript errors.
- [ ] Frontend loads, `AuthProvider` initializes, `isAuthLoading` becomes `false`.
- [ ] Supabase auth state changes propagate to Zustand store.

---

### Day 4 — Auth Pages + API Client Token Injection

**Files:**
- `ui-next/src/app/login/page.tsx`
- `ui-next/src/app/signup/page.tsx`
- `ui-next/src/lib/api-client.ts` (modification)
- `ui-next/src/components/layout/Composer.tsx` (modification — auth gate)

**Task 2.4.1 — Login Page**

```tsx
// ui-next/src/app/login/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { signInWithEmail } from '@/lib/auth';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await signInWithEmail(email, password);
      router.push('/');
    } catch (err: any) {
      setError(err.message || 'Login failed');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-md p-8 space-y-4">
        <h1 className="text-2xl font-bold">Sign In</h1>
        {error && <div className="text-red-500">{error}</div>}
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full p-2 border rounded"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-2 border rounded"
          required
        />
        <button type="submit" className="w-full p-2 bg-blue-600 text-white rounded">
          Sign In
        </button>
        <p className="text-center">
          No account? <a href="/signup" className="text-blue-600">Sign up</a>
        </p>
      </form>
    </div>
  );
}
```

**Task 2.4.2 — Signup Page**

```tsx
// ui-next/src/app/signup/page.tsx
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { signUpWithEmail } from '@/lib/auth';

export default function SignupPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await signUpWithEmail(email, password);
      router.push('/login?message=check-email');
    } catch (err: any) {
      setError(err.message || 'Signup failed');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <form onSubmit={handleSubmit} className="w-full max-w-md p-8 space-y-4">
        <h1 className="text-2xl font-bold">Create Account</h1>
        {error && <div className="text-red-500">{error}</div>}
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full p-2 border rounded"
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full p-2 border rounded"
          required
        />
        <button type="submit" className="w-full p-2 bg-blue-600 text-white rounded">
          Sign Up
        </button>
        <p className="text-center">
          Already have an account? <a href="/login" className="text-blue-600">Sign in</a>
        </p>
      </form>
    </div>
  );
}
```

**Task 2.4.3 — Update `ui-next/src/lib/api-client.ts`**

Modify the API client to inject the Supabase auth token on every request:

```typescript
// ui-next/src/lib/api-client.ts
import { getAuthToken } from './auth';

export async function apiFetch(path: string, options: RequestInit = {}) {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(path, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // Redirect to login on auth failure
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }

  return res;
}
```

**Task 2.4.4 — Add User Menu to Header**

Add a user menu component to the main page or sidebar showing:
- User email (truncated)
- Logout button
- Link to `/dashboard` (placeholder for Phase 9)

**Day 4 Acceptance Criteria:**
- [ ] `/login` page renders and accepts credentials.
- [ ] `/signup` page creates a new Supabase user.
- [ ] API calls from frontend include `Authorization: Bearer <jwt>` header.
- [ ] `apiFetch` redirects to `/login` on 401.

---

### Day 5 — Rate Limiter User-ID Bucketing + Tests

**Files:**
- `src/reasoner/rate_limiter.py` (modification)
- `src/reasoner/api/dependencies.py` (modification)
- `tests/test_saas_auth_integration.py` (new)
- `tests/test_saas_rate_limit_user.py` (new)

**Task 2.5.1 — Extend RateLimiter for User-ID Bucketing**

Modify `src/reasoner/rate_limiter.py`:

```python
# Add to RateLimiter class:

async def is_allowed_for_user(
    self,
    user_id: str,
    tier: str = "default",
) -> tuple[bool, dict]:
    """
    Check rate limit for an authenticated user.
    Uses user_id as bucket key instead of IP.
    """
    # Premium tiers get higher limits
    tier_multipliers = {
        "default": 1.0,
        "free": 1.0,
        "pro": 2.0,
        "enterprise": 5.0,
    }
    multiplier = tier_multipliers.get(tier, 1.0)

    # Temporarily adjust config for this check
    original_config = self.config
    adjusted = RateLimitConfig(
        requests_per_minute=int(original_config.requests_per_minute * multiplier),
        requests_per_hour=int(original_config.requests_per_hour * multiplier),
        burst_size=int(original_config.burst_size * multiplier),
    )

    # Save/restore around check
    self.config = adjusted
    try:
        result = await self.is_allowed(user_id)
    finally:
        self.config = original_config

    return result
```

**Task 2.5.2 — Update Rate Limit Dependency**

Modify `check_rate_limit` in `src/reasoner/api/__init__.py` or `dependencies.py`:

```python
async def check_rate_limit(
    request: Request,
    user: User | None = Depends(get_optional_user),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
):
    """
    Check rate limit using user_id if authenticated, otherwise IP.
    """
    if user is not None:
        # Authenticated user — use user_id as bucket key
        # TODO Phase 3: fetch tier from subscription
        client_id = f"user:{user.id}"
        allowed, info = await rate_limiter.is_allowed(client_id)
    else:
        # Anonymous — use IP + User-Agent hash
        client_id = await get_client_id(request)
        allowed, info = await rate_limiter.is_allowed(client_id)

    request.state.rate_limit_info = info

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={...},  # same as existing
            headers={...},  # same as existing
        )
    return True
```

**Task 2.5.3 — Integration Tests**

```python
# tests/test_saas_auth_integration.py
import pytest
from fastapi.testclient import TestClient

from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
from reasoner.infrastructure.auth import set_auth_adapter
from reasoner.api import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def local_adapter():
    adapter = LocalAuthAdapter(secret="test-secret")
    set_auth_adapter(adapter)
    yield adapter
    set_auth_adapter(None)


@pytest.fixture
def auth_token(local_adapter):
    return local_adapter.create_token(
        user_id="12345678-1234-5678-1234-567812345678",
        email="test@example.com",
        display_name="Test User",
    )


def test_auth_me_without_token_returns_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_auth_me_with_valid_token(client, auth_token):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test User"


def test_run_pipeline_with_auth_token(client, auth_token):
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200


def test_run_pipeline_without_auth_still_works_in_legacy_mode(client):
    # When ENABLE_LEGACY_API_KEY=true, anonymous requests are allowed
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
    )
    assert response.status_code == 200


def test_legacy_api_key_still_works(client):
    # Assuming a default admin key exists in test environment
    import os
    os.environ["ADMIN_API_KEY"] = "test-admin-key-12345"
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
        headers={"Authorization": "Bearer test-admin-key-12345"},
    )
    assert response.status_code == 200
```

**Task 2.5.4 — Full Regression**

```bash
python -m pytest tests/ --tb=short -q
```

**Day 5 Acceptance Criteria:**
- [ ] `tests/test_saas_auth_integration.py` passes.
- [ ] `tests/test_saas_rate_limit_user.py` passes.
- [ ] Full regression suite passes.
- [ ] `ENABLE_LEGACY_API_KEY=true` → anonymous requests still work.
- [ ] `ENABLE_LEGACY_API_KEY=false` → anonymous requests to protected routes return 401 (after Phase 3 wiring).

---

## 3. File Inventory

### New Files

| File | Purpose | Layer |
|---|---|---|
| `src/reasoner/infrastructure/auth/__init__.py` | Adapter factory | Infrastructure |
| `src/reasoner/infrastructure/auth/supabase_adapter.py` | Supabase JWT validation | Infrastructure |
| `src/reasoner/infrastructure/auth/local_adapter.py` | Local HS256 JWT (dev/test) | Infrastructure |
| `src/reasoner/api/dependencies.py` | FastAPI dependency injectors | Interface |
| `src/reasoner/api/saas_router.py` | SaaS REST routes (`/api/auth/me`) | Interface |
| `ui-next/src/lib/supabase.ts` | Supabase browser client | Presentation |
| `ui-next/src/lib/auth.ts` | Auth helper functions | Presentation |
| `ui-next/src/app/login/page.tsx` | Login page | Presentation |
| `ui-next/src/app/signup/page.tsx` | Signup page | Presentation |
| `tests/test_saas_auth_integration.py` | Auth E2E tests | Tests |
| `tests/test_saas_rate_limit_user.py` | Rate limit tests | Tests |

### Modified Files

| File | Change | Blast Radius |
|---|---|---|
| `src/reasoner/api/__init__.py` | Import new dependencies; mount `saas_router`; add `user` to `/api/run` | Medium — verify all SSE paths |
| `src/reasoner/rate_limiter.py` | Add `is_allowed_for_user()` with tier multiplier | Low — additive |
| `ui-next/src/stores/app-store.ts` | Add `user`, `isAuthenticated`, `isAuthLoading` | Low — additive |
| `ui-next/src/app/providers.tsx` | Add `AuthProvider` with Supabase listener | Low — additive |
| `ui-next/src/app/layout.tsx` | Wrap children in `AuthProvider` | Low — layout only |
| `ui-next/src/lib/api-client.ts` | Inject `Authorization` header | Low — additive |
| `.env.example` | Add `SUPABASE_*`, `JWT_SECRET_KEY`, `ENABLE_LEGACY_API_KEY` | Low — documentation |

---

## 4. Environment Variables

Add to `.env.example`:

```env
# ── SaaS Auth ──
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# ── Local Dev JWT (fallback when Supabase unavailable) ──
JWT_SECRET_KEY=<generate-with-openssl-rand-hex-32>

# ── Legacy Compatibility ──
ENABLE_LEGACY_API_KEY=true   # Set to false after full SaaS migration
```

---

## 5. Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| **UnifiedAuthResolver with JWT heuristic** | Avoids forcing frontend to use two different auth schemes. Existing API clients continue to work during migration. |
| **LocalAuthAdapter for tests** | Unit tests should not depend on network or external services. Local JWT is deterministic and instant. |
| **Supabase SSR with Zustand** | `@supabase/supabase-js` handles refresh tokens automatically. Zustand store subscribes to auth state for reactive UI. |
| **Rate limit tier multiplier** | Pro/Enterprise users get higher rate limits without duplicating the rate limiter. Multiplier applied dynamically. |
| **Additive changes to `api/__init__.py`** | `user: User | None = Depends(get_optional_user)` is injected but not consumed yet. Consumption happens in Phase 3 (quotas). |

---

## 6. Risk Mitigation

| Risk | Mitigation |
|---|---|
| **Supabase outage blocks all auth** | `LocalAuthAdapter` can be forced via `ENVIRONMENT=development`. Production should have Supabase status monitoring. |
| **JWT heuristic misclassifies API key** | API keys generated by `secrets.token_urlsafe(32)` rarely contain exactly 2 dots. If collision occurs, user can prefix JWTs with a marker or we can add explicit `type=jwt` header. |
| **Legacy auth breakage** | `ENABLE_LEGACY_API_KEY=true` preserves existing behavior. Full test suite validates this. |
| **Frontend bundle size increase** | `@supabase/supabase-js` is ~40KB gzipped. Acceptable for SaaS functionality. |
| **CORS issues with Supabase** | Supabase client uses the same origin when calling `/api/*`. No additional CORS needed. |

---

## 7. Definition of Done (Phase 2)

- [ ] `GET /api/auth/me` with valid JWT → returns user profile.
- [ ] `GET /api/auth/me` without token → 401.
- [ ] `GET /api/auth/me/optional` without token → `{"authenticated": false}`.
- [ ] `POST /api/run` with JWT → works, user_id available in dependency.
- [ ] `POST /api/run` with legacy API key → works (when `ENABLE_LEGACY_API_KEY=true`).
- [ ] `POST /api/run` without auth → works (legacy mode).
- [ ] Rate limiter uses `user:{id}` bucket for authenticated users.
- [ ] Frontend `/login` and `/signup` pages render and function.
- [ ] Frontend injects `Authorization: Bearer <jwt>` on API calls.
- [ ] Supabase auth state syncs to Zustand store.
- [ ] All existing tests pass.
- [ ] New integration tests pass.

---

## 8. Handoff to Phase 3

Phase 3 (Usage Quotas + Tier Enforcement) will consume the infrastructure established here:

1. **`get_current_user`** dependency is already injecting `User` into routes.
2. **`user.id`** is available for quota checks and audit logging.
3. **Rate limiter** already buckets by `user_id`.
4. **Frontend** already sends authenticated requests.

Phase 3 only needs to:
- Implement `PostgresQuotaRepository`
- Wire `QuotaService.check()` into `/api/run`
- Add `require_tier()` enforcement to premium presets

No auth infrastructure changes required.

---

*End of Phase 2 Plan*
