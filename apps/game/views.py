from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import PlayerProfile
from .forms import CharacterForm
from apps.labs.models import LabScenario, UserLabSession

@login_required
def create_character(request):
    # Если профиль уже есть, идем в офис
    if hasattr(request.user, 'profile'):
        return redirect('office')

    if request.method == 'POST':
        form = CharacterForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            return redirect('intro')
        else:
            print("Form Errors:", form.errors) 

    else:
        form = CharacterForm()
    
    return render(request, 'game/char_create.html', {'form': form})

@login_required
def intro(request):
    return render(request, 'game/intro.html')

@login_required
def office(request):
    profile = request.user.profile
    
    # 1. Ищем АКТИВНОЕ задание (принятое, но не выполненное)
    active_session = UserLabSession.objects.filter(
        user=request.user, 
        is_completed=False
    ).first() # Берем первое активное
    
    # 2. Ищем ВХОДЯЩИЕ задания (доступные по уровню, не выполненные и не активные сейчас)
    # Получаем ID всех начатых или завершенных лаб
    excluded_ids = UserLabSession.objects.filter(user=request.user).values_list('lab_id', flat=True)
    
    inbox_labs = LabScenario.objects.filter(
        min_level__lte=profile.level
    ).exclude(
        id__in=excluded_ids
    )
    
    return render(request, 'game/office.html', {
        'profile': profile,
        'inbox_labs': inbox_labs,
        'active_session': active_session, # Передаем активную сессию
    })

def game_root(request):
    """Главная точка входа (Root URL)"""
    # 1. Если не залогинен -> на страницу входа
    if not request.user.is_authenticated:
        return redirect('login')
    
    # 2. Если залогинен, но нет профиля (персонажа) -> Создание персонажа
    if not hasattr(request.user, 'profile'):
        return redirect('create_character')
        
    # 3. Если есть профиль -> В офис
    return redirect('office')