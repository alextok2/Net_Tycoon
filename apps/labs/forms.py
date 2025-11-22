from django import forms
from .models import LabScenario
import json

class LabScenarioForm(forms.ModelForm):
    class Meta:
        model = LabScenario
        fields = ['title', 'description', 'allowed_devices', 'topology_data', 'success_criteria']
        
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            # Используем Textarea, скрытый стилем
            'allowed_devices': forms.Textarea(attrs={'style': 'display:none;'}),
            'topology_data': forms.Textarea(attrs={'style': 'display:none;'}),
            'success_criteria': forms.Textarea(attrs={'style': 'display:none;'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance.pk:
            for field in ['allowed_devices', 'topology_data', 'success_criteria']:
                val = self.initial.get(field)
                
                # 1. Если это уже объект (Django распарсил JSONField) -> превращаем в красивую строку
                if isinstance(val, (dict, list)):
                    self.initial[field] = json.dumps(val, indent=2, ensure_ascii=False)
                
                # 2. Если это строка (возможно, "грязная")
                elif isinstance(val, str):
                    try:
                        # Попытка декодировать
                        parsed = json.loads(val)
                        
                        # Если после декодирования это СНОВА строка (Double Encoded)
                        # Например: val='"{\"a\":1}"' -> parsed='{"a":1}'
                        if isinstance(parsed, str):
                            # Мы нашли двойное кодирование! Убираем один слой.
                            # Пробуем превратить её в объект для красивого форматирования
                            try:
                                obj = json.loads(parsed)
                                self.initial[field] = json.dumps(obj, indent=2, ensure_ascii=False)
                            except:
                                self.initial[field] = parsed
                        else:
                            # Это был нормальный JSON в виде строки, просто форматируем красиво
                            self.initial[field] = json.dumps(parsed, indent=2, ensure_ascii=False)
                    except:
                        # Если это просто мусор, оставляем как есть
                        pass

    # Валидаторы (очищают данные ПЕРЕД сохранением в БД)
    
    def clean_json_field(self, field_name):
        data = self.cleaned_data[field_name]
        if isinstance(data, str):
            try:
                # Парсим строку в объект, чтобы в БД лег именно JSON-объект (или словарь)
                # Это предотвратит сохранение строки как значения JSONField
                return json.loads(data)
            except json.JSONDecodeError as e:
                raise forms.ValidationError(f"Invalid JSON in {field_name}: {e}")
        return data

    def clean_allowed_devices(self): return self.clean_json_field('allowed_devices')
    def clean_topology_data(self): return self.clean_json_field('topology_data')
    def clean_success_criteria(self): return self.clean_json_field('success_criteria')
