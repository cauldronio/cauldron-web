from django import template
import urllib.parse
from cauldron_apps.cauldron.models.backends import Backends

register = template.Library()

FA_ICONS = {
    Backends.GIT: 'fab fa-git-square',
    Backends.GITHUB: 'fab fa-github',
    Backends.GITLAB: 'fab fa-gitlab',
    Backends.GNOME: 'gnome-icon',
    Backends.KDE: 'kde-icon',
    Backends.MEETUP: 'fab fa-meetup',
    Backends.STACK_EXCHANGE: 'fab fa-stack-exchange',
}

FA_ICONS_NAME = {
    'git': 'fab fa-git-square',
    'github': 'fab fa-github',
    'gitlab': 'fab fa-gitlab',
    'gnome': 'gnome-icon',
    'kde': 'kde-icon',
    'meetup': 'fab fa-meetup',
    'stackexchange': 'fab fa-stack-exchange',
}


@register.simple_tag
def url_replace(request, field, value):
    '''
    This tag replaces just the specified field of the QueryString, kepping
    the values of the rest of the fields
    '''
    dict_ = request.GET.copy()
    dict_[field] = value
    return dict_.urlencode()


@register.simple_tag
def url_replace_qs(url, field, value):
    """
    This filter replaces the specified field of the QueryString, keeping
    the values of the rest of the fields
    """
    dict_ = urllib.parse.parse_qs(url)
    dict_[field] = value
    return urllib.parse.urlencode(dict_, doseq=True)


@register.simple_tag
def get_sorting_icon(request, field):
    '''
    This tag returns the icon that the specified column should have
    given the existing filters
    '''
    dict_ = request.GET.copy()
    sort_by = dict_.get('sort_by', None)

    if not sort_by:
        return 'fas fa-sort text-secondary'

    reverse = False
    if sort_by[0] == '-':
        reverse = True
        sort_by = sort_by[1:]

    if sort_by == field:
        if reverse:
            return 'fas fa-sort-down text-dark'
        else:
            return 'fas fa-sort-up text-dark'

    return 'fas fa-sort text-secondary'


@register.simple_tag
def get_sorting_link(request, field):
    '''
    This tag returns the sorting link that the specified column should have
    given the existing filters
    '''
    dict_ = request.GET.copy()
    sort_by = dict_.get('sort_by', None)

    if not sort_by:
        return field

    reverse = False
    if sort_by[0] == '-':
        reverse = True
        sort_by = sort_by[1:]

    if sort_by == field:
        if reverse:
            return field
        else:
            return '-' + field

    return field


@register.filter
def backend_fa_icon(backend):
    """This tag returns the Font Awesome icon for a backend repository"""
    try:
        return FA_ICONS[backend]
    except KeyError:
        return "fas fa-question"


@register.filter
def backend_name_fa_icon(backend):
    """This tag returns the Font Awesome icon for a backend name"""
    try:
        return FA_ICONS_NAME[backend.lower()]
    except KeyError:
        return "fas fa-question"


@register.filter
def icon_boolean(true_input):
    """Return a tick if input is not False/None/0/etc, else a cross"""
    if true_input:
        return "far fa-check-circle"
    else:
        return "far fa-times-circle"
