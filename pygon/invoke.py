# Copyright (c) 2019 Nikita Tsarev
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""This module defines helper class for running solutions and
measuring their execution time."""

import os
import sys
import subprocess
import tempfile
from shutil import copyfile
from contextlib import contextmanager

import yaml
from pkg_resources import resource_filename

from pygon.testcase import Verdict
from pygon.language import Language
from pygon.config import CONFIG, BUILD_DIR


def get_exe_suffix():
    """Returns suffix of executable files: ".exe" on Windows, "" elsewhere."""

    if sys.platform in ["win32", "cygwin"]:
        return ".exe"

    return ""


def get_run_path():
    """Returns path to run utility executable."""

    if not CONFIG.get("custom_run") and sys.platform in ["win32", "cygwin"]:
        return resource_filename(
            "pygon",
            os.path.join("data", "run", "run_win32.exe")
        )


    return resource_filename(
        "pygon",
        os.path.join("data", BUILD_DIR, "run") + get_exe_suffix()
    )


def ensure_run_built():
    """Compile run utility if it isn't built."""

    if os.path.exists(get_run_path()):
        return

    if sys.platform == "win32":
        run_filename = "run_win32.cpp"
        lang = Language.from_name("c++03")
    else:
        run_filename = "run_posix.c"
        lang = Language.from_name("c99")

    lang.compile(
        resource_filename("pygon", os.path.join("data", "run", run_filename)),
        get_run_path(),
        []
    )


class InvokeResult:
    """Result of the invocation.

    Attributes:
        verdict: a Verdict
        time: time used in seconds
        memory: memory used in MiB
        comment: checker's comment
        icomment: interactor's comment
    """

    def __init__(self, verdict, time, memory, comment="", icomment=""):
        self.verdict = verdict
        self.time = time
        self.memory = memory
        self.comment = comment
        self.icomment = icomment

    def to_dict(self):
        return dict(
            verdict=self.verdict.value,
            time=self.time,
            memory=self.memory,
            comment=self.comment,
            icomment=self.icomment
        )

    @classmethod
    def from_dict(cls, data):
        return cls(verdict=Verdict(data["verdict"]),
                   time=data["time"],
                   memory=data["memory"],
                   comment=data["comment"],
                   icomment=data["icomment"])


class Invoke:
    """Helper class for running solutions, redirecting their stdin/stdout,
    measuring their time and memory usage.

    Attributes:
        cmd: command to run as a list of strings.
        cwd: working directory of the command.
        stdin: file-like instance to redirect stdin from.
        stdout: file-like instance to redirect stdout to.
        time_limit: time limit in seconds.
        memory_limit: memory limit in MiB.
    """

    def __init__(self, cmd, time_limit=1.0, memory_limit=256.0):
        """Construct an Invoke instance."""

        self.cmd = cmd
        self.cwd = None
        self.stdin = None
        self.stdout = None
        self.time_limit = time_limit
        self.memory_limit = memory_limit


    def run(self):
        """Run the command."""

        ensure_run_built()

        with tempfile.TemporaryDirectory() as dirpath:
            logpath = os.path.join(dirpath, "run.yaml")

            cmd = [
                get_run_path(),
                str(round(1000 * self.time_limit)),
                str(round(self.memory_limit)),
                str(round(5000 * self.time_limit)),
                logpath
            ] + self.cmd

            subprocess.run(cmd, stdin=self.stdin, stdout=self.stdout,
                           stderr=subprocess.DEVNULL, cwd=self.cwd,
                           check=True)

            with open(logpath) as logf:
                log = yaml.safe_load(logf.read())

            time_used = log["time"] / 1000
            memory_used = log["memory"]
            verdict = Verdict(log["verdict"])

            return InvokeResult(verdict, time_used, memory_used)

    @contextmanager
    def with_temp_cwd(self):
        """Use temporary working directory."""

        with tempfile.TemporaryDirectory() as dirpath:
            self.cwd = dirpath
            yield

        self.cwd = None

    @contextmanager
    def with_stdin(self, filename, path):
        """Redirect stdin transparently.

        Args:
            filename: a FileName instance, where will solution read input from?
            path: path to actual input file.
        """

        if filename.stdio:
            with open(path, 'rb') as input_file:
                self.stdin = input_file
                yield
        else:
            copyfile(path, os.path.join(self.cwd, filename.filename))
            self.stdin = subprocess.DEVNULL
            yield

        self.stdin = None

    @contextmanager
    def with_stdout(self, filename, path):
        """Redirect stdout transparently.

        Args:
            filename: a FileName instance, where will solution write to?
            path: path to output file.
        """

        if filename.stdio:
            with open(path, 'wb') as output_file:
                self.stdout = output_file
                yield
        else:
            self.stdout = subprocess.DEVNULL
            yield
            copyfile(os.path.join(self.cwd, filename.filename), path)

        self.stdout = None
