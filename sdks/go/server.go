package memanto

import (
	"context"
	"errors"
	"fmt"
	"io/fs"
	"net"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const uvxInstallHint = "install uv from https://docs.astral.sh/uv/ and ensure uvx is on PATH"

// server resolves the base URL of the memanto REST server, spawning
// `uvx memanto serve` on first use when no BaseURL was configured.
type server struct {
	opts Options
	http *http.Client

	mu     sync.Mutex
	url    string
	cmd    *exec.Cmd
	exited chan struct{} // closed when cmd exits
}

func (s *server) start(ctx context.Context) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.url != "" {
		return s.url, nil
	}
	if s.opts.BaseURL != "" {
		s.url = strings.TrimRight(s.opts.BaseURL, "/")
		return s.url, nil
	}

	host := s.opts.Host
	if host == "" {
		host = "127.0.0.1"
	}
	port := s.opts.Port
	if port == 0 {
		p, err := pickFreePort(host)
		if err != nil {
			return "", fmt.Errorf("memanto: pick free port: %w", err)
		}
		port = p
	}
	uvx := s.opts.UvxPath
	if uvx == "" {
		uvx = "uvx"
	}
	spec := s.opts.PackageSpec
	if spec == "" {
		spec = "memanto"
	}

	// Not CommandContext: the server must outlive the ctx of the call that
	// happened to start it. Close stops it.
	cmd := exec.Command(uvx, spec, "serve", "--host", host, "--port", strconv.Itoa(port))
	cmd.Env = os.Environ()
	if s.opts.APIKey != "" {
		cmd.Env = append(cmd.Env, "MOORCHEH_API_KEY="+s.opts.APIKey)
	}
	if s.opts.Verbose {
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	}
	if err := cmd.Start(); err != nil {
		if errors.Is(err, exec.ErrNotFound) || errors.Is(err, fs.ErrNotExist) {
			return "", fmt.Errorf("memanto: could not find %q: %s", uvx, uvxInstallHint)
		}
		return "", fmt.Errorf("memanto: start server: %w", err)
	}
	exited := make(chan struct{})
	go func() {
		_ = cmd.Wait()
		close(exited)
	}()
	s.cmd = cmd
	s.exited = exited

	baseURL := "http://" + net.JoinHostPort(host, strconv.Itoa(port))
	if err := s.waitForHealth(ctx, baseURL); err != nil {
		s.stopLocked()
		return "", err
	}
	s.url = baseURL
	return baseURL, nil
}

func (s *server) waitForHealth(ctx context.Context, baseURL string) error {
	timeout := s.opts.HealthTimeout
	if timeout == 0 {
		timeout = 60 * time.Second
	}
	deadline := time.NewTimer(timeout)
	defer deadline.Stop()
	tick := time.NewTicker(250 * time.Millisecond)
	defer tick.Stop()

	var lastErr error
	for {
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL+"/health", nil)
		if err != nil {
			return err
		}
		res, err := s.http.Do(req)
		if err == nil {
			res.Body.Close()
			if res.StatusCode == http.StatusOK {
				return nil
			}
			lastErr = fmt.Errorf("/health returned %d", res.StatusCode)
		} else {
			lastErr = err
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-s.exited:
			return fmt.Errorf("memanto: server exited with code %d before becoming healthy", s.cmd.ProcessState.ExitCode())
		case <-deadline.C:
			return fmt.Errorf("memanto: server at %s did not become healthy within %s: %v", baseURL, timeout, lastErr)
		case <-tick.C:
		}
	}
}

func (s *server) stop() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stopLocked()
}

func (s *server) stopLocked() {
	cmd, exited := s.cmd, s.exited
	s.cmd, s.exited = nil, nil
	if s.opts.BaseURL == "" {
		s.url = ""
	}
	if cmd == nil {
		return
	}
	if runtime.GOOS == "windows" {
		// uvx runs the server as a child process, which survives killing
		// uvx alone on Windows, so end the whole tree.
		pid := strconv.Itoa(cmd.Process.Pid)
		if err := exec.Command("taskkill", "/T", "/F", "/PID", pid).Run(); err != nil {
			_ = cmd.Process.Kill()
		}
	} else {
		// SIGTERM lets the server shut down cleanly; uvx forwards it.
		_ = cmd.Process.Signal(syscall.SIGTERM)
	}
	select {
	case <-exited:
	case <-time.After(5 * time.Second):
		_ = cmd.Process.Kill()
		<-exited
	}
}

func pickFreePort(host string) (int, error) {
	l, err := net.Listen("tcp", net.JoinHostPort(host, "0"))
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}
