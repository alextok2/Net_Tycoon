import json
import traceback
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import LabScenario, UserLabSession
from .engine.processor import IOSCommandProcessor
# В начало файла добавьте импорт
from django.http import HttpResponseRedirect
from django.urls import reverse

# Добавьте эти импорты
from django.contrib.auth.decorators import user_passes_test
from .forms import LabScenarioForm

@login_required
def reset_lab(request, session_id):
    """Полный сброс лабораторной работы (Hard Reset)"""
    session = get_object_or_404(UserLabSession, id=session_id, user=request.user)
    
    # Сбрасываем параметры в исходное состояние
    session.current_context = "privileged"
    session.virtual_config = {}
    session.command_history = []
    session.is_completed = False
    session.save()
    
    # Перезагружаем страницу
    return HttpResponseRedirect(reverse('lab_workspace', args=[session_id]))

# Настраиваем простой логгер
logger = logging.getLogger(__name__)

@login_required
def lab_list(request):
    labs = LabScenario.objects.all()
    active_sessions = UserLabSession.objects.filter(user=request.user).values_list('lab_id', flat=True)
    return render(request, 'labs/index.html', {
        'labs': labs, 
        'active_sessions': active_sessions
    })

@login_required
def start_lab(request, lab_id):
    lab = get_object_or_404(LabScenario, id=lab_id)
    session, created = UserLabSession.objects.get_or_create(
        user=request.user,
        lab=lab
    )
    return redirect('lab_workspace', session_id=session.id)

@login_required
def lab_workspace(request, session_id):
    session = get_object_or_404(UserLabSession, id=session_id, user=request.user)
    
    # --- НОВАЯ ЛОГИКА: ПРОВЕРКА ПРИ ЗАГРУЗКЕ ---
    # Создаем процессор, чтобы запустить валидацию
    processor = IOSCommandProcessor(session)
    # Проверяем выполнение по АКТУАЛЬНЫМ критериям из БД (которые мог поменять админ)
    is_completed_now = processor.check_completion() 
    # -------------------------------------------

    # 1. Получаем текущее устройство
    current_dev = session.current_device
    dev_data = session.virtual_config.get(current_dev, {})
    
    # 2. Промпт
    config = dev_data.get("config", {})
    display_name = config.get("hostname", current_dev)
    current_ctx = dev_data.get("context", "privileged")
    
    prompt_map = {
        "privileged": f"{display_name}#",
        "global_config": f"{display_name}(config)#",
        "interface_config": f"{display_name}(config-if)#",
        "isakmp_config": f"{display_name}(config-isakmp)#",
        "crypto_map_config": f"{display_name}(config-crypto-map)#",
        "line_config": f"{display_name}(config-line)#",
    }
    initial_prompt = prompt_map.get(current_ctx, f"{display_name}#")
    
    # 3. Логи
    initial_logs = dev_data.get("console_logs", [])
    if not initial_logs:
        initial_logs = [{"type": "out", "text": f"System Bootstrap\nConnected to {current_dev} console."}]

    # 4. Имена устройств
    device_hostnames = {}
    all_devices = session.lab.allowed_devices if session.lab.allowed_devices else ["R1", "R2"]
    for dev in all_devices:
        d_cfg = session.virtual_config.get(dev, {}).get("config", {})
        device_hostnames[dev] = d_cfg.get("hostname", dev)

    return render(request, 'labs/workspace.html', {
        'session': session,
        'lab': session.lab,
        'initial_logs_json': initial_logs, 
        'initial_prompt': initial_prompt,
        'device_hostnames_json': device_hostnames,
        
        # Передаем обновленный статус в шаблон
        'is_completed': is_completed_now 
    })


@csrf_exempt
@require_POST
def send_command(request, session_id):
    if not request.user.is_authenticated:
         return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
         
    try:
        data = json.loads(request.body)
        command_text = data.get('command', '')
        
        session = get_object_or_404(UserLabSession, id=session_id, user=request.user)
        
        # --- ИСПРАВЛЕНИЕ: Безопасное получение контекста из JSON ---
        # Мы больше не используем session.current_context напрямую
        current_device = session.current_device
        device_config = session.virtual_config.get(current_device, {})
        current_ctx = device_config.get("context", "unknown")
        
        print(f"DEBUG: User '{request.user}' on '{current_device}' sent: '{command_text}' (ctx: {current_ctx})")
        
        processor = IOSCommandProcessor(session)
        result = processor.process_input(command_text)
        
        return JsonResponse({
            'status': 'ok',
            'output': result['output'],
            'prompt': result['prompt'],
            'completed': result['is_completed'],
            'new_hostname': result['hostname'] 
        })

    except Exception as e:
        print("\n" + "="*30)
        print("!!! CRITICAL ERROR IN LAB ENGINE !!!")
        print(f"Error Message: {str(e)}")
        print("Traceback:")
        traceback.print_exc() 
        print("="*30 + "\n")
        
        return JsonResponse({
            'status': 'error', 
            'message': f"Server Logic Error: {str(e)}"
        }, status=500)


@csrf_exempt
@login_required
def switch_device(request, session_id, device_name):
    session = get_object_or_404(UserLabSession, id=session_id, user=request.user)
    lab = session.lab
    
    # 1. Проверка прав
    allowed = lab.allowed_devices if lab.allowed_devices else ["R1"]
    if device_name not in allowed:
         return JsonResponse({'status': 'error', 'message': 'Access Denied'}, status=403)

    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
    # 2. Определяем ТИП устройства
    # Защита от того, что JSONField вернулся как строка
    topology = lab.topology_data
    if isinstance(topology, str):
        try:
            topology = json.loads(topology)
        except json.JSONDecodeError:
            topology = {} # Если мусор в БД

    nodes = topology.get('nodes', [])
    # -------------------------

    device_type = "router" 
    for node in nodes:
        if node.get('id') == device_name:
            device_type = node.get('type', 'router')
            break


    # 3. Переключение сессии в БД
    session.current_device = device_name
    
    # Инициализация, если данных еще нет
    if device_name not in session.virtual_config:
        session.virtual_config[device_name] = {
            "config": {"hostname": device_name},
            "context": "privileged",
            "history": [],
            "console_logs": [] 
        }
        session.save()
    else:
        session.save()
    
    # Получаем данные устройства
    dev_data = session.virtual_config[device_name]
    
    # ============================================================
    # !!! ВАЖНО: Читаем hostname из конфига !!!
    # ============================================================
    config = dev_data.get("config", {})
    # Если пользователь задал hostname, берем его. Иначе берем имя девайса (R1)
    display_name = config.get("hostname", device_name) 
    
    # Определяем контекст (в каком режиме мы вышли)
    current_ctx = dev_data.get("context", "privileged")

    # Генерируем промпт на основе display_name
    prompt_map = {
        "privileged": f"{display_name}#",
        "global_config": f"{display_name}(config)#",
        "interface_config": f"{display_name}(config-if)#",
        "isakmp_config": f"{display_name}(config-isakmp)#",
        "crypto_map_config": f"{display_name}(config-crypto-map)#",
    }
    
    new_prompt = prompt_map.get(current_ctx, f"{display_name}#")
    # ============================================================

    logs = dev_data.get("console_logs", [])
    if not logs:
        logs = [{"type": "out", "text": f"Switched to {device_name} ({device_type})."}]

    return JsonResponse({
        'status': 'ok', 
        'prompt': new_prompt,
        'logs': logs,
        'device_type': device_type
    })

# Проверка: является ли юзер админом
def is_admin(user):
    return user.is_authenticated and user.is_staff

@user_passes_test(is_admin)
def edit_lab(request, lab_id):
    lab = get_object_or_404(LabScenario, pk=lab_id)
    
    if request.method == 'POST':
        form = LabScenarioForm(request.POST, instance=lab)
        if form.is_valid():
            form.save()
            # Редирект на список лаб после сохранения
            return redirect('lab_list')
    else:
        form = LabScenarioForm(instance=lab)
        
    return render(request, 'labs/edit_lab.html', {
        'form': form, 
        'lab': lab
    })