from django import template

register = template.Library()


@register.inclusion_tag('partials/pagination_number.html', takes_context=True)
def mapping_pages(context):
    """Nomor halaman dinamis yang mempertahankan seluruh filter GET aktif.

    Sebelumnya link nomor halaman hanya menghasilkan ``?page=N`` sehingga
    filter status/search/Posyandu hilang ketika pengguna berpindah halaman.
    """
    page_obj = context.get('page_obj')
    if not page_obj:
        return {}

    current_num = page_obj.number
    total_pages = page_obj.paginator.num_pages
    start_page = max(1, current_num - 2)
    end_page = min(total_pages, current_num + 2)

    request = context.get('request')
    querystring = ''
    if request is not None:
        query = request.GET.copy()
        query.pop('page', None)
        querystring = query.urlencode()

    return {
        'page_obj': page_obj,
        'page_range': range(start_page, end_page + 1),
        'querystring': querystring,
    }
