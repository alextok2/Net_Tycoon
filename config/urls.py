from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.users.urls')), # Auth
    path('', include('apps.labs.urls')),       # Labs (корень сайта теперь ведет на список лаб)
]