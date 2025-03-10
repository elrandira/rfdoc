# Copyright 2009-2013 Nokia Siemens Networks Oyj
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django import forms
from django.forms.utils import ErrorList
from django.shortcuts import render
from xml.etree import cElementTree as ET

from rfdoc.rfdocapp.models import Library


def upload(request):
    lib = None
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            lib = form.parse_kw_spec(request.FILES['file'],
                                         form.cleaned_data['override'],
                                         form.cleaned_data['override_name'].strip(),
                                         form.cleaned_data['override_version'].strip())
    else:
        form = UploadFileForm()
    return render(request, 'upload.html', {
            'form': form,
            'lib': lib
        }
    )


class UploadFileForm(forms.Form):
    file = forms.FileField()
    file.widget.attrs['size'] = 40
    override = forms.BooleanField(required=False)
    override_name = forms.CharField(required=False)
    override_version = forms.CharField(required=False)
    override_version.widget.attrs['size'] = 10

    def parse_kw_spec(self, fileobj, override, override_name, override_version):
        try:
            libdata = LibraryData(fileobj)
            if override_version:
                libdata.version = override_version
            if override_name:
                libdata.name = override_name
            if Library.objects.filter(name=libdata.name).filter(version=libdata.version):
                if not override:
                    raise InvalidXmlError("Library %s version %s already exists." % (libdata.name, libdata.version))
                else:
                    Library.objects.filter(name=libdata.name).filter(version=libdata.version).delete()
            lib = Library(name=libdata.name, doc=libdata.doc, version=libdata.version)
            lib.save()
            for init in libdata.inits:
                lib.init_set.create(doc=init.doc, args=init.args)
            for kw in libdata.kws:
                lib.keyword_set.create(name=kw.name, doc=kw.doc, args=kw.args)
        except InvalidXmlError as err:
            self._errors['file'] = ErrorList([str(err)])
            return None
        return lib


class LibraryData(object):

    def __init__(self, fileobj):
        self.filename = fileobj.name
        root = self._get_root(fileobj)
        try:
            self.name = self._get_name(root)
            self.version = self._get_version(root)
            self.doc = self._get_doc(root)
        except InvalidXmlError as e:
            raise InvalidXmlError('Library parsing error. Given file %s contains invalid XML: %s' % (self.filename, e))
        self.inits = [ InitData(data, self.filename) for data in self._get_inits(root) ]
        self.kws = [ KeywordData(data, self.filename) for data in self._get_keywords(root) ]

    def _get_root(self, fileobj):
        try:
            root = ET.parse(fileobj).getroot()
        except SyntaxError as e:
            raise InvalidXmlError('Given file %s is not XML: %s' % (self.filename, e))
        if root.tag != 'keywordspec':
            raise InvalidXmlError('Given file %s contains invalid XML: Root tag must be keywordspec' % self.filename)
        return root

    def _get_name(self, elem):
        return get_attr(elem, 'name')

    def _get_doc(self, elem):
        return get_child_element(elem, 'doc').text or ''

    def _get_version(self, elem):
        # libdoc.py didn't add version in 2.1 and earlier
        try:
            version_elem = get_child_element(elem, 'version')
        except InvalidXmlError:
            version = None
        else:
            version = version_elem.text
        return version or '<unknown>'

    def _get_inits(self, elem):
        return elem.findall('init')

    def _get_keywords(self, elem):
        # 'keywords/kw' is backwards compatibility for libdoc.py 2.1 and earlier
        kws = elem.findall('keywords/kw') + elem.findall('kw')
        if not kws:
            raise InvalidXmlError('Given test library file %s contains no keywords.' % self.filename)
        return kws


class KeywordData(object):

    def __init__(self, elem, filename):
        try:
            self.name = self._get_name(elem)
            self.doc = self._get_doc(elem)
            self.args = ', '.join(arg.text for arg in self._get_args(elem))
        except InvalidXmlError as e:
            raise InvalidXmlError('Keyword parsing error. Given file %s contains invalid XML: %s' % (filename, e))

    def _get_name(self, elem):
        return get_attr(elem, 'name')

    def _get_doc(self, elem):
        return get_child_element(elem, 'doc').text or ''

    def _get_args(self, elem):
        return get_child_element(elem, 'arguments').findall('arg')


class InitData(KeywordData):

    def _get_name(self, elem):
        return '<init>'


def get_attr(elem, attr_name):
    attr = elem.get(attr_name)
    if not attr:
        raise InvalidXmlError('Attribute %s not found' % attr_name)
    return attr

def get_child_element(elem, child_name):
    child = elem.find(child_name)
    if child is None:
        raise InvalidXmlError('Child element %s not found' % child_name)
    return child


class InvalidXmlError(TypeError):
    pass

