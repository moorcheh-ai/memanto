package memanto

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

type recorded struct {
	Method, Path, Query, Token, APIKey, ContentType string
	Body                                            []byte
}

// fakeAPI imitates the memanto REST endpoints the client uses.
type fakeAPI struct {
	t       *testing.T
	agentID string
	// agentExists makes GET /api/v2/agents/{id} return 200 instead of 404.
	agentExists bool
	// rejectToken answers 401 to session calls carrying this token.
	rejectToken string
	// rejectAll answers 401 to every session call.
	rejectAll bool

	mu          sync.Mutex
	calls       []recorded
	activations int
}

func (f *fakeAPI) start() string {
	srv := httptest.NewServer(http.HandlerFunc(f.handle))
	f.t.Cleanup(srv.Close)
	return srv.URL
}

func (f *fakeAPI) handle(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	f.mu.Lock()
	f.calls = append(f.calls, recorded{
		Method: r.Method, Path: r.URL.Path, Query: r.URL.RawQuery,
		Token: r.Header.Get("X-Session-Token"), APIKey: r.Header.Get("X-Api-Key"),
		ContentType: r.Header.Get("Content-Type"), Body: body,
	})
	f.mu.Unlock()

	reply := func(status int, v any) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(v)
	}
	agent := "/api/v2/agents/" + f.agentID
	now := time.Now().UTC().Format(time.RFC3339)

	switch {
	case r.URL.Path == "/health":
		reply(200, map[string]any{"status": "ok"})
	case r.URL.Path == agent && r.Method == http.MethodGet:
		f.mu.Lock()
		exists := f.agentExists
		f.mu.Unlock()
		if !exists {
			reply(404, map[string]any{"detail": "Agent not found"})
			return
		}
		reply(200, map[string]any{"agent_id": f.agentID, "namespace": "ns", "pattern": "support", "created_at": now})
	case r.URL.Path == "/api/v2/agents" && r.Method == http.MethodPost:
		f.mu.Lock()
		f.agentExists = true
		f.mu.Unlock()
		reply(201, map[string]any{"agent_id": f.agentID, "namespace": "ns", "pattern": "support", "created_at": now})
	case r.URL.Path == agent && r.Method == http.MethodDelete:
		reply(200, map[string]any{"agent_id": f.agentID, "deleted": true})
	case r.URL.Path == agent+"/activate":
		f.mu.Lock()
		f.activations++
		token := "token-" + string(rune('0'+f.activations))
		f.mu.Unlock()
		reply(200, map[string]any{
			"session_token": token, "agent_id": f.agentID, "session_id": "sess",
			"namespace": "ns", "started_at": now, "expires_at": now,
		})
	case strings.HasPrefix(r.URL.Path, agent+"/"):
		if f.rejectAll || (f.rejectToken != "" && r.Header.Get("X-Session-Token") == f.rejectToken) {
			reply(401, map[string]any{"detail": "Session token expired"})
			return
		}
		switch strings.TrimPrefix(r.URL.Path, agent) {
		case "/remember":
			reply(200, map[string]any{"memory_id": "mem-1", "agent_id": f.agentID, "session_id": "sess",
				"namespace": "ns", "status": "queued", "provenance": "explicit_statement", "confidence": 0.8})
		case "/recall":
			reply(200, map[string]any{"agent_id": f.agentID, "session_id": "sess", "query": "q", "count": 1,
				"memories": []map[string]any{{"id": "mem-1", "content": "likes tea", "score": 0.9}}})
		case "/upload-file":
			reply(200, map[string]any{"agent_id": f.agentID, "session_id": "sess", "namespace": "ns",
				"file_name": "notes.md", "status": "uploaded"})
		case "/deactivate":
			reply(200, map[string]any{"agent_id": f.agentID, "session_id": "sess", "started_at": now,
				"ended_at": now, "duration_hours": 0.1, "memories_created": 1})
		default:
			reply(200, map[string]any{"ok": true})
		}
	default:
		reply(404, map[string]any{"detail": "no route"})
	}
}

func (f *fakeAPI) paths() []string {
	f.mu.Lock()
	defer f.mu.Unlock()
	var out []string
	for _, c := range f.calls {
		out = append(out, c.Method+" "+c.Path)
	}
	return out
}

func (f *fakeAPI) activationCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.activations
}

func (f *fakeAPI) last(path string) recorded {
	f.mu.Lock()
	defer f.mu.Unlock()
	for i := len(f.calls) - 1; i >= 0; i-- {
		if f.calls[i].Path == path {
			return f.calls[i]
		}
	}
	f.t.Fatalf("no call to %s", path)
	return recorded{}
}

func newTestClient(t *testing.T, f *fakeAPI, opts Options) *Client {
	t.Helper()
	opts.AgentID = f.agentID
	opts.BaseURL = f.start() + "/"
	c, err := New(opts)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Close() })
	return c
}

func equal(t *testing.T, got, want any) {
	t.Helper()
	if raw, ok := got.(json.RawMessage); ok {
		// Decode so map keys compare in json.Marshal's sorted order.
		if err := json.Unmarshal(raw, &got); err != nil {
			t.Fatal(err)
		}
	}
	g, _ := json.Marshal(got)
	w, _ := json.Marshal(want)
	if string(g) != string(w) {
		t.Fatalf("got %s, want %s", g, w)
	}
}

func TestNewRequiresAgentID(t *testing.T) {
	if _, err := New(Options{}); err == nil {
		t.Fatal("want error for empty AgentID")
	}
}

func TestRememberCreatesAgentActivatesAndSendsDefaults(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a b"}
	c := newTestClient(t, f, Options{APIKey: "key"})

	res, err := c.Remember(context.Background(), RememberInput{Content: "likes tea", Tags: []string{"x"}})
	if err != nil {
		t.Fatal(err)
	}
	equal(t, res.MemoryId, "mem-1")
	equal(t, f.paths(), []string{
		"GET /api/v2/agents/a b",
		"POST /api/v2/agents",
		"POST /api/v2/agents/a b/activate",
		"POST /api/v2/agents/a b/remember",
	})
	rem := f.last("/api/v2/agents/a b/remember")
	equal(t, rem.Token, "token-1")
	equal(t, rem.APIKey, "key")
	equal(t, json.RawMessage(rem.Body), map[string]any{
		"content": "likes tea", "confidence": 0.8, "tags": []string{"x"},
		"source": "agent", "provenance": "explicit_statement",
	})
	equal(t, json.RawMessage(f.last("/api/v2/agents").Body), map[string]any{"agent_id": "a b"})

	// The session is reused.
	if _, err := c.Recall(context.Background(), RecallInput{Query: "tea", MinSimilarity: Ptr(0.0)}); err != nil {
		t.Fatal(err)
	}
	equal(t, f.activationCount(), 1)
	equal(t, json.RawMessage(f.last("/api/v2/agents/a b/recall").Body), map[string]any{"query": "tea", "min_similarity": 0})
}

func TestDisableAutoCreateSkipsLookup(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a"}
	c := newTestClient(t, f, Options{DisableAutoCreate: true})
	if _, err := c.Recall(context.Background(), RecallInput{Query: "q"}); err != nil {
		t.Fatal(err)
	}
	equal(t, f.paths(), []string{"POST /api/v2/agents/a/activate", "POST /api/v2/agents/a/recall"})
}

func TestExpiredSessionIsRenewedOnce(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a", agentExists: true, rejectToken: "token-1"}
	c := newTestClient(t, f, Options{})
	if _, err := c.Remember(context.Background(), RememberInput{Content: "x"}); err != nil {
		t.Fatal(err)
	}
	equal(t, f.activationCount(), 2)
	equal(t, f.last("/api/v2/agents/a/remember").Token, "token-2")
}

func TestRejectedSessionReturnsAPIErrorAfterOneRetry(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a", agentExists: true, rejectAll: true}
	c := newTestClient(t, f, Options{})
	_, err := c.Remember(context.Background(), RememberInput{Content: "x"})
	var apiErr *APIError
	if !errors.As(err, &apiErr) {
		t.Fatalf("want *APIError, got %v", err)
	}
	equal(t, apiErr.StatusCode, 401)
	equal(t, apiErr.Detail, "Session token expired")
	equal(t, f.activationCount(), 2)
}

func TestConcurrentExpiredCallsRenewOnce(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a", agentExists: true, rejectToken: "token-1"}
	c := newTestClient(t, f, Options{})
	// Activate token-1 first so every goroutine starts with the stale token.
	if _, err := c.session(context.Background()); err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	errs := make(chan error, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := c.Remember(context.Background(), RememberInput{Content: "x"})
			errs <- err
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatal(err)
		}
	}
	equal(t, f.activationCount(), 2)
}

func TestDeleteAgentPurgesAndForgetsSession(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a", agentExists: true}
	c := newTestClient(t, f, Options{})
	ctx := context.Background()
	if _, err := c.Remember(ctx, RememberInput{Content: "x"}); err != nil {
		t.Fatal(err)
	}
	if _, err := c.DeleteAgent(ctx, DeleteAgentInput{DeleteMemories: true}); err != nil {
		t.Fatal(err)
	}
	equal(t, f.last("/api/v2/agents/a").Query, "delete-backup-too=true")
	if _, err := c.Remember(ctx, RememberInput{Content: "y"}); err != nil {
		t.Fatal(err)
	}
	equal(t, f.activationCount(), 2)
}

func TestUploadFileSendsMultipart(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a", agentExists: true}
	c := newTestClient(t, f, Options{})
	path := filepath.Join(t.TempDir(), "notes.md")
	if err := os.WriteFile(path, []byte("# hello"), 0o600); err != nil {
		t.Fatal(err)
	}
	res, err := c.UploadFile(context.Background(), UploadFileInput{Path: path})
	if err != nil {
		t.Fatal(err)
	}
	equal(t, res.FileName, "notes.md")
	up := f.last("/api/v2/agents/a/upload-file")
	if !strings.HasPrefix(up.ContentType, "multipart/form-data") ||
		!strings.Contains(string(up.Body), `name="file"; filename="notes.md"`) ||
		!strings.Contains(string(up.Body), "# hello") {
		t.Fatalf("unexpected upload: %s %s", up.ContentType, up.Body)
	}
}

func TestErrorDetail(t *testing.T) {
	equal(t, errorDetail([]byte(`{"detail":"nope"}`)), "nope")
	equal(t, errorDetail([]byte(`{"detail":[{"msg":"bad"}]}`)), `[{"msg":"bad"}]`)
	equal(t, errorDetail([]byte(`{"detail":{"details":{},"error":"AgentNotFound","message":"Agent 'a' not found"}}`)), "Agent 'a' not found")
	equal(t, errorDetail([]byte("plain")), "plain")
}

func TestMapResultsAreReturned(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a", agentExists: true}
	c := newTestClient(t, f, Options{})
	ctx := context.Background()
	calls := map[string]func() (map[string]any, error){
		"ExtractMemories": func() (map[string]any, error) {
			return c.ExtractMemories(ctx, ExtractMemoriesInput{Messages: []ConversationMessage{{Role: "user", Content: "hi"}}})
		},
		"DeleteMemory":      func() (map[string]any, error) { return c.DeleteMemory(ctx, "mem-1") },
		"DailySummary":      func() (map[string]any, error) { return c.DailySummary(ctx, DailySummaryInput{}) },
		"GenerateConflicts": func() (map[string]any, error) { return c.GenerateConflicts(ctx, ConflictDateInput{}) },
		"ListConflicts":     func() (map[string]any, error) { return c.ListConflicts(ctx, ConflictDateInput{Date: "2026-10-01"}) },
		"ResolveConflict": func() (map[string]any, error) {
			return c.ResolveConflict(ctx, ResolveConflictInput{ConflictIndex: 0, Action: "keep_new"})
		},
	}
	for name, call := range calls {
		got, err := call()
		if err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		if got["ok"] != true {
			t.Errorf("%s returned %v, want the response body", name, got)
		}
	}
	equal(t, f.last("/api/v2/agents/a/conflicts").Query, "date=2026-10-01")
}

func TestErrorsReturnNilResult(t *testing.T) {
	f := &fakeAPI{t: t, agentID: "a", agentExists: true, rejectAll: true}
	c := newTestClient(t, f, Options{})
	res, err := c.Recall(context.Background(), RecallInput{Query: "q"})
	if err == nil || res != nil {
		t.Fatalf("want nil result and an error, got %v, %v", res, err)
	}
}
