from dexy.commands.utils import import_extra_plugins
from dexy.commands.utils import init_wrapper
from dexy.commands.utils import template_text
from dexy.utils import getdoc
import dexy.template
import os
import sys
from dexy.utils import file_exists

DEFAULT_TEMPLATE = 'dexy:default'
def gen_command(
        plugins='', # extra python packages to load so plugins will register with dexy
        d=None,  # The directory to place generated files in, must not exist.
        t=False, # Shorter alternative to --template.
        template=DEFAULT_TEMPLATE, # The alias of the template to use.
        **kwargs # Additional kwargs passed to template's run() method.
        ):
    """
    Generate a new dexy project in the specified directory, using the template.
    """
    import_extra_plugins({'plugins' : plugins})

    if t and (template == DEFAULT_TEMPLATE):
        template = t
    elif t and template != DEFAULT_TEMPLATE:
        raise dexy.exceptions.UserFeedback("Only specify one of --t or --template, not both.")

    if not template in dexy.template.Template.aliases:
        print "Can't find a template named '%s'. Run 'dexy templates' for a list of templates." % template
        sys.exit(1)

    template_class = dexy.template.Template.aliases[template]
    template_class().run(d, **kwargs)

    # We run dexy setup. This will respect any dexy.conf file in the template
    # but passing command line options for 'setup' to 'gen' currently not supported.
    os.chdir(d)
    wrapper = init_wrapper({})
    wrapper.setup_dexy_dirs()
    print "Success! Your new dexy project has been created in directory '%s'" % d
    if file_exists("README"):
        with open("README", "r") as f:
            print f.read()
        print "\nThis information is in the 'README' file for future reference."

def template_command(
        alias=None
        ):
    print template_text(alias)

def templates_command(
        plugins='', # extra python packages to load so plugins will register with dexy
        simple=False, # Only print template names, without docstring or headers.
        validate=False # For developer use only, validate templates (runs and checks each template).
        ):
    """
    List templates that can be used to generate new projects.
    """
    import_extra_plugins({'plugins' : plugins})

    aliases = []
    for alias in sorted(dexy.template.Template.aliases):
        klass = dexy.template.Template.aliases[alias]
        if klass.is_active():
            aliases.append(alias)

    if simple:
        print "\n".join(aliases)
    else:
        FMT = "%-40s %s"
        print FMT % ("Alias", "Info")
        for alias in aliases:
            klass = dexy.template.Template.aliases[alias]
            print FMT % (alias, getdoc(klass)),
            if validate:
                print " validating...",
                print klass.validate() and "OK" or "ERROR"
            else:
                print ''

        if len(aliases) == 1:
            print "Run '[sudo] pip install dexy-templates' to install some more templates."

        print "Run 'dexy help -on gen' for help on generating projects from templates."
