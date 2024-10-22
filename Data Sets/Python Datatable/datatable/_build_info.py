#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# --------------------------------------------------------------
# Copyright 2018-2021 H2O.ai
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the 'Software'), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY
# KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
# PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
# OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# --------------------------------------------------------------
# This file was auto-generated from ci/ext.py

import types

try:
    import datatable.lib._datatable as _dt
    _compiler = _dt._compiler()
except:
    _compiler = 'unknown'

build_info = types.SimpleNamespace(
    version='1.0.0',
    build_date='2021-07-01 20:53:57',
    build_mode='release',
    compiler=_compiler,
    git_revision='ffb58ac31a77d5b8f6323fe4e94c9caebb97f90e',
    git_branch='rel-1.0',
    git_date='2021-07-01 20:51:46',
    git_diff='',
)
