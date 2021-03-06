from dexy.filter import DexyFilter
from dexy.filters.templating_plugins import TemplatePlugin
from jinja2 import FileSystemLoader
from jinja2.exceptions import TemplateSyntaxError
from jinja2.exceptions import UndefinedError
from jinja2.exceptions import TemplateNotFound
import dexy.exceptions
import jinja2
import os
import re
import traceback

class TemplateFilter(DexyFilter):
    """
    Base class for templating system filters such as JinjaFilter. Templating
    systems are used to make generated artifacts available within documents.

    Plugins are used to prepare content.
    """
    ALIASES = ['template']

    _SETTINGS = {
            'output' : True,
            'variables' : ("Variables to be made available to document.", {}),
            'vars' : ("Variables to be made available to document.", {}),
            'plugins' : ("List of plugins for run_plugins to use.", [])
            }

    def template_plugins(self):
        """
        Returns a list of plugin classes for run_plugins to use.
        """
        if self.setting('plugins'):
            return [TemplatePlugin.create_instance(alias, self) for alias in self.setting('plugins')]
        else:
            return TemplatePlugin.__iter__(self)

    def run_plugins(self):
        env = {}
        for plugin in self.template_plugins():
            self.log.debug("Running template plugin %s" % plugin.__class__.__name__)
            new_env_vars = plugin.run()
            if any(v in env.keys() for v in new_env_vars):
                new_keys = ", ".join(sorted(new_env_vars))
                existing_keys = ", ".join(sorted(env))
                msg = "plugin class '%s' is trying to add new keys '%s', already have '%s'"
                raise dexy.exceptions.InternalDexyProblem(msg % (plugin.__class__.__name__, new_keys, existing_keys))
            env.update(new_env_vars)
        return env

    def process_text(self, input_text):
        template_data = self.run_plugins()
        return input_text % template_data

class JinjaFilter(TemplateFilter):
    """
    Runs the Jinja templating engine.
    """
    ALIASES = ['jinja']

    _SETTINGS = {
            'block-start-string' : ("Tag to indicate the start of a block.", "{%"),
            'block-end-string' : ("Tag to indicate the start of a block.", "%}"),
            'variable-start-string' : ("Tag to indicate the start of a variable.", "{{"),
            'variable-end-string' : ("Tag to indicate the start of a variable.", "}}"),
            'comment-start-string' : ("Tag to indicate the start of a comment.", "{#"),
            'comment-end-string' : ("Tag to indicate the start of a comment.", "#}"),
            'changetags' : ("Automatically change from { to < based tags for .tex and .wiki files.", True),
            'jinja-path' : ("List of additional directories to pass to jinja loader.", []),
            }
    TEX_TAGS = {
            'block_start_string': '<%',
            'block_end_string': '%>',
            'variable_start_string': '<<',
            'variable_end_string': '>>',
            'comment_start_string': '<#',
            'comment_end_string': '#>'
            }

    def setup_jinja_env(self, loader=None):
        env_attrs = {}
        skip_settings = ('changetags', 'jinja-path',)
        for k, v in self.setting_values().iteritems():
            underscore_k = k.replace("-", "_")
            if k in self._SETTINGS and not k in skip_settings:
                env_attrs[underscore_k] = v

        env_attrs['undefined'] = jinja2.StrictUndefined

        if self.artifact.ext in (".tex", ".wiki") and self.setting('changetags'):
            self.log.debug("Changing tags to latex/wiki format.")
            for k, v in self.TEX_TAGS.iteritems():
                hyphen_k = k.replace("_", "-")
                if env_attrs[k] == self._SETTINGS[hyphen_k][1]:
                    self.log.debug("Setting %s to %s" % (k, v))
                    env_attrs[k] = v

        if loader:
            env_attrs['loader'] = loader

        debug_attr_string = ", ".join("%s: %r" % (k, v) for k, v in env_attrs.iteritems())
        self.log.debug("creating jinja2 environment with: %s" % debug_attr_string)
        return jinja2.Environment(**env_attrs)

    def handle_jinja_exception(self, e, input_text, template_data):
        result = []
        input_lines = input_text.splitlines()

        # Try to parse line number from stack trace...
        if isinstance(e, UndefinedError) or isinstance(e, TypeError):
            # try to get the line number
            m = re.search(r"File \"<template>\", line ([0-9]+), in top\-level template code", traceback.format_exc())
            if m:
                e.lineno = int(m.groups()[0])
            else:
                e.lineno = 0
                self.log.warn("unable to parse line number from traceback")

        args = {
                'error_type' : e.__class__.__name__,
                'key' : self.artifact.key,
                'lineno' : e.lineno,
                'message' : e.message,
                'name' : self.output().name,
                'workfile' : self.input().storage.data_file()
                }

        result.append("a %(error_type)s problem was detected: %(message)s" % args)

        if isinstance(e, UndefinedError):
            match_has_no_attribute = re.match("^'[\w\s\.]+' has no attribute '(.+)'$", e.message)
            match_is_undefined = re.match("^'([\w\s]+)' is undefined$", e.message)

            if match_has_no_attribute:
                undefined_object = match_has_no_attribute.groups()[0]
                match_lines = []
                for i, line in enumerate(input_lines):
                    if (".%s" % undefined_object in line) or ("'%s'" % undefined_object in line) or ("\"%s\"" % undefined_object in line):
                        result.append("line %04d: %s" % (i+1, line))
                        match_lines.append(i)
                if len(match_lines) == 0:
                    raise dexy.exceptions.InternalDexyProblem("Tried to find source of: %s. Could not find match for '%s'" % (e.message, undefined_object))

            elif match_is_undefined:
                undefined_object = match_is_undefined.groups()[0]
                for i, line in enumerate(input_lines):
                    if undefined_object in line:
                        result.append("line %04d: %s" % (i+1, line))
            else:
                raise dexy.exceptions.InternalDexyProblem("don't know how to match pattern: %s" % e.message)
        else:
            result.append("line %04d: %s" % (e.lineno, input_lines[e.lineno-1]))

        raise dexy.exceptions.UserFeedback("\n".join(result))

    def process(self):
        wd = self.setup_wd()
        macro_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'macros'))
        dirs = ['.', wd, self.artifact.full_wd(), macro_dir] + self.setting('jinja-path')
        self.log.debug("setting up jinja FileSystemLoader with dirs %s" % ", ".join(dirs))
        loader = FileSystemLoader(dirs)

        self.log.debug("setting up jinja environment")
        env = self.setup_jinja_env(loader=loader)

        env.filters['pygmentize'] = dexy.filters.templating_plugins.PygmentsStylesheet.highlight
        env.filters['rstcode'] = dexy.filters.templating_plugins.RstCode.rstcode
        env.filters['indent'] = dexy.filters.templating_plugins.JinjaFilters.indent
        env.filters['head'] = dexy.filters.templating_plugins.JinjaFilters.head
        env.filters['javadoc2rst'] = dexy.filters.templating_plugins.JavadocToRst.javadoc2rst
        if dexy.filters.templating_plugins.PrettyPrintHtml.is_active():
            env.filters['prettify_html'] = dexy.filters.templating_plugins.PrettyPrintHtml.prettify_html

        self.log.debug("initializing template")

        template_data = self.run_plugins()
        self.log.debug("jinja template data keys are %s" % ", ".join(sorted(template_data)))

        try:
            self.log.debug("about to create jinja template")
            template = env.get_template(self.input_filename())
            self.log.debug("about to process jinja template")
            template.stream(template_data).dump(self.output_filepath(), encoding="utf-8")
        except (TemplateSyntaxError, UndefinedError, TypeError) as e:
            try:
                self.log.debug("removing %s since jinja had an error" % self.output_filepath())
                os.remove(self.output_filepath())
            except os.error:
                pass
            self.handle_jinja_exception(e, self.input().as_text(), template_data)
        except TemplateNotFound as e:
            raise dexy.exceptions.UserFeedback("Jinja couldn't find the template '%s', make sure this file is an input to %s" % (e.message, self.artifact.doc.key))
        except Exception as e:
            try:
                self.log.debug("removing %s since jinja had an error" % self.output_filepath())
                os.remove(self.output_filepath())
            except os.error:
                pass
            self.log.debug(str(e))
            raise
