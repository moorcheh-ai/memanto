import signal
import atexit

class ServerLifecycle:
    def __init__(self):
        self.exit_handler = None
        self.sigint_handler = None
        self.sigterm_handler = None
        self.health_polling_loop = None

    def start(self):
        self.exit_handler = self.exit_handler_func
        self.sigint_handler = self.sigint_handler_func
        self.sigterm_handler = self.sigterm_handler_func

        atexit.register(self.exit_handler)
        signal.signal(signal.SIGINT, self.sigint_handler)
        signal.signal(signal.SIGTERM, self.sigterm_handler)

    def stop(self):
        if self.exit_handler:
            atexit.unregister(self.exit_handler)
        if self.sigint_handler:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        if self.sigterm_handler:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

        if self.health_polling_loop:
            self.health_polling_loop.stop()

    def exit_handler_func(self):
        # Handle exit event
        pass

    def sigint_handler_func(self, signum, frame):
        # Handle SIGINT event
        pass

    def sigterm_handler_func(self, signum, frame):
        # Handle SIGTERM event
        pass

    def spawn_child_process(self):
        # Spawn child process and start health polling loop
        self.health_polling_loop = HealthPollingLoop()
        self.health_polling_loop.start()

        # Register child process exit handler
        def child_exit_handler():
            self.stop()
        # Replace with actual child process exit registration

    def startup_failed(self):
        self.stop()

class HealthPollingLoop:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True
        # Start polling loop

    def stop(self):
        self.running = False
        # Stop polling loop

def test_lifecycle():
    lifecycle = ServerLifecycle()
    lifecycle.start()
    lifecycle.stop()

    # Verify listener counts return to baseline
    assert len(atexit._exithandlers) == 0
    assert signal.getsignal(signal.SIGINT) == signal.SIG_DFL
    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL

test_lifecycle()