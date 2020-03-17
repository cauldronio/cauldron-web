from django import template
from ..models import Repository

register = template.Library()

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
    This tag returns the value of the specified filter or returns 'all'
    if the filter does not meet the requirements
    '''
    dict_ = request.GET.copy()
    filter_ = dict_.get(filter, None)

    if filter_ is None:
        return 'all'

    if filter == 'kind' and filter_ not in Repository.BACKEND_CHOICES:
        return 'all'

    if filter == 'status' and filter_ not in Repository.STATUS_CHOICES:
        return 'all'

    return filter_


@register.simple_tag
def get_sorting_icon(request, field):
    '''
    This tag returns the icon that the specified column should have
    given the existing filters
    '''
    dict_ = request.GET.copy()
    sort_by = dict_.get('sort_by', None)

    if sort_by is None:
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

    if sort_by is None:
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
