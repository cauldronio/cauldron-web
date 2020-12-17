from django.shortcuts import render, redirect
from CauldronApp.views import create_context, delete_user
from cauldron_apps.poolsched_github.models import GHToken
from cauldron_apps.poolsched_gitlab.models import GLToken
from cauldron_apps.poolsched_meetup.models import MeetupToken
from django.contrib.auth.decorators import login_required

from .forms import ProfileEditForm


@login_required(redirect_field_name=None)
def index(request):
    context = create_context(request)
    context['user'] = request.user
    context['tokens'] = {
        'github': GHToken.objects.filter(user=request.user, instance='GitHub').first(),
        'gitlab': GLToken.objects.filter(user=request.user, instance='GitLab').first(),
        'meetup': MeetupToken.objects.filter(user=request.user).first(),
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


@login_required(redirect_field_name=None)
def request_delete_own_user(request):
    """
    Delete your own user
    """
    context = create_context(request)

    if request.method != 'POST':
        context['title'] = "Not allowed"
        context['description'] = "Method not allowed for this path"
        return render(request, 'error.html', status=405, context=context)

    user = request.user
    delete_user(user)

    return redirect('homepage')
