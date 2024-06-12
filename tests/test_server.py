import errno
import socket
import unittest

from waitress.compat import VSOCK

dummy_app = object()


class TestWSGIServer(unittest.TestCase):
    def _makeOne(
        self,
        application=dummy_app,
        host="127.0.0.1",
        port=0,
        _dispatcher=None,
        adj=None,
        map=None,
        _start=True,
        _sock=None,
        _server=None,
    ):
        from waitress.server import create_server

        self.inst = create_server(
            application,
            host=host,
            port=port,
            map=map,
            _dispatcher=_dispatcher,
            _start=_start,
            _sock=_sock,
        )
        return self.inst

    def _makeOneWithMap(
        self, adj=None, _start=True, host="127.0.0.1", port=0, app=dummy_app
    ):
        sock = DummySock()
        task_dispatcher = DummyTaskDispatcher()
        map = {}
        return self._makeOne(
            app,
            host=host,
            port=port,
            map=map,
            _sock=sock,
            _dispatcher=task_dispatcher,
            _start=_start,
        )

    def _makeOneWithMulti(
        self, adj=None, _start=True, app=dummy_app, listen="127.0.0.1:0 127.0.0.1:0"
    ):
        sock = DummySock()
        task_dispatcher = DummyTaskDispatcher()
        map = {}
        from waitress.server import create_server

        self.inst = create_server(
            app,
            listen=listen,
            map=map,
            _dispatcher=task_dispatcher,
            _start=_start,
            _sock=sock,
        )
        return self.inst

    def _makeWithSockets(
        self,
        application=dummy_app,
        _dispatcher=None,
        map=None,
        _start=True,
        _sock=None,
        _server=None,
        sockets=None,
    ):
        from waitress.server import create_server

        _sockets = []
        if sockets is not None:
            _sockets = sockets
        self.inst = create_server(
            application,
            map=map,
            _dispatcher=_dispatcher,
            _start=_start,
            _sock=_sock,
            sockets=_sockets,
        )
        return self.inst

    def tearDown(self):
        if self.inst is not None:
            self.inst.close()

    def test_ctor_app_is_None(self):
        self.inst = None
        self.assertRaises(ValueError, self._makeOneWithMap, app=None)

    def test_ctor_start_true(self):
        inst = self._makeOneWithMap(_start=True)
        self.assertEqual(inst.accepting, True)
        self.assertEqual(inst.socket.listened, 1024)

    def test_ctor_makes_dispatcher(self):
        inst = self._makeOne(_start=False, map={})
        self.assertEqual(
            inst.task_dispatcher.__class__.__name__, "ThreadedTaskDispatcher"
        )

    def test_ctor_start_false(self):
        inst = self._makeOneWithMap(_start=False)
        self.assertEqual(inst.accepting, False)

    def test_get_server_multi(self):
        inst = self._makeOneWithMulti()
        self.assertEqual(inst.__class__.__name__, "MultiSocketServer")

    def test_run(self):
        inst = self._makeOneWithMap(_start=False)
        inst.asyncore = DummyAsyncore()
        inst.task_dispatcher = DummyTaskDispatcher()
        inst.run()
        self.assertTrue(inst.task_dispatcher.was_shutdown)

    def test_run_base_server(self):
        inst = self._makeOneWithMulti(_start=False)
        inst.asyncore = DummyAsyncore()
        inst.task_dispatcher = DummyTaskDispatcher()
        inst.run()
        self.assertTrue(inst.task_dispatcher.was_shutdown)

    def test_pull_trigger(self):
        inst = self._makeOneWithMap(_start=False)
        inst.trigger.close()
        inst.trigger = DummyTrigger()
        inst.pull_trigger()
        self.assertEqual(inst.trigger.pulled, True)

    def test_add_task(self):
        task = DummyTask()
        inst = self._makeOneWithMap()
        inst.add_task(task)
        self.assertEqual(inst.task_dispatcher.tasks, [task])
        self.assertFalse(task.serviced)

    def test_readable_not_accepting(self):
        inst = self._makeOneWithMap()
        inst.accepting = False
        self.assertFalse(inst.readable())

    def test_readable_maplen_gt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {"a": 1, "b": 2}
        self.assertFalse(inst.readable())
        self.assertTrue(inst.in_connection_overflow)

    def test_readable_maplen_lt_connection_limit(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {}
        self.assertTrue(inst.readable())
        self.assertFalse(inst.in_connection_overflow)

    def test_readable_maplen_toggles_connection_overflow(self):
        inst = self._makeOneWithMap()
        inst.accepting = True
        inst.adj = DummyAdj
        inst._map = {"a": 1, "b": 2}
        self.assertFalse(inst.in_connection_overflow)
        self.assertFalse(inst.readable())
        self.assertTrue(inst.in_connection_overflow)
        inst._map = {}
        self.assertTrue(inst.readable())
        self.assertFalse(inst.in_connection_overflow)

    def test_readable_maintenance_false(self):
        import time

        inst = self._makeOneWithMap()
        then = time.time() + 1000
        inst.next_channel_cleanup = then
        L = []
        inst.maintenance = lambda t: L.append(t)
        inst.readable()
        self.assertEqual(L, [])
        self.assertEqual(inst.next_channel_cleanup, then)

    def test_readable_maintenance_true(self):
        inst = self._makeOneWithMap()
        inst.next_channel_cleanup = 0
        L = []
        inst.maintenance = lambda t: L.append(t)
        inst.readable()
        self.assertEqual(len(L), 1)
        self.assertNotEqual(inst.next_channel_cleanup, 0)

    def test_writable(self):
        inst = self._makeOneWithMap()
        self.assertFalse(inst.writable())

    def test_handle_read(self):
        inst = self._makeOneWithMap()
        self.assertEqual(inst.handle_read(), None)

    def test_handle_connect(self):
        inst = self._makeOneWithMap()
        self.assertEqual(inst.handle_connect(), None)

    def test_handle_accept_wouldblock_socket_error(self):
        inst = self._makeOneWithMap()
        ewouldblock = socket.error(errno.EWOULDBLOCK)
        inst.socket = DummySock(toraise=ewouldblock)
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, False)

    def test_handle_accept_other_socket_error(self):
        inst = self._makeOneWithMap()
        eaborted = socket.error(errno.ECONNABORTED)
        inst.socket = DummySock(toraise=eaborted)
        inst.adj = DummyAdj

        def foo():
            raise OSError

        inst.accept = foo
        inst.logger = DummyLogger()
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, False)
        self.assertEqual(len(inst.logger.logged), 1)

    def test_handle_accept_noerror(self):
        inst = self._makeOneWithMap()
        innersock = DummySock()
        inst.socket = DummySock(acceptresult=(innersock, None))
        inst.adj = DummyAdj
        L = []
        inst.channel_class = lambda *arg, **kw: L.append(arg)
        inst.handle_accept()
        self.assertEqual(inst.socket.accepted, True)
        self.assertEqual(innersock.opts, [("level", "optname", "value")])
        self.assertEqual(L, [(inst, innersock, None, inst.adj)])

    def test_maintenance(self):
        inst = self._makeOneWithMap()

        class DummyChannel:
            requests = []

        zombie = DummyChannel()
        zombie.last_activity = 0
        zombie.running_tasks = False
        inst.active_channels[100] = zombie
        inst.maintenance(10000)
        self.assertEqual(zombie.will_close, True)

    def test_backward_compatibility(self):
        from waitress.adjustments import Adjustments
        from waitress.server import TcpWSGIServer, WSGIServer

        self.assertTrue(WSGIServer is TcpWSGIServer)
        self.inst = WSGIServer(None, _start=False, port=1234)
        # Ensure the adjustment was actually applied.
        self.assertNotEqual(Adjustments.port, 1234)
        self.assertEqual(self.inst.adj.port, 1234)

    def test_create_with_one_tcp_socket(self):
        from waitress.server import TcpWSGIServer

        sockets = [socket.socket(socket.AF_INET, socket.SOCK_STREAM)]
        sockets[0].bind(("127.0.0.1", 0))
        inst = self._makeWithSockets(_start=False, sockets=sockets)
        self.assertTrue(isinstance(inst, TcpWSGIServer))

    def test_create_with_multiple_tcp_sockets(self):
        from waitress.server import MultiSocketServer

        sockets = [
            socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            socket.socket(socket.AF_INET, socket.SOCK_STREAM),
        ]
        sockets[0].bind(("127.0.0.1", 0))
        sockets[1].bind(("127.0.0.1", 0))
        inst = self._makeWithSockets(_start=False, sockets=sockets)
        self.assertTrue(isinstance(inst, MultiSocketServer))
        self.assertEqual(len(inst.effective_listen), 2)

    def test_create_with_one_socket_should_not_bind_socket(self):
        innersock = DummySock()
        sockets = [DummySock(acceptresult=(innersock, None))]
        sockets[0].bind(("127.0.0.1", 80))
        sockets[0].bind_called = False
        inst = self._makeWithSockets(_start=False, sockets=sockets)
        self.assertEqual(inst.socket.bound, ("127.0.0.1", 80))
        self.assertFalse(inst.socket.bind_called)

    def test_create_with_one_socket_handle_accept_noerror(self):
        innersock = DummySock()
        sockets = [DummySock(acceptresult=(innersock, None))]
        sockets[0].bind(("127.0.0.1", 80))
        inst = self._makeWithSockets(sockets=sockets)
        L = []
        inst.channel_class = lambda *arg, **kw: L.append(arg)
        inst.adj = DummyAdj
        inst.handle_accept()
        self.assertEqual(sockets[0].accepted, True)
        self.assertEqual(innersock.opts, [("level", "optname", "value")])
        self.assertEqual(L, [(inst, innersock, None, inst.adj)])


if hasattr(socket, "AF_UNIX"):

    class TestUnixWSGIServer(unittest.TestCase):
        unix_socket = "/tmp/waitress.test.sock"

        def _makeOne(self, _start=True, _sock=None):
            from waitress.server import create_server

            self.inst = create_server(
                dummy_app,
                map={},
                _start=_start,
                _sock=_sock,
                _dispatcher=DummyTaskDispatcher(),
                unix_socket=self.unix_socket,
                unix_socket_perms="600",
            )
            return self.inst

        def _makeWithSockets(
            self,
            application=dummy_app,
            _dispatcher=None,
            map=None,
            _start=True,
            _sock=None,
            _server=None,
            sockets=None,
        ):
            from waitress.server import create_server

            _sockets = []
            if sockets is not None:
                _sockets = sockets
            self.inst = create_server(
                application,
                map=map,
                _dispatcher=_dispatcher,
                _start=_start,
                _sock=_sock,
                sockets=_sockets,
            )
            return self.inst

        def tearDown(self):
            self.inst.close()

        def _makeDummy(self, *args, **kwargs):
            sock = DummySock(*args, **kwargs)
            sock.family = socket.AF_UNIX
            return sock

        def test_unix(self):
            inst = self._makeOne(_start=False)
            self.assertEqual(inst.socket.family, socket.AF_UNIX)
            self.assertEqual(inst.socket.getsockname(), self.unix_socket)

        def test_handle_accept(self):
            # Working on the assumption that we only have to test the happy path
            # for Unix domain sockets as the other paths should've been covered
            # by inet sockets.
            client = self._makeDummy()
            listen = self._makeDummy(acceptresult=(client, None))
            inst = self._makeOne(_sock=listen)
            self.assertEqual(inst.accepting, True)
            self.assertEqual(inst.socket.listened, 1024)
            L = []
            inst.channel_class = lambda *arg, **kw: L.append(arg)
            inst.handle_accept()
            self.assertEqual(inst.socket.accepted, True)
            self.assertEqual(client.opts, [])
            self.assertEqual(L, [(inst, client, ("localhost", None), inst.adj)])

        def test_creates_new_sockinfo(self):
            from waitress.server import UnixWSGIServer

            self.inst = UnixWSGIServer(
                dummy_app, unix_socket=self.unix_socket, unix_socket_perms="600"
            )

            self.assertEqual(self.inst.sockinfo[0], socket.AF_UNIX)

        def test_create_with_unix_socket(self):
            from waitress.server import (
                BaseWSGIServer,
                MultiSocketServer,
                TcpWSGIServer,
                UnixWSGIServer,
            )

            sockets = [
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
                socket.socket(socket.AF_UNIX, socket.SOCK_STREAM),
            ]
            inst = self._makeWithSockets(sockets=sockets, _start=False)
            self.assertTrue(isinstance(inst, MultiSocketServer))
            server = list(
                filter(lambda s: isinstance(s, BaseWSGIServer), inst.map.values())
            )
            self.assertTrue(isinstance(server[0], UnixWSGIServer))
            self.assertTrue(isinstance(server[1], UnixWSGIServer))


if VSOCK:

    class TestVsockWSGIServer(unittest.TestCase):
        vsock_socket_cid = 2
        vsock_socket_port = -1

        def _makeOne(self, _start=True, _sock=None):
            from waitress.server import create_server

            self.inst = create_server(
                dummy_app,
                map={},
                _start=_start,
                _sock=_sock,
                _dispatcher=DummyTaskDispatcher(),
                vsock_socket_cid=self.vsock_socket_cid,
                vsock_socket_port=self.vsock_socket_port,
            )
            return self.inst

        def _makeWithSockets(
            self,
            application=dummy_app,
            _dispatcher=None,
            map=None,
            _start=True,
            _sock=None,
            _server=None,
            sockets=None,
        ):
            from waitress.server import create_server

            _sockets = []
            if sockets is not None:
                _sockets = sockets
            self.inst = create_server(
                application,
                map=map,
                _dispatcher=_dispatcher,
                _start=_start,
                _sock=_sock,
                sockets=_sockets,
            )
            return self.inst

        def tearDown(self):
            self.inst.close()

        def _makeDummy(self, *args, **kwargs):
            sock = DummySock(*args, **kwargs)
            sock.family = socket.AF_VSOCK
            return sock

        def test_unix(self):
            inst = self._makeOne(_start=False)
            self.assertEqual(inst.socket.family, socket.AF_VSOCK)
            self.assertEqual(inst.socket.getsockname(), self.vsock_socket_cid)

        def test_handle_accept(self):
            # Working on the assumption that we only have to test the happy path
            # for Unix domain sockets as the other paths should've been covered
            # by inet sockets.
            client = self._makeDummy()
            listen = self._makeDummy(acceptresult=(client, None))
            inst = self._makeOne(_sock=listen)
            self.assertEqual(inst.accepting, True)
            self.assertEqual(inst.socket.listened, 1024)
            L = []
            inst.channel_class = lambda *arg, **kw: L.append(arg)
            inst.handle_accept()
            self.assertEqual(inst.socket.accepted, True)
            self.assertEqual(client.opts, [])
            self.assertEqual(L, [(inst, client, ("localhost", None), inst.adj)])

        def test_creates_new_sockinfo(self):
            from waitress.server import VsockWSGIServer

            self.inst = VsockWSGIServer(
                dummy_app,
                vsock_socket_cid=self.vsock_socket_cid,
                vsock_socket_port=self.vsock_socket_port,
            )

            self.assertEqual(self.inst.sockinfo[0], socket.AF_UNIX)

        def test_create_with_unix_socket(self):
            from waitress.server import (
                BaseWSGIServer,
                MultiSocketServer,
                TcpWSGIServer,
                VsockWSGIServer,
            )

            sockets = [
                socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM),
                socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM),
            ]
            inst = self._makeWithSockets(sockets=sockets, _start=False)
            self.assertTrue(isinstance(inst, MultiSocketServer))
            server = list(
                filter(lambda s: isinstance(s, BaseWSGIServer), inst.map.values())
            )
            self.assertTrue(isinstance(server[0], VsockWSGIServer))
            self.assertTrue(isinstance(server[1], VsockWSGIServer))


class DummySock(socket.socket):
    accepted = False
    blocking = False
    family = socket.AF_INET
    type = socket.SOCK_STREAM
    proto = 0

    def __init__(self, toraise=None, acceptresult=(None, None)):
        self.toraise = toraise
        self.acceptresult = acceptresult
        self.bound = None
        self.opts = []
        self.bind_called = False

    def bind(self, addr):
        self.bind_called = True
        self.bound = addr

    def accept(self):
        if self.toraise:
            raise self.toraise
        self.accepted = True
        return self.acceptresult

    def setblocking(self, x):
        self.blocking = True

    def fileno(self):
        return 10

    def getpeername(self):
        return "127.0.0.1"

    def setsockopt(self, *arg):
        self.opts.append(arg)

    def getsockopt(self, *arg):
        return 1

    def listen(self, num):
        self.listened = num

    def getsockname(self):
        return self.bound

    def close(self):
        pass


class DummyTaskDispatcher:
    def __init__(self):
        self.tasks = []

    def add_task(self, task):
        self.tasks.append(task)

    def shutdown(self):
        self.was_shutdown = True


class DummyTask:
    serviced = False
    start_response_called = False
    wrote_header = False
    status = "200 OK"

    def __init__(self):
        self.response_headers = {}
        self.written = ""

    def service(self):  # pragma: no cover
        self.serviced = True


class DummyAdj:
    connection_limit = 1
    log_socket_errors = True
    socket_options = [("level", "optname", "value")]
    cleanup_interval = 900
    channel_timeout = 300


class DummyAsyncore:
    def loop(self, timeout=30.0, use_poll=False, map=None, count=None):
        raise SystemExit


class DummyTrigger:
    def pull_trigger(self):
        self.pulled = True

    def close(self):
        pass


class DummyLogger:
    def __init__(self):
        self.logged = []

    def warning(self, msg, **kw):
        self.logged.append(msg)
