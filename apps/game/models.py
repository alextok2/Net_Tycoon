from django.db import models
from django.contrib.auth.models import User

class PlayerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    company_name = models.CharField(max_length=100, default="NetStart Inc.")
    
    # Внешность (храним коды для JS/SVG)
    skin_color = models.CharField(max_length=20, default="#f5d0b0")
    hair_style = models.IntegerField(default=1)
    hair_color = models.CharField(max_length=20, default="#4a3b2a")
    shirt_color = models.CharField(max_length=20, default="#3498db")
    
    # Прогресс
    level = models.IntegerField(default=1)
    xp = models.IntegerField(default=0)
    money = models.IntegerField(default=1000) # Бюджет IT отдела
    
    day = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.user.username} ({self.company_name})"