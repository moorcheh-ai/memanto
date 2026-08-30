# memanto/accounts/views.py
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
import logging
import json

logger = logging.getLogger(__name__)

@csrf_exempt
@ratelimit(key='ip', rate='5/m', block=True)
def login_view(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            
            if not username or not password:
                return JsonResponse({'error': 'Username and password required'}, status=400)
            
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return JsonResponse({'success': True})
            else:
                # Increment failed attempts counter (simplified)
                ip = request.META.get('REMOTE_ADDR')
                logger.warning(f"Failed login attempt for user '{username}' from IP {ip}")
                
                # Optional: Add CAPTCHA after 3 failed attempts (not implemented here for brevity)
                return JsonResponse({'error': 'Invalid credentials'}, status=401)
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return JsonResponse({'error': 'Internal server error'}, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

# memanto/accounts/urls.py
from django.urls import path
from .views import login_view

urlpatterns = [
    path('login/', login_view, name='login'),
]

# memanto/settings.py (add to existing settings)
# Rate limiting configuration
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_VIEW = 'django_ratelimit.views.rate_limited'

# Add django-ratelimit to INSTALLED_APPS
INSTALLED_APPS = [
    # ... existing apps ...
    'django_ratelimit',
]

# Add rate limiting middleware (if not already present)
MIDDLEWARE = [
    # ... existing middleware ...
    'django_ratelimit.middleware.RatelimitMiddleware',
]

# Cache setup for rate limiting (ensure Redis or similar is configured)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}