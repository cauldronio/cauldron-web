from django import template
from cauldron_apps.cauldron.models import Repository

register = template.Library()

FA_ICONS = {
    Repository.GIT: 'fab fa-git-square',
    Repository.GITHUB: 'fab fa-github',
    Repository.GITLAB: 'fab fa-gitlab',
    Repository.MEETUP: 'fab fa-meetup',
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
def get_filter_value(request, filter):
    '''
    This tag returns the value of the specified filter or returns
    a default value if the filter does not meet the requirements
    '''
    dict_ = request.GET.copy()
    filter_ = dict_.get(filter, None)

    if filter == 'kind' and filter_ not in Repository.BACKEND_CHOICES:
        return 'Any Data Source'

    if filter == 'status' and filter_ not in Repository.STATUS_CHOICES:
        return 'Any Status'

    if filter == 'search' and filter_ is None:
        return ''

    if filter_ is None:
        return 'any'

    return filter_


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
    """This tag returns the Font Awesome icon for a backend"""
    try:
        return FA_ICONS[backend]
    except KeyError:
        return "fas fa-question"
