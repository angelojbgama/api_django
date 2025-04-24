from django.contrib import admin
from django.urls import path, include  # ✅ precisa importar path e include

from django.conf import settings
from django.conf.urls.static import static  # ✅ precisa disso para servir arquivos estáticos

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('locations.urls')),
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
