import os
import os.path
import sublime
import sublime_plugin
import subprocess
import tempfile

SETTINGS_FILE = "BeautifyRust.sublime-settings"


def temp_opener(name, flag, mode=0o777):
    return os.open(name, flag | os.O_TEMPORARY, mode)


def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)
    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
    return None


class BeautifyRustOnSave(sublime_plugin.EventListener):

    def on_pre_save(self, view):
        if sublime.load_settings(SETTINGS_FILE).get("run_on_save", False):
            return view.run_command("beautify_rust")
        return


class BeautifyRustCommand(sublime_plugin.TextCommand):

    ENCODING_UTF8 = "UTF-8"

    def run(self, edit):
        self.filename = self.view.file_name()
        self.fname = os.path.basename(self.filename)
        self.settings = sublime.load_settings(SETTINGS_FILE)
        if self.is_rust_file():
            self.run_format(edit)

    def is_rust_file(self):
        return self.fname.endswith(".rs")

    def pipe(self, cmd):
        cwd = os.path.dirname(self.filename)
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        beautifier = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            startupinfo=startupinfo)
        (_, err) = beautifier.communicate()
        return (beautifier.wait(), err.decode(self.ENCODING_UTF8))

    def run_format(self, edit):
        buffer_region = sublime.Region(0, self.view.size())
        buffer_text = self.view.substr(buffer_region)
        if buffer_text == "":
            return
        rustfmt_bin = which(self.settings.get("rustfmt", "rustfmt"))
        if rustfmt_bin is None:
            return sublime.error_message(
                "Beautify rust: can not find {0} in path.".format(self.settings.get("rustfmt", "rustfmt")))

        try:
            self.save_viewport_state()
            formatted_source = self.format_in_temporary_file(rustfmt_bin, buffer_text)
            self.view.replace(edit, buffer_region, formatted_source)
            self.reset_viewport_state()
        except Exception as ex:
            (exit_code, err) = ex.args
            self.view.replace(edit, buffer_region, buffer_text)
            print("failed: exit_code: {0}\n{1}".format(exit_code, err))
            if sublime.load_settings(SETTINGS_FILE).get("show_errors", True):
                sublime.error_message(
                    "Beautify rust: rustfmt process call failed. See log (ctrl + `) for details.")

    def save_viewport_state(self):
        self.previous_selection = [(region.a, region.b)
                                   for region in self.view.sel()]
        self.previous_position = self.view.viewport_position()

    def reset_viewport_state(self):
        self.view.set_viewport_position((0, 0,), False)
        self.view.set_viewport_position(self.previous_position, False)
        self.view.sel().clear()
        for a, b in self.previous_selection:
            self.view.sel().add(sublime.Region(a, b))

    def format_in_temporary_file(self, rustfmt_bin, rust_source):
        with tempfile.NamedTemporaryFile() as f:
            f.write(bytes(rust_source, self.ENCODING_UTF8))
            f.flush()

            cmd_list = [rustfmt_bin, f.name, "--write-mode=overwrite"] + self.settings.get("args", [])

            (exit_code, err) = self.pipe(cmd_list)
            if exit_code != 0 or (err != "" and not err.startswith("Using rustfmt")):
                raise Exception(exit_code, err)

            with open(f.name, "rb", opener=temp_opener) as f:
                return f.read().decode(self.ENCODING_UTF8)
