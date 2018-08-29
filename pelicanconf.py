#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals

THEME = 'pelican-mg'
AUTHOR = 'lgrn'
SITENAME = 'agren.cc'
#SITEURL = 'https://agren.cc'
JINJA_ENVIRONMENT = {'extensions': ['jinja2.ext.i18n']}

DEFAULT_DATE_FORMAT = '%Y-%m-%d'

#PLUGIN_PATHS = ['pelican-plugins']
#PLUGINS = ['i18n_subsites','bootstrap-rst']

PATH = 'content'

TIMEZONE = 'Europe/Paris'

DEFAULT_LANG = 'En'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = 'feed/atom/index.html' 
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

# Blogroll
# LINKS = (('Pelican', 'http://getpelican.com/'),
         # ('Python.org', 'http://python.org/'),
         # ('Jinja2', 'http://jinja.pocoo.org/'),
         # ('You can modify those links in your config file', '#'),)

# Social widget
SOCIAL = (
         ('Github', 'https://github.com/lgrn'),
         )

DEFAULT_PAGINATION = 10

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True
