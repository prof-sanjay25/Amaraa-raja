from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('authentication.urls')),
    path('panel/', include('admin_panel.urls')),
    path('superadmin/', include('superadmin.urls')),
    path('forms/', include('forms.urls')),
    path('employee/', include('employees.urls')),
    
    
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
