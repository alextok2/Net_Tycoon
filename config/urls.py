from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.users.urls')),
    path('lab/', include('apps.labs.urls')),
    path('', include('apps.game.urls')),  # <--- Подключаем game urls в корень

]