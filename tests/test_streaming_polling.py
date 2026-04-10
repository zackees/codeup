import unittest
from unittest.mock import patch


class _FakeEndOfStream:
    pass


class _ModuleEndOfStream:
    pass


class _ScriptedRunningProcess:
    end_of_stream_type = _FakeEndOfStream
    script = []

    def __init__(self, *args, **kwargs):
        self._script = list(type(self).script)
        self.returncode = 0
        self.killed = False

    def get_next_line(self, timeout=None):
        if not self._script:
            return _FakeEndOfStream()
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def poll(self):
        if self._script and any(
            not isinstance(item, _FakeEndOfStream) for item in self._script
        ):
            return None
        return self.returncode

    @property
    def finished(self):
        return self.poll() is not None

    def is_running(self):
        return any(not isinstance(item, _FakeEndOfStream) for item in self._script)

    def wait(self):
        return self.returncode

    def kill(self):
        self.killed = True


class _LegacyRunningProcess:
    script = []

    def __init__(self, *args, **kwargs):
        self._script = list(type(self).script)
        self.returncode = 0
        self.killed = False

    def get_next_line(self, timeout=None):
        if not self._script:
            raise TimeoutError("Process finished without end-of-stream sentinel")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def poll(self):
        if self._script:
            return None
        return self.returncode

    @property
    def finished(self):
        return self.poll() is not None

    def wait(self):
        return self.returncode

    def kill(self):
        self.killed = True


class StreamingPollingTests(unittest.TestCase):
    def test_run_command_streaming_treats_quiet_period_as_polling(self):
        from codeup import main

        _ScriptedRunningProcess.script = [
            TimeoutError("No combined output available before timeout"),
            "hello",
            _FakeEndOfStream(),
        ]

        with (
            patch("codeup.main.RunningProcess", _ScriptedRunningProcess),
            patch("codeup.utils.is_interrupted", return_value=False),
        ):
            code, stdout, stderr = main._run_command_streaming(
                ["dummy"], quiet=True, capture_output=True
            )

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "hello")
        self.assertEqual(stderr, "")

    def test_command_runner_treats_quiet_period_as_polling(self):
        from codeup import command_runner

        _ScriptedRunningProcess.script = [
            TimeoutError("No combined output available before timeout"),
            "lint ok",
            _FakeEndOfStream(),
        ]

        with (
            patch("codeup.command_runner.RunningProcess", _ScriptedRunningProcess),
            patch("codeup.utils.is_interrupted", return_value=False),
        ):
            code, stdout, stderr, stopped_early = (
                command_runner.run_command_with_callback(["dummy"], on_line=None)
            )

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "lint ok")
        self.assertEqual(stderr, "")
        self.assertFalse(stopped_early)

    def test_exec_treats_quiet_period_as_polling(self):
        from codeup import utils

        _ScriptedRunningProcess.script = [
            TimeoutError("No combined output available before timeout"),
            "done",
            _FakeEndOfStream(),
        ]

        with (
            patch("codeup.utils.RunningProcess", _ScriptedRunningProcess),
            patch("codeup.utils.is_interrupted", return_value=False),
        ):
            code = utils._exec("echo done", bash=False, die=False)

        self.assertEqual(code, 0)

    def test_run_command_streaming_recognizes_module_end_of_stream_without_process_attr(
        self,
    ):
        from codeup import main

        _LegacyRunningProcess.script = [
            TimeoutError("No combined output available before timeout"),
            "hello",
            _ModuleEndOfStream(),
        ]

        with (
            patch("codeup.main.RunningProcess", _LegacyRunningProcess),
            patch("codeup.utils._RunningProcessEndOfStream", _ModuleEndOfStream),
            patch("codeup.utils.is_interrupted", return_value=False),
        ):
            code, stdout, stderr = main._run_command_streaming(
                ["dummy"], quiet=True, capture_output=True
            )

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "hello")
        self.assertEqual(stderr, "")

    def test_command_runner_recognizes_module_end_of_stream_without_process_attr(self):
        from codeup import command_runner

        _LegacyRunningProcess.script = [
            TimeoutError("No combined output available before timeout"),
            "lint ok",
            _ModuleEndOfStream(),
        ]

        with (
            patch("codeup.command_runner.RunningProcess", _LegacyRunningProcess),
            patch("codeup.utils._RunningProcessEndOfStream", _ModuleEndOfStream),
            patch("codeup.utils.is_interrupted", return_value=False),
        ):
            code, stdout, stderr, stopped_early = (
                command_runner.run_command_with_callback(["dummy"], on_line=None)
            )

        self.assertEqual(code, 0)
        self.assertEqual(stdout, "lint ok")
        self.assertEqual(stderr, "")
        self.assertFalse(stopped_early)

    def test_exec_recognizes_module_end_of_stream_without_process_attr(self):
        from codeup import utils

        _LegacyRunningProcess.script = [
            TimeoutError("No combined output available before timeout"),
            "done",
            _ModuleEndOfStream(),
        ]

        with (
            patch("codeup.utils.RunningProcess", _LegacyRunningProcess),
            patch("codeup.utils._RunningProcessEndOfStream", _ModuleEndOfStream),
            patch("codeup.utils.is_interrupted", return_value=False),
        ):
            code = utils._exec("echo done", bash=False, die=False)

        self.assertEqual(code, 0)
