from dexy.common import OrderedDict
from dexy.exceptions import InternalDexyProblem
from dexy.exceptions import UserFeedback
from dexy.filters.process import SubprocessFilter
import re

try:
    import pexpect
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

class DexyEOFException(UserFeedback):
    pass

class PexpectReplFilter(SubprocessFilter):
    """
    Base class for filters which use pexpect to retrieve output line-by-line based on detecting prompts.
    """
    _SETTINGS = {
            'trim-prompt' : ("The closing prompt to be trimmed off.", '>>>'),
            'line-ending' : ("The line ending returned by REPL.", "\n"),
            'save-vars-to-json-cmd' : ("Command to be run to save variables to a JSON file.", None),
            'ps1' : ('PS1', None),
            'ps2' : ('PS2', None),
            'ps3' : ('PS3', None),
            'ps4' : ('PS4', None),
            'initial-prompt' : ("The initial prompt the REPL will display.", None),
            'prompt' : ("Single prompt to match exactly.", None),
            'prompts' : ("List of possible prompts to match exactly.", ['>>>', '...']),
            'prompt-regex' : ("A prompt regex to match.", None),
            'strip-regex' : ("Regex to strip", None),
            'output-data-type' : 'sectioned',
            'allow-match-prompt-without-newline' : ("Whether to require a newline before prompt.", False),
            }

    def is_active(klass):
        return AVAILABLE

    def prompt_search_terms(self):
        """
        Search first for the prompt (or prompts) following a line ending.
        Also optionally allow matching the prompt with no preceding line ending.
        """
        prompt_regex = self.setting('prompt-regex')
        prompt = self.setting('prompt')

        if prompt_regex:
            prompts = [prompt_regex]
        elif prompt:
            prompts = [prompt]
        else:
            prompts = self.setting('prompts')

        if self.setting('allow-match-prompt-without-newline'):
            return ["%s%s" % (self.setting('line-ending'), p) for p in prompts] + prompts
        else:
            return ["%s%s" % (self.setting('line-ending'), p) for p in prompts]

    def lines_for_section(self, section_text):
        """
        Take the section text and split it into lines which will be sent to the
        T
        differently, or if you don't want the extra newline at the end.
        """
        return section_text.splitlines() + ["\n"]

    def strip_trailing_prompts(self, section_transcript):
        lines = section_transcript.splitlines()
        while len(lines) > 0 and re.match("^\s*(%s)\s*$|^\s*$" % self.setting('trim-prompt'), lines[-1]):
            lines = lines[0:-1]
        return self.setting('line-ending').join(lines)

    def strip_newlines(self, line):
        return line.replace(" \r", "")

    def section_output(self, input_dict):
        """
        Runs the code in sections and returns an iterator so we can do custom stuff.
        """
        # If we want to automatically record values of local variables in the
        # script we are running, we add a section at the end of script
        do_record_vars = self.setting('record-vars')
        if do_record_vars:
            if not self.setting('save-vars-to-json-cmd'):
                raise UserFeedback("You specified record-vars but this option isn't available since SAVE_VARS_TO_JSON_CMD is not set for this filter.")

            section_text = self.setting('save-vars-to-json-cmd') % self.input().basename()
            self.log.debug("Adding save-vars-to-json-cmd code:\n%s" % section_text)
            input_dict['dexy--save-vars'] = section_text
            if not self.setting('add-new-files'):
                docstr = self._settings['add-new-files'][0]
                self._settings['add-new-files'] = (docstr, ".json")

        search_terms = self.prompt_search_terms()

        env = self.setup_env()

        if self.setting('ps1'):
            ps1 = self.setting('ps1')
            self.log.debug("Setting PS1 to %s" % ps1)
            env['PS1'] = ps1

        if self.setting('ps2'):
            ps2 = self.setting('PS2')
            self.log.debug("Setting PS2 to %s" % ps2)
            env['PS2'] = ps2

        if self.setting('ps3'):
            ps3 = self.arg_value('PS3')
            self.log.debug("Setting PS3 to %s" % ps3)
            env['PS3'] = ps3

        if self.setting('ps4'):
            ps4 = self.arg_value('PS4')
            self.log.debug("Setting PS4 to %s" % ps4)
            env['PS4'] = ps4

        timeout = self.setup_timeout()
        initial_timeout = self.setup_initial_timeout()

        self.log.debug("timeout set to '%s'" % timeout)

        wd=self.setup_wd()
        executable = self.setting('executable')
        self.log.debug("About to spawn new process '%s' in %s." % (executable, wd))

        # Spawn the process
        proc = pexpect.spawn(
                executable,
                cwd=wd,
                env=env)

        self.log.debug("Capturing initial prompt...")
        initial_prompt = self.setting('initial-prompt')
        try:
            if initial_prompt:
                proc.expect(initial_prompt, timeout=initial_timeout)
            elif self.setting('prompt-regex'):
                proc.expect(search_terms, timeout=initial_timeout)
            else:
                proc.expect_exact(search_terms, timeout=initial_timeout)

        except pexpect.TIMEOUT:
            if self.setting('initial-prompt'):
                match = self.setting('initial-prompt')
            else:
                match = search_terms

            msg = "%s failed at matching initial prompt within %s seconds. " % (self.__class__.__name__, initial_timeout)
            msg += "Received '%s', tried to match with '%s'" % (proc.before, match)
            msg += "\nExact characters received:\n"
            for i, c in enumerate(proc.before):
                msg += "chr %02d: %s\n" % (i, ord(c))
            msg += "The developer might need to set a longer initial prompt timeout or the regexp may be wrong."
            raise InternalDexyProblem(msg)

        start = proc.before + proc.after

        self.log.debug(u"Initial prompt captured!")
        self.log.debug(unicode(start))

        for section_key, section_text in input_dict.items():
            section_transcript = start
            start = ""

            lines = self.lines_for_section(section_text)
            for l in lines:
                self.log.debug(u"Sending '%s'" % l)
                section_transcript += start
                proc.send(l.rstrip() + "\n")
                try:
                    if self.setting('prompt-regex'):
                        proc.expect(search_terms, timeout=timeout)
                    else:
                        proc.expect_exact(search_terms, timeout=timeout)


                    self.log.debug(u"Received '%s'" % unicode(proc.before, errors='replace'))

                    section_transcript += self.strip_newlines(proc.before)
                    start = proc.after
                except pexpect.EOF:
                    self.log.debug("EOF occurred!")
                    raise DexyEOFException()
                except pexpect.TIMEOUT:
                    msg = "failed at matching prompt within %s seconds. " % timeout
                    msg += "received '%s', tried to match with '%s'" % (proc.before, search_terms)
                    msg += "something may have gone wrong, or you may need to set a longer timeout"
                    raise UserFeedback(msg)
                except pexpect.ExceptionPexpect as e:
                    raise UserFeedback(str(e))
                except pexpect.EOF as e:
                    raise UserFeedback(str(e))

            if self.setting('strip-regex'):
                section_transcript = re.sub(self.setting('strip-regex'), "", section_transcript)

            yield section_key, section_transcript

        if self.do_add_new_files():
            self.add_new_files()

        try:
            proc.close()
        except pexpect.ExceptionPexpect:
            raise UserFeedback("process %s may not have closed" % proc.pid)

        if proc.exitstatus and self.setting('check-return-code'):
            self.handle_subprocess_proc_return(self.setting('executable'), proc.exitstatus, section_transcript)

    def process(self):
        output = OrderedDict()

        for section_key, section_transcript in self.section_output(self.input().as_sectioned()):
            self.log.debug("Processing section %s" % section_key)
            section_output = self.strip_trailing_prompts(section_transcript)

            output[section_key] = section_output

        self.output().set_data(output)

try:
    import IPython
    IPYTHON_AVAILABLE = True
except ImportError:
    IPYTHON_AVAILABLE = False

class IpythonPexpectReplFilter(PexpectReplFilter):
    """
    Runs python code in ipython.
    """
    ALIASES = ['ipython']
    _SETTINGS = {
            'executable' : 'ipython --classic',
            'check-return-code' : False,
            'input-extensions' : [".txt", ".py"],
            'output-extensions' : [".pycon"],
            'version-command' : 'ipython -Version'
            }

    def is_active(klass):
        return IPYTHON_AVAILABLE

class ClojureInteractiveFilter(PexpectReplFilter):
    """
    Runs clojure.
    """
    ALIASES = ['clj', 'cljint']
    _SETTINGS = {
            'check-return-code' : False,
            'executable' : 'clojure -r',
            'input-extensions' : [".clj", ".txt"],
            'output-extensions' : [".txt"],
            'prompt' : "user=> "
            }

    def lines_for_section(self, input_text):
        input_lines = []
        current_line = []
        in_indented_block = False
        for l in input_text.splitlines():
            if re.match("^\s+", l):
                in_indented_block = True
                current_line.append(l)
            else:
                if len(current_line) > 0:
                    input_lines.append("\n".join(current_line))
                if in_indented_block:
                    # we have reached the end of this indented block
                    in_indented_block = False
                current_line = [l]
        input_lines.append("\n".join(current_line))
        return input_lines
