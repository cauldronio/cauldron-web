from django.shortcuts import render
from CauldronApp.models import Token
from CauldronApp.views import create_context
from django.contrib.auth.decorators import login_required

from .forms import ProfileEditForm


@login_required(redirect_field_name=None)
def index(request):
    context = create_context(request)
    context['user'] = request.user
    context['tokens'] = {
        'github': Token.objects.filter(backend='github', user=request.user).first(),
        'gitlab': Token.objects.filter(backend='gitlab', user=request.user).first(),
        'meetup': Token.objects.filter(backend='meetup', user=request.user).first(),
    }

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            context['message_success'] = "Profile was successfully updated"
    else:
        form = ProfileEditForm(instance=request.user)

    context['form'] = form

    return render(request, 'profile/index.html', context)
