from django.urls import path
from . import views

urlpatterns = [
    # Дашборд
    path('', views.lab_list, name='lab_list'),
    
    # Старт лабы
    path('start/<int:lab_id>/', views.start_lab, name='start_lab'),
    path('accept/<int:lab_id>/', views.accept_task, name='accept_task'),
    
    # Рабочее пространство
    path('workspace/<int:session_id>/', views.lab_workspace, name='lab_workspace'),
    
    path('api/lab/<int:session_id>/command/', views.send_command, name='send_command'),
    path('reset/<int:session_id>/', views.reset_lab, name='reset_lab'),
    path('switch/<int:session_id>/<str:device_name>/', views.switch_device, name='switch_device'),
    path('api/lab/<int:session_id>/switch/<str:device_name>/', views.switch_device, name='switch_device'),

    path('manage/<int:lab_id>/edit/', views.edit_lab, name='edit_lab'),

]