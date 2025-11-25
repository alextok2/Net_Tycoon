from django.db import models
from django.contrib.auth.models import User

class LabScenario(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    topology_data = models.JSONField(default=dict)
    success_criteria = models.JSONField(default=dict)
    allowed_devices = models.JSONField(default=list)
    
    
    min_level = models.IntegerField(default=1) 
    reward_money = models.IntegerField(default=100)
    reward_xp = models.IntegerField(default=10)

    def __str__(self):
        return self.title

class UserLabSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    lab = models.ForeignKey(LabScenario, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # !!! НОВОЕ: Какое устройство сейчас открыто в терминале
    current_device = models.CharField(max_length=10, default="R1")
    
    # В virtual_config теперь храним ВСЁ: и конфиг, и контекст, и историю для каждого роутера
    # Структура: { "R1": { "config": {}, "context": "...", "history": [] }, "R2": ... }
    virtual_config = models.JSONField(default=dict)
    
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.lab.title}"