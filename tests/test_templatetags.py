# coding: utf-8
from __future__ import unicode_literals

import lxml.etree
import lxml.html
import pytest
import six
from django.core.exceptions import ImproperlyConfigured
from django.template import Context, RequestContext, Template
from django.utils.safestring import mark_safe

import django_tables2 as tables
from django_tables2.config import RequestConfig
from six.moves.urllib.parse import parse_qs

from .app.models import Person, Region
from .test_templates import MEMORY_DATA, CountryTable
from .utils import build_request, parse


def test_render_table_templatetag(settings):
    request = build_request('/')
    # ensure it works with a multi-order-by
    table = CountryTable(MEMORY_DATA, order_by=('name', 'population'))
    RequestConfig(request).configure(table)
    template = Template('{% load django_tables2 %}{% render_table table %}')
    html = template.render(Context({'request': request, 'table': table}))

    root = parse(html)
    assert len(root.findall('.//thead/tr')) == 1
    assert len(root.findall('.//thead/tr/th')) == 4
    assert len(root.findall('.//tbody/tr')) == 4
    assert len(root.findall('.//tbody/tr/td')) == 16
    assert root.find('ul[@class="pagination"]/li[@class="cardinality"]').text == '4 items'

    # no data with no empty_text
    table = CountryTable([])
    template = Template('{% load django_tables2 %}{% render_table table %}')
    html = template.render(Context({'request': build_request('/'), 'table': table}))
    root = parse(html)
    assert len(root.findall('.//thead/tr')) == 1
    assert len(root.findall('.//thead/tr/th')) == 4
    assert len(root.findall('.//tbody/tr')) == 0

    # no data WITH empty_text
    request = build_request('/')
    table = CountryTable([], empty_text='this table is empty')
    RequestConfig(request).configure(table)
    template = Template('{% load django_tables2 %}{% render_table table %}')
    html = template.render(Context({'request': request, 'table': table}))
    root = parse(html)
    assert len(root.findall('.//thead/tr')) == 1
    assert len(root.findall('.//thead/tr/th')) == 4
    assert len(root.findall('.//tbody/tr')) == 1
    assert len(root.findall('.//tbody/tr/td')) == 1
    assert int(root.find('.//tbody/tr/td').get('colspan')) == len(root.findall('.//thead/tr/th'))
    assert root.find('.//tbody/tr/td').text == 'this table is empty'

    # variable that doesn't exist (issue #8)
    template = Template('{% load django_tables2 %}'
                        '{% render_table this_doesnt_exist %}')
    with pytest.raises(ValueError):
        settings.DEBUG = True
        template.render(Context())

    # Should still be noisy with debug off
    with pytest.raises(ValueError):
        settings.DEBUG = False
        template.render(Context())


def test_render_table_should_support_template_argument():
    table = CountryTable(MEMORY_DATA, order_by=('name', 'population'))
    template = Template('{% load django_tables2 %}'
                        '{% render_table table "dummy.html" %}')
    request = build_request('/')
    context = RequestContext(request, {'table': table})
    assert template.render(context) == 'dummy template contents\n'


@pytest.mark.django_db
def test_render_table_supports_queryset():
    for name in ("Mackay", "Brisbane", "Maryborough"):
        Region.objects.create(name=name)
    template = Template('{% load django_tables2 %}{% render_table qs %}')
    html = template.render(Context({'qs': Region.objects.all(),
                                    'request': build_request('/')}))

    root = parse(html)
    assert [e.text for e in root.findall('.//thead/tr/th/a')] == ["ID", "name", "mayor"]
    td = [[td.text for td in tr.findall('td')] for tr in root.findall('.//tbody/tr')]
    db = []
    for region in Region.objects.all():
        db.append([six.text_type(region.id), region.name, "—"])
    assert td == db


def test_querystring_templatetag():
    template = Template('{% load django_tables2 %}'
                        '<b>{% querystring "name"="Brad" foo.bar=value %}</b>')

    # Should be something like: <root>?name=Brad&amp;a=b&amp;c=5&amp;age=21</root>
    xml = template.render(Context({
        "request": build_request('/?a=b&name=dog&c=5'),
        "foo": {"bar": "age"},
        "value": 21,
    }))

    # Ensure it's valid XML, retrieve the URL
    url = parse(xml).text

    qs = parse_qs(url[1:])  # everything after the ?
    assert qs["name"] == ["Brad"]
    assert qs["age"] == ["21"]
    assert qs["a"] == ["b"]
    assert qs["c"] == ["5"]


def test_querystring_templatetag_requires_request():
    with pytest.raises(ImproperlyConfigured):
        (Template('{% load django_tables2 %}{% querystring "name"="Brad" %}')
         .render(Context()))


def test_querystring_templatetag_supports_without():
    context = Context({
        "request": build_request('/?a=b&name=dog&c=5'),
        "a_var": "a",
    })

    template = Template('{% load django_tables2 %}'
                        '<b>{% querystring "name"="Brad" without a_var %}</b>')
    url = parse(template.render(context)).text
    qs = parse_qs(url[1:])  # trim the ?
    assert set(qs.keys()) == set(["name", "c"])

    # Try with only exclusions
    template = Template('{% load django_tables2 %}'
                        '<b>{% querystring without "a" "name" %}</b>')
    url = parse(template.render(context)).text
    qs = parse_qs(url[1:])  # trim the ?
    assert set(qs.keys()) == set(["c"])


def test_title_should_only_apply_to_words_without_uppercase_letters():
    expectations = {
        "a brown fox": "A Brown Fox",
        "a brown foX": "A Brown foX",
        "black FBI": "Black FBI",
        "f.b.i": "F.B.I",
        "start 6pm": "Start 6pm",
    }

    for raw, expected in expectations.items():
        template = Template("{% load django_tables2 %}{{ x|title }}")
        assert template.render(Context({"x": raw})) == expected


def test_nospaceless_works():
    template = Template("{% load django_tables2 %}"
                        "{% spaceless %}<b>a</b> <i>b {% nospaceless %}<b>c</b>"
                        "  <b>d</b> {% endnospaceless %}lic</i>{% endspaceless %}")
    assert template.render(Context()) == "<b>a</b><i>b <b>c</b>&#32;<b>d</b> lic</i>"


def test_whitespace_is_preserved():
    class TestTable(tables.Table):
        name = tables.Column(verbose_name=mark_safe("<b>foo</b> <i>bar</i>"))

    request = build_request('/')
    html = TestTable([{"name": mark_safe("<b>foo</b> <i>bar</i>")}]).as_html(request)

    tree = parse(html)

    assert "<b>foo</b> <i>bar</i>" in lxml.etree.tostring(tree.findall('.//thead/tr/th')[0], encoding='unicode')
    assert "<b>foo</b> <i>bar</i>" in lxml.etree.tostring(tree.findall('.//tbody/tr/td')[0], encoding='unicode')


@pytest.mark.django_db
def test_as_html_db_queries(transactional_db):
    class PersonTable(tables.Table):
        class Meta:
            model = Person

    # TODO: check why this is commented out
    # with queries(count=1):
    #     PersonTable(Person.objects.all()).as_html(request)
