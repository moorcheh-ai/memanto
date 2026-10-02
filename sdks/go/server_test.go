package memanto

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

// When FAKE_UVX is set, the test binary acts as `uvx`: it checks the args it
// was given and, like real uvx, runs the server as a child process that
// serves /health on the requested host and port.
func TestMain(m *testing.M) {
	switch os.Getenv("FAKE_UVX") {
	case "":
		os.Exit(m.Run())
	case "serve":
		child := exec.Command(os.Args[0], os.Args[1:]...)
		child.Env = append(os.Environ(), "FAKE_UVX=child")
		child.Stderr = os.Stderr
		if err := child.Start(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(7)
		}
		// Forward SIGTERM to the server, as uv does on Unix.
		sigs := make(chan os.Signal, 1)
		signal.Notify(sigs, syscall.SIGTERM)
		go func() { _ = child.Process.Signal(<-sigs) }()
		_ = child.Wait()
		os.Exit(7)
	}
	args := os.Args[1:]
	if len(args) != 6 || args[0] != "memanto==9.9.9" || args[1] != "serve" || args[2] != "--host" || args[4] != "--port" {
		fmt.Fprintf(os.Stderr, "unexpected args %q\n", args)
		os.Exit(3)
	}
	switch os.Getenv("FAKE_UVX") {
	case "crash":
		os.Exit(4)
	case "hang":
		time.Sleep(time.Hour)
	}
	if os.Getenv("MOORCHEH_API_KEY") != "key" {
		fmt.Fprintln(os.Stderr, "MOORCHEH_API_KEY not passed")
		os.Exit(5)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) { fmt.Fprint(w, `{"status":"ok"}`) })
	fmt.Fprintln(os.Stderr, http.ListenAndServe(net.JoinHostPort(args[3], args[5]), mux))
	os.Exit(6)
}

func fakeUvxOptions(t *testing.T, mode string) Options {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_UVX", mode)
	return Options{
		AgentID:       "a",
		APIKey:        "key",
		UvxPath:       exe,
		PackageSpec:   "memanto==9.9.9",
		HealthTimeout: 10 * time.Second,
	}
}

func TestSpawnsServerAndStopsItOnClose(t *testing.T) {
	c, err := New(fakeUvxOptions(t, "serve"))
	if err != nil {
		t.Fatal(err)
	}
	url, err := c.server.start(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(url, "http://127.0.0.1:") {
		t.Fatalf("unexpected url %s", url)
	}
	// A second start reuses the running server.
	again, err := c.server.start(context.Background())
	if err != nil || again != url {
		t.Fatalf("restart: %s %v", again, err)
	}
	exited := c.server.exited
	c.Close()
	select {
	case <-exited:
	case <-time.After(10 * time.Second):
		t.Fatal("server still running after Close")
	}
	if _, err := http.Get(url + "/health"); err == nil {
		t.Fatal("server still answering after Close")
	}
}

func TestSpawnReportsEarlyExit(t *testing.T) {
	c, _ := New(fakeUvxOptions(t, "crash"))
	_, err := c.server.start(context.Background())
	if err == nil || !strings.Contains(err.Error(), "exited with code 4") {
		t.Fatalf("want early-exit error, got %v", err)
	}
}

func TestSpawnReportsMissingUvx(t *testing.T) {
	c, _ := New(Options{AgentID: "a", UvxPath: filepath.Join(t.TempDir(), "no-such-uvx")})
	_, err := c.Recall(context.Background(), RecallInput{Query: "q"})
	if err == nil || !strings.Contains(err.Error(), "install uv") {
		t.Fatalf("want install hint, got %v", err)
	}
}

func TestBaseURLSkipsSpawn(t *testing.T) {
	c, _ := New(Options{AgentID: "a", BaseURL: "http://example.invalid/", UvxPath: "must-not-run"})
	url, err := c.server.start(context.Background())
	if err != nil || url != "http://example.invalid" {
		t.Fatalf("got %s %v", url, err)
	}
	c.Close()
	if url, _ := c.server.start(context.Background()); url != "http://example.invalid" {
		t.Fatalf("BaseURL lost after Close: %s", url)
	}
}

func TestSpawnHonorsContext(t *testing.T) {
	c, _ := New(fakeUvxOptions(t, "hang"))
	ctx, cancel := context.WithTimeout(context.Background(), 500*time.Millisecond)
	defer cancel()
	if _, err := c.server.start(ctx); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("want deadline error, got %v", err)
	}
	if c.server.cmd != nil {
		t.Fatal("hung server was not stopped")
	}
}
