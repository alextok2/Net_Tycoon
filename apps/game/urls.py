from django.urls import path
from . import views

urlpatterns = [
    path('', views.game_root, name='game_root'), 

    path('new-game/', views.create_character, name='create_character'),
    path('intro/', views.intro, name='intro'),
    path('office/', views.office, name='office'),
]