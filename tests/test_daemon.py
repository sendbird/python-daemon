# -*- coding: utf-8 -*-
#
# tests/test_daemon.py
#
# Copyright © 2008–2009 Ben Finney <ben+python@benfinney.id.au>
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Python Software Foundation License, version 2 or
# later as published by the Python Software Foundation.
# No warranty expressed or implied. See the file LICENSE.PSF-2 for details.

""" Unit test for daemon module
"""

import __builtin__
import os
import sys
from StringIO import StringIO
import tempfile
import resource
import errno
import signal

import scaffold
from test_pidlockfile import (
    FakeFileDescriptorStringIO,
    setup_pidfile_fixtures,
    )

from daemon import pidlockfile
import daemon


class prevent_core_dump_TestCase(scaffold.TestCase):
    """ Test cases for prevent_core_dump function """

    def setUp(self):
        """ Set up test fixtures """
        self.mock_outfile = StringIO()
        self.mock_tracker = scaffold.MockTracker(self.mock_outfile)

        self.RLIMIT_CORE = object()
        scaffold.mock(
            "resource.RLIMIT_CORE", mock_obj=self.RLIMIT_CORE,
            tracker=self.mock_tracker)
        scaffold.mock(
            "resource.getrlimit", returns=None,
            tracker=self.mock_tracker)
        scaffold.mock(
            "resource.setrlimit", returns=None,
            tracker=self.mock_tracker)

    def tearDown(self):
        """ Tear down test fixtures """
        scaffold.mock_restore()

    def test_sets_core_limit_to_zero(self):
        """ Should set the RLIMIT_CORE resource to zero """
        expect_resource = self.RLIMIT_CORE
        expect_limit = (0, 0)
        expect_mock_output = """\
            Called resource.getrlimit(
                %(expect_resource)r)
            Called resource.setrlimit(
                %(expect_resource)r,
                %(expect_limit)r)
            """ % vars()
        daemon.daemon.prevent_core_dump()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_raises_error_when_no_core_resource(self):
        """ Should raise ValueError if no RLIMIT_CORE resource """
        def mock_getrlimit(res):
            if res == resource.RLIMIT_CORE:
                raise ValueError("Bogus platform doesn't have RLIMIT_CORE")
            else:
                return None
        resource.getrlimit.mock_returns_func = mock_getrlimit
        expect_error = ValueError
        self.failUnlessRaises(
            expect_error,
            daemon.daemon.prevent_core_dump)


class detach_process_context_TestCase(scaffold.TestCase):
    """ Test cases for detach_process_context function """

    def setUp(self):
        """ Set up test fixtures """
        self.mock_outfile = StringIO()
        self.mock_tracker = scaffold.MockTracker(self.mock_outfile)

        self.mock_stderr = FakeFileDescriptorStringIO()

        test_pids = [0, 0]
        scaffold.mock(
            "os.fork", returns_iter=test_pids,
            tracker=self.mock_tracker)
        scaffold.mock(
            "os.setsid",
            tracker=self.mock_tracker)

        def raise_system_exit(status=None):
            raise SystemExit(status)

        scaffold.mock(
            "sys.exit", returns_func=raise_system_exit,
            tracker=self.mock_tracker)

        scaffold.mock(
            "sys.stderr",
            mock_obj=self.mock_stderr,
            tracker=self.mock_tracker)

    def tearDown(self):
        """ Tear down test fixtures """
        scaffold.mock_restore()

    def test_parent_exits(self):
        """ Parent process should exit """
        parent_pid = 23
        scaffold.mock("os.fork", returns_iter=[parent_pid],
            tracker=self.mock_tracker)
        self.failUnlessRaises(
            SystemExit,
            daemon.daemon.detach_process_context)
        expect_mock_output = """\
            Called os.fork()
            Called sys.exit(0)
            """
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_first_fork_error_reports_to_stderr(self):
        """ Error on first fork should cause report to stderr """
        fork_errno = 13
        fork_strerror = "Bad stuff happened"
        fork_error = OSError(fork_errno, fork_strerror)
        test_pids_iter = iter([fork_error])

        def mock_fork():
            next = test_pids_iter.next()
            if isinstance(next, Exception):
                raise next
            else:
                return next

        scaffold.mock("os.fork", returns_func=mock_fork,
            tracker=self.mock_tracker)
        self.failUnlessRaises(
            SystemExit,
            daemon.daemon.detach_process_context)
        expect_mock_output = """\
            Called os.fork()
            Called sys.exit(1)
            """
        expect_stderr = """\
            fork #1 failed: ...%(fork_errno)d...%(fork_strerror)s...
            """ % vars()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())
        self.failUnlessOutputCheckerMatch(
            expect_stderr, self.mock_stderr.getvalue())

    def test_child_starts_new_process_group(self):
        """ Child should start new process group """
        expect_mock_output = """\
            Called os.fork()
            Called os.setsid()
            ...
            """
        daemon.daemon.detach_process_context()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_child_forks_next_parent_exits(self):
        """ Child should fork, then exit if parent """
        test_pids = [0, 42]
        scaffold.mock("os.fork", returns_iter=test_pids,
            tracker=self.mock_tracker)
        self.failUnlessRaises(
            SystemExit,
            daemon.daemon.detach_process_context)
        expect_mock_output = """\
            Called os.fork()
            Called os.setsid()
            Called os.fork()
            Called sys.exit(0)
            """
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_second_fork_error_reports_to_stderr(self):
        """ Error on second fork should cause report to stderr """
        fork_errno = 17
        fork_strerror = "Nasty stuff happened"
        fork_error = OSError(fork_errno, fork_strerror)
        test_pids_iter = iter([0, fork_error])

        def mock_fork():
            next = test_pids_iter.next()
            if isinstance(next, Exception):
                raise next
            else:
                return next

        scaffold.mock("os.fork", returns_func=mock_fork,
            tracker=self.mock_tracker)
        self.failUnlessRaises(
            SystemExit,
            daemon.daemon.detach_process_context)
        expect_mock_output = """\
            Called os.fork()
            Called os.setsid()
            Called os.fork()
            Called sys.exit(1)
            """
        expect_stderr = """\
            fork #2 failed: ...%(fork_errno)d...%(fork_strerror)s...
            """ % vars()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())
        self.failUnlessOutputCheckerMatch(
            expect_stderr, self.mock_stderr.getvalue())

    def test_child_forks_next_child_continues(self):
        """ Child should fork, then continue if child """
        expect_mock_output = """\
            Called os.fork()
            Called os.setsid()
            Called os.fork()
            """ % vars()
        daemon.daemon.detach_process_context()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())


def setup_streams_fixtures(testcase):
    """ Set up common test fixtures for standard streams """
    testcase.mock_outfile = StringIO()
    testcase.mock_tracker = scaffold.MockTracker(
        testcase.mock_outfile)

    testcase.stream_file_paths = dict(
        stdin = tempfile.mktemp(),
        stdout = tempfile.mktemp(),
        stderr = tempfile.mktemp(),
        )

    testcase.stream_files_by_name = dict(
        (name, FakeFileDescriptorStringIO())
        for name in ['stdin', 'stdout', 'stderr']
        )

    testcase.stream_files_by_path = dict(
        (testcase.stream_file_paths[name],
            testcase.stream_files_by_name[name])
        for name in ['stdin', 'stdout', 'stderr']
        )

    scaffold.mock(
        "os.dup2",
        tracker=testcase.mock_tracker)


class redirect_stream_TestCase(scaffold.TestCase):
    """ Test cases for redirect_stream function """

    def setUp(self):
        """ Set up test fixtures """
        setup_streams_fixtures(self)

    def tearDown(self):
        """ Tear down test fixtures """
        scaffold.mock_restore()

    def test_duplicates_file_descriptor(self):
        """ Should duplicate file descriptor from target to system stream """
        system_stream = FakeFileDescriptorStringIO()
        system_fileno = system_stream.fileno()
        target_stream = FakeFileDescriptorStringIO()
        target_fileno = target_stream.fileno()
        expect_mock_output = """\
            Called os.dup2(%(target_fileno)r, %(system_fileno)r)
            """ % vars()
        daemon.daemon.redirect_stream(system_stream, target_stream)
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())


def setup_daemon_context_fixtures(testcase):
    """ Set up common test fixtures for DaemonContext test case """

    testcase.mock_outfile = StringIO()
    testcase.mock_tracker = scaffold.MockTracker(
        testcase.mock_outfile)

    setup_pidfile_fixtures(testcase)
    setup_streams_fixtures(testcase)

    testcase.mock_pidfile_path = tempfile.mktemp()

    testcase.mock_pidlockfile = scaffold.Mock(
        "pidlockfile.PIDLockFile",
        tracker=testcase.mock_tracker)
    testcase.mock_pidlockfile.path = testcase.mock_pidfile_path

    scaffold.mock(
        "pidlockfile.abort_if_existing_pidfile",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "pidlockfile.abort_if_no_existing_pidfile",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "pidlockfile.read_pid_from_pidfile",
        returns=testcase.mock_pid,
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "pidlockfile.write_pid_to_pidfile",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "pidlockfile.remove_existing_pidfile",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "pidlockfile.PIDLockFile",
        returns=testcase.mock_pidlockfile,
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "daemon.daemon.detach_process_context",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "daemon.daemon.prevent_core_dump",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "daemon.daemon.redirect_stream",
        tracker=testcase.mock_tracker)

    testcase.mock_stderr = FakeFileDescriptorStringIO()

    testcase.daemon_context_args = dict(
        pidfile_path = testcase.mock_pidfile_path,
        stdin = testcase.stream_files_by_name['stdin'],
        stdout = testcase.stream_files_by_name['stdout'],
        stderr = testcase.stream_files_by_name['stderr'],
        )
    testcase.test_instance = daemon.DaemonContext(
        **testcase.daemon_context_args)

    def mock_open(filename, mode=None, buffering=None):
        if filename in testcase.stream_files_by_path:
            result = testcase.stream_files_by_path[filename]
        else:
            result = FakeFileDescriptorStringIO()
        return result

    scaffold.mock(
        "__builtin__.open",
        returns_func=mock_open,
        tracker=testcase.mock_tracker)

    scaffold.mock(
        "os.kill",
        tracker=testcase.mock_tracker)

    scaffold.mock(
        "sys.stdin",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "sys.stdout",
        tracker=testcase.mock_tracker)
    scaffold.mock(
        "sys.stderr",
        mock_obj=testcase.mock_stderr,
        tracker=testcase.mock_tracker)


class DaemonContext_TestCase(scaffold.TestCase):
    """ Test cases for DaemonContext class """

    def setUp(self):
        """ Set up test fixtures """
        setup_daemon_context_fixtures(self)

    def tearDown(self):
        """ Tear down test fixtures """
        scaffold.mock_restore()

    def test_instantiate(self):
        """ New instance of DaemonContext should be created """
        self.failUnlessIsInstance(
            self.test_instance, daemon.daemon.DaemonContext)

    def test_requires_no_arguments(self):
        """ Initialiser should not require any arguments """
        instance = daemon.daemon.DaemonContext()
        self.failIfIs(None, instance)

    def test_has_specified_pidfile_path(self):
        """ Should have specified pidlockfile """
        args = dict(
            pidfile_path = "/foo/bar",
            )
        expect_lockfile = self.mock_pidlockfile
        instance = daemon.daemon.DaemonContext(**args)
        self.failUnlessIs(expect_lockfile, instance.pidlockfile)

    def test_has_specified_stdin(self):
        """ Should have specified stdin option """
        args = dict(
            stdin = object(),
            )
        expect_file = args['stdin']
        instance = daemon.daemon.DaemonContext(**args)
        self.failUnlessEqual(expect_file, instance.stdin)

    def test_has_specified_stdout(self):
        """ Should have specified stdout option """
        args = dict(
            stdout = object(),
            )
        expect_file = args['stdout']
        instance = daemon.daemon.DaemonContext(**args)
        self.failUnlessEqual(expect_file, instance.stdout)

    def test_has_specified_stderr(self):
        """ Should have specified stderr option """
        args = dict(
            stderr = object(),
            )
        expect_file = args['stderr']
        instance = daemon.daemon.DaemonContext(**args)
        self.failUnlessEqual(expect_file, instance.stderr)

    def test_error_when_pidfile_path_not_string(self):
        """ Should raise ValueError when PID file path not a string """
        pidfile_path = object()
        args = dict(
            pidfile_path = pidfile_path,
            )
        expect_error = ValueError
        self.failUnlessRaises(
            expect_error,
            daemon.DaemonContext, **args)

    def test_error_when_pidfile_path_not_absolute(self):
        """ Should raise ValueError when PID file path not absolute """
        pidfile_path = "foo/bar.pid"
        args = dict(
            pidfile_path = pidfile_path,
            )
        expect_error = ValueError
        self.failUnlessRaises(
            expect_error,
            daemon.DaemonContext, **args)

    def test_creates_pidlockfile(self):
        """ Should create a PIDLockFile with the specified PID file name """
        instance = self.test_instance
        pidfile_path = self.mock_pidfile_path
        expect_mock_output = """\
            Called pidlockfile.PIDLockFile(%(pidfile_path)r)
            """ % vars()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())


class DaemonContext_start_TestCase(scaffold.TestCase):
    """ Test cases for DaemonContext.start method """

    def setUp(self):
        """ Set up test fixtures """
        setup_daemon_context_fixtures(self)

    def tearDown(self):
        """ Tear down test fixtures """
        scaffold.mock_restore()

    def test_aborts_if_pidfile_locked(self):
        """ Should raise SystemExit if PID file is locked """
        instance = self.test_instance
        self.mock_pidlockfile.is_locked.mock_returns = True
        try:
            instance.start()
        except SystemExit, exc:
            pass
        else:
            raise self.failureException("Failed to raise SystemExit")
        self.failUnlessIn(exc.message, self.mock_pidfile_path)

    def test_detaches_process_context(self):
        """ Should request detach of process context """
        instance = self.test_instance
        expect_mock_output = """\
            ...
            Called daemon.daemon.detach_process_context()
            ...
            """ % vars()
        instance.start()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_prevents_core_dump(self):
        """ Should request prevention of core dumps """
        instance = self.test_instance
        expect_mock_output = """\
            ...
            Called daemon.daemon.prevent_core_dump()
            ...
            """ % vars()
        instance.start()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_acquires_pidfile_lock(self):
        """ Should acquire the PID file lock """
        instance = self.test_instance
        expect_mock_output = """\
            ...
            Called pidlockfile.PIDLockFile.acquire()
            ...
            """
        instance.start()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_redirects_standard_streams(self):
        """ Should request redirection of standard stream files """
        instance = self.test_instance
        (system_stdin, system_stdout, system_stderr) = (
            sys.stdin, sys.stdout, sys.stderr)
        (target_stdin, target_stdout, target_stderr) = (
            self.stream_files_by_name[name]
            for name in ['stdin', 'stdout', 'stderr'])
        expect_mock_output = """\
            ...
            Called daemon.daemon.redirect_stream(
                %(system_stdin)r, %(target_stdin)r)
            Called daemon.daemon.redirect_stream(
                %(system_stdout)r, %(target_stdout)r)
            Called daemon.daemon.redirect_stream(
                %(system_stderr)r, %(target_stderr)r)
            """ % vars()
        instance.start()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())


class DaemonContext_stop_TestCase(scaffold.TestCase):
    """ Test cases for DaemonContext.stop method """

    def setUp(self):
        """ Set up test fixtures """
        setup_daemon_context_fixtures(self)
        self.mock_pidlockfile.is_locked.mock_returns = True
        self.mock_pidlockfile.i_am_locking.mock_returns = True

        self.pidfile_open_func = self.mock_pidfile_open_exist

    def tearDown(self):
        """ Tear down test fixtures """
        scaffold.mock_restore()

    def test_aborts_if_pidfile_not_locked(self):
        """ Should raise SystemExit if PID file is not locked """
        instance = self.test_instance
        self.mock_pidlockfile.i_am_locking.mock_returns = False
        try:
            instance.stop()
        except SystemExit, exc:
            pass
        else:
            raise self.failureException("Failed to raise SystemExit")
        self.failUnlessIn(exc.message, self.mock_pidfile_path)

    def test_releases_pidfile_lock(self):
        """ Should release the PID file lock """
        instance = self.test_instance
        expect_mock_output = """\
            ...
            Called pidlockfile.PIDLockFile.release()
            ...
            """
        instance.stop()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())

    def test_sends_terminate_signal_to_process(self):
        """ Should send SIGTERM to the daemon process """
        instance = self.test_instance
        pid = self.mock_pid
        expect_signal = signal.SIGTERM
        expect_mock_output = """\
            ...
            Called os.kill(%(pid)r, %(expect_signal)r)
            """ % vars()
        instance.stop()
        scaffold.mock_restore()
        self.failUnlessOutputCheckerMatch(
            expect_mock_output, self.mock_outfile.getvalue())
