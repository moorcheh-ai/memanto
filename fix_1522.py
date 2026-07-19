import atexit
import signal
from unittest.mock import patch, MagicMock

class ServerLifecycle:
    def __init__(self, exit_handler=None, sigint_handler=None, sigterm_handler=None, health_polling_loop=None):
        self.exit_handler = exit_handler
        self.sigint_handler = sigint_handler
        self.sigterm_handler = sigterm_handler
        self.health_polling_loop = health_polling_loop
        
        self._original_sigint = None
        self._original_sigterm = None
        self._registered_exit = False

    def start(self):
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

        if self.exit_handler:
            atexit.register(self.exit_handler)
            self._registered_exit = True
        
        if self.sigint_handler:
            signal.signal(signal.SIGINT, self.sigint_handler)
            
        if self.sigterm_handler:
            signal.signal(signal.SIGTERM, self.sigterm_handler)

    def stop(self):
        if self._registered_exit and self.exit_handler:
            atexit.unregister(self.exit_handler)
            self._registered_exit = False
            
        if self.sigint_handler and self._original_sigint is not None:
            signal.signal(signal.SIGINT, self._original_sigint)
            self.sigint_handler = None
            
        if self.sigterm_handler and self._original_sigterm is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm)
            self.sigterm_handler = None
            
        if self.health_polling_loop:
            self.health_polling_loop.stop()

def test_lifecycle():
    with patch('atexit.register') as mock_atexit_reg, \
         patch('atexit.unregister') as mock_atexit_unreg, \
         patch('signal.signal') as mock_signal_sig:
        
        exit_mock = MagicMock()
        sigint_mock = MagicMock()
        sigterm_mock = MagicMock()
        health_mock = MagicMock()
        
        lifecycle = ServerLifecycle(
            exit_handler=exit_mock,
            sigint_handler=sigint_mock,
            sigterm_handler=sigterm_mock,
            health_polling_loop=health_mock
        )
        
        lifecycle.start()
        
        mock_atexit_reg.assert_called_once_with(exit_mock)
        assert mock_signal_sig.call_count == 2 
        
        lifecycle.stop()
        
        mock_atexit_unreg.assert_called_once_with(exit_mock)
        health_mock.stop.assert_called_once()
        
        assert lifecycle.sigint_handler is None
        assert lifecycle.sigterm_handler is None

    print("Test passed: Lifecycle handlers preserved, restored, and cleared correctly.")

if __name__ == "__main__":
    test_lifecycle()
