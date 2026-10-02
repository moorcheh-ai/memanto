// Package memanto is the Go client for Memanto, memory for AI agents.
//
// A Client is bound to one agent. It talks to a memanto REST server: the one
// at Options.BaseURL, or, when BaseURL is empty, one it starts itself with
// `uvx memanto serve` on first use and stops on Close. The client creates the
// agent if it is missing, activates a session, and renews the session once
// when the server rejects it.
//
// Response types live in the generated package
// github.com/moorcheh-ai/memanto/sdks/go/api.
package memanto

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/moorcheh-ai/memanto/sdks/go/api"
)

// Options configures a Client. Only AgentID is required.
type Options struct {
	// AgentID is the agent this client reads and writes memories for.
	AgentID string
	// DisableAutoCreate stops the client from creating the agent when it
	// does not exist yet.
	DisableAutoCreate bool

	// BaseURL of a running memanto server, e.g. "http://127.0.0.1:8000".
	// When empty, the client starts `uvx memanto serve` on first use.
	BaseURL string
	// APIKey is the Moorcheh API key. A spawned server receives it as
	// MOORCHEH_API_KEY, and every request sends it as X-Api-Key, which a
	// server bound beyond loopback requires for agent management.
	APIKey string
	// HTTPClient used for every request. Defaults to http.DefaultClient.
	HTTPClient *http.Client

	// The fields below only apply when BaseURL is empty.

	// Host the spawned server binds to. Defaults to 127.0.0.1.
	Host string
	// Port the spawned server listens on. Defaults to a free port.
	Port int
	// UvxPath is the uvx binary. Defaults to "uvx" on PATH.
	UvxPath string
	// PackageSpec passed to uvx. Defaults to "memanto"; use e.g.
	// "memanto==0.2.3" to pin a version.
	PackageSpec string
	// HealthTimeout bounds how long to wait for the spawned server's /health.
	// Defaults to 60s.
	HealthTimeout time.Duration
	// Verbose streams the spawned server's output to this process's
	// stdout and stderr.
	Verbose bool
}

// Client is a Memanto client bound to one agent. It is safe for concurrent
// use. Call Close when done to stop a server the client spawned.
type Client struct {
	agentID    string
	agentPath  string
	autoCreate bool
	apiKey     string
	http       *http.Client
	server     *server

	mu    sync.Mutex // guards token and serializes session activation
	token string
}

// New returns a client for opts.AgentID. It does not contact the server; the
// server is started (if needed) and the session activated on the first call.
func New(opts Options) (*Client, error) {
	if opts.AgentID == "" {
		return nil, errors.New("memanto: AgentID is required")
	}
	hc := opts.HTTPClient
	if hc == nil {
		hc = http.DefaultClient
	}
	return &Client{
		agentID:    opts.AgentID,
		agentPath:  "/api/v2/agents/" + url.PathEscape(opts.AgentID),
		autoCreate: !opts.DisableAutoCreate,
		apiKey:     opts.APIKey,
		http:       hc,
		server:     &server{opts: opts, http: hc},
	}, nil
}

// Close forgets the session and stops the server if this client spawned it.
func (c *Client) Close() error {
	c.mu.Lock()
	c.token = ""
	c.mu.Unlock()
	c.server.stop()
	return nil
}

// Ptr returns a pointer to v, for optional fields such as
// AnswerInput.Temperature where the zero value is meaningful.
func Ptr[T any](v T) *T { return &v }

// APIError is returned when the server answers with a non-2xx status.
type APIError struct {
	// Op is the request that failed, e.g. "POST /api/v2/agents/a/recall".
	Op         string
	StatusCode int
	// Detail is the server's error message, or the raw body.
	Detail string
}

func (e *APIError) Error() string {
	return fmt.Sprintf("memanto: %s failed (%d): %s", e.Op, e.StatusCode, e.Detail)
}

// ---------------------------------------------------------------------------
// Memory writes
// ---------------------------------------------------------------------------

// RememberInput is one memory to store.
type RememberInput struct {
	Content string `json:"content"`
	// Type is a memory type such as "fact", "preference" or "decision".
	Type  string `json:"type,omitempty"`
	Title string `json:"title,omitempty"`
	// Confidence in [0, 1]. Zero means the default, 0.8.
	Confidence float64  `json:"confidence,omitempty"`
	Tags       []string `json:"tags,omitempty"`
	// Source is who wrote the memory. Defaults to "agent".
	Source string `json:"source,omitempty"`
	// Provenance is how it was obtained. Defaults to "explicit_statement".
	Provenance string `json:"provenance,omitempty"`
}

func (in RememberInput) withDefaults() RememberInput {
	if in.Confidence == 0 {
		in.Confidence = 0.8
	}
	if in.Source == "" {
		in.Source = "agent"
	}
	if in.Provenance == "" {
		in.Provenance = "explicit_statement"
	}
	return in
}

// Remember stores one memory.
func (c *Client) Remember(ctx context.Context, in RememberInput) (*api.RememberResponse, error) {
	var out api.RememberResponse
	return &out, c.do(ctx, http.MethodPost, c.agentPath+"/remember", in.withDefaults(), true, &out)
}

// BatchRemember stores several memories in one request.
func (c *Client) BatchRemember(ctx context.Context, items []RememberInput) (*api.BatchRememberResponse, error) {
	memories := make([]RememberInput, len(items))
	for i, m := range items {
		memories[i] = m.withDefaults()
	}
	body := map[string]any{"memories": memories}
	var out api.BatchRememberResponse
	return &out, c.do(ctx, http.MethodPost, c.agentPath+"/batch-remember", body, true, &out)
}

// ConversationMessage is one turn passed to ExtractMemories.
type ConversationMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// ExtractMemoriesInput is a conversation to extract memories from.
type ExtractMemoriesInput struct {
	Messages []ConversationMessage `json:"messages"`
	// DryRun returns the candidates without writing them.
	DryRun bool `json:"dry_run,omitempty"`
	// MaxMemories in [1, 100]. Zero means the server default, 20.
	MaxMemories int    `json:"max_memories,omitempty"`
	AIModel     string `json:"ai_model,omitempty"`
}

// ExtractMemories asks the server's LLM to pull memories out of a conversation.
func (c *Client) ExtractMemories(ctx context.Context, in ExtractMemoriesInput) (map[string]any, error) {
	var out map[string]any
	return out, c.do(ctx, http.MethodPost, c.agentPath+"/remember/extract", in, true, &out)
}

// DeleteMemory deletes one memory by id.
func (c *Client) DeleteMemory(ctx context.Context, memoryID string) (map[string]any, error) {
	var out map[string]any
	return out, c.do(ctx, http.MethodDelete, c.agentPath+"/memories/"+url.PathEscape(memoryID), nil, true, &out)
}

// UploadFileInput is a local file to upload as memories.
type UploadFileInput struct {
	// Path to a .pdf, .docx, .xlsx, .json, .txt, .csv or .md file.
	Path string
	// Filename sent to the server. Defaults to the base name of Path.
	Filename string
}

// UploadFile uploads a document; the server turns it into memories.
func (c *Client) UploadFile(ctx context.Context, in UploadFileInput) (*api.UploadFileResponse, error) {
	data, err := os.ReadFile(in.Path)
	if err != nil {
		return nil, fmt.Errorf("memanto: read upload: %w", err)
	}
	name := in.Filename
	if name == "" {
		name = filepath.Base(in.Path)
	}
	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	fw, err := mw.CreateFormFile("file", name)
	if err != nil {
		return nil, err
	}
	if _, err := fw.Write(data); err != nil {
		return nil, err
	}
	if err := mw.Close(); err != nil {
		return nil, err
	}
	var out api.UploadFileResponse
	return &out, c.send(ctx, http.MethodPost, c.agentPath+"/upload-file", buf.Bytes(), mw.FormDataContentType(), true, &out)
}

// ---------------------------------------------------------------------------
// Memory reads
// ---------------------------------------------------------------------------

// RecallInput is a semantic search over the agent's memories.
type RecallInput struct {
	Query string `json:"query"`
	// Limit on results. Zero means the server default.
	Limit int `json:"limit,omitempty"`
	// MinSimilarity in [0, 1]. Nil means the server default.
	MinSimilarity *float64 `json:"min_similarity,omitempty"`
	// Type keeps only memories of these types.
	Type []string `json:"type,omitempty"`
	// Tags keeps only memories carrying all of these tags.
	Tags []string `json:"tags,omitempty"`
}

// Recall returns the memories most relevant to a query.
func (c *Client) Recall(ctx context.Context, in RecallInput) (*api.RecallResponse, error) {
	var out api.RecallResponse
	return &out, c.do(ctx, http.MethodPost, c.agentPath+"/recall", in, true, &out)
}

// RecallAsOfInput selects memories as they were at a point in time.
type RecallAsOfInput struct {
	// AsOf is YYYY-MM-DD or an ISO 8601 datetime.
	AsOf  string   `json:"as_of"`
	Limit int      `json:"limit,omitempty"`
	Type  []string `json:"type,omitempty"`
}

// RecallAsOf returns memories as they existed at AsOf.
func (c *Client) RecallAsOf(ctx context.Context, in RecallAsOfInput) (*api.TemporalRecallResponse, error) {
	var out api.TemporalRecallResponse
	return &out, c.do(ctx, http.MethodPost, c.agentPath+"/recall/as-of", in, true, &out)
}

// RecallChangedSinceInput selects memories changed after a point in time.
type RecallChangedSinceInput struct {
	// Since is YYYY-MM-DD or an ISO 8601 datetime.
	Since string   `json:"since"`
	Limit int      `json:"limit,omitempty"`
	Type  []string `json:"type,omitempty"`
}

// RecallChangedSince returns memories created or changed since Since.
func (c *Client) RecallChangedSince(ctx context.Context, in RecallChangedSinceInput) (*api.TemporalRecallResponse, error) {
	var out api.TemporalRecallResponse
	return &out, c.do(ctx, http.MethodPost, c.agentPath+"/recall/changed-since", in, true, &out)
}

// RecallRecentInput selects the newest memories.
type RecallRecentInput struct {
	Limit int      `json:"limit,omitempty"`
	Type  []string `json:"type,omitempty"`
}

// RecallRecent returns the most recently created memories.
func (c *Client) RecallRecent(ctx context.Context, in RecallRecentInput) (*api.TemporalRecallResponse, error) {
	var out api.TemporalRecallResponse
	return &out, c.do(ctx, http.MethodPost, c.agentPath+"/recall/recent", in, true, &out)
}

// AnswerInput is a question answered from the agent's memories.
type AnswerInput struct {
	Question string `json:"question"`
	// Limit on context memories. Zero means the server default.
	Limit int `json:"limit,omitempty"`
	// Threshold and Temperature: nil means the server default.
	Threshold   *float64 `json:"threshold,omitempty"`
	Temperature *float64 `json:"temperature,omitempty"`
	AIModel     string   `json:"ai_model,omitempty"`
	KioskMode   bool     `json:"kiosk_mode"`
}

// Answer generates an answer grounded in the agent's memories.
func (c *Client) Answer(ctx context.Context, in AnswerInput) (*api.AnswerResponse, error) {
	var out api.AnswerResponse
	return &out, c.do(ctx, http.MethodPost, c.agentPath+"/answer", in, true, &out)
}

// ---------------------------------------------------------------------------
// Analysis (summaries + conflicts)
// ---------------------------------------------------------------------------

// DailySummaryInput selects the day to summarize.
type DailySummaryInput struct {
	// Date is YYYY-MM-DD. Empty means today.
	Date       string `json:"date,omitempty"`
	OutputPath string `json:"output_path,omitempty"`
}

// DailySummary summarizes one day of memories.
func (c *Client) DailySummary(ctx context.Context, in DailySummaryInput) (map[string]any, error) {
	var out map[string]any
	return out, c.do(ctx, http.MethodPost, c.agentPath+"/daily-summary", in, true, &out)
}

// ConflictDateInput selects the day of a conflict report.
type ConflictDateInput struct {
	// Date is YYYY-MM-DD. Empty means today.
	Date string `json:"date,omitempty"`
}

// GenerateConflicts detects conflicting memories for a day.
func (c *Client) GenerateConflicts(ctx context.Context, in ConflictDateInput) (map[string]any, error) {
	var out map[string]any
	return out, c.do(ctx, http.MethodPost, c.agentPath+"/conflicts/generate", in, true, &out)
}

// ListConflicts returns the conflict report for a day.
func (c *Client) ListConflicts(ctx context.Context, in ConflictDateInput) (map[string]any, error) {
	path := c.agentPath + "/conflicts"
	if in.Date != "" {
		path += "?date=" + url.QueryEscape(in.Date)
	}
	var out map[string]any
	return out, c.do(ctx, http.MethodGet, path, nil, true, &out)
}

// ResolveConflictInput resolves one entry of a conflict report.
type ResolveConflictInput struct {
	ConflictIndex int `json:"conflict_index"`
	// Action is keep_old, keep_new, keep_both, remove_both or manual.
	Action        string `json:"action"`
	Date          string `json:"date,omitempty"`
	ManualContent string `json:"manual_content,omitempty"`
	ManualType    string `json:"manual_type,omitempty"`
}

// ResolveConflict applies a resolution to one conflict.
func (c *Client) ResolveConflict(ctx context.Context, in ResolveConflictInput) (map[string]any, error) {
	var out map[string]any
	return out, c.do(ctx, http.MethodPost, c.agentPath+"/conflicts/resolve", in, true, &out)
}

// ---------------------------------------------------------------------------
// Agent + session lifecycle
// ---------------------------------------------------------------------------

// ListAgents returns every agent on the server.
func (c *Client) ListAgents(ctx context.Context) (*api.AgentList, error) {
	var out api.AgentList
	return &out, c.do(ctx, http.MethodGet, "/api/v2/agents", nil, false, &out)
}

// GetAgent returns the bound agent.
func (c *Client) GetAgent(ctx context.Context) (*api.AgentInfo, error) {
	var out api.AgentInfo
	return &out, c.do(ctx, http.MethodGet, c.agentPath, nil, false, &out)
}

// CreateAgentInput configures CreateAgent.
type CreateAgentInput struct {
	// Pattern is support, project or tool. Empty means the server default.
	Pattern     string
	Description string
}

// CreateAgent creates the bound agent. Most callers do not need it: the
// client creates a missing agent on first use unless DisableAutoCreate is set.
func (c *Client) CreateAgent(ctx context.Context, in CreateAgentInput) (*api.AgentInfo, error) {
	body := struct {
		AgentID     string `json:"agent_id"`
		Pattern     string `json:"pattern,omitempty"`
		Description string `json:"description,omitempty"`
	}{c.agentID, in.Pattern, in.Description}
	var out api.AgentInfo
	return &out, c.do(ctx, http.MethodPost, "/api/v2/agents", body, false, &out)
}

// DeleteAgentInput configures DeleteAgent.
type DeleteAgentInput struct {
	// DeleteMemories also permanently deletes the agent's memories in
	// Moorcheh. If that fails, the agent is kept and an error is returned.
	DeleteMemories bool
}

// DeleteAgent deletes the bound agent and forgets its session. Its memories
// stay in Moorcheh unless DeleteMemories is set.
func (c *Client) DeleteAgent(ctx context.Context, in DeleteAgentInput) (map[string]any, error) {
	path := c.agentPath
	if in.DeleteMemories {
		path += "?delete-backup-too=true"
	}
	var out map[string]any
	if err := c.do(ctx, http.MethodDelete, path, nil, false, &out); err != nil {
		return nil, err
	}
	c.forgetSession()
	return out, nil
}

// Deactivate ends the agent's session. The next call activates a new one.
func (c *Client) Deactivate(ctx context.Context) (*api.SessionSummary, error) {
	var out api.SessionSummary
	if err := c.do(ctx, http.MethodPost, c.agentPath+"/deactivate", nil, true, &out); err != nil {
		return nil, err
	}
	c.forgetSession()
	return &out, nil
}

// Status returns the server's currently active session, whichever agent
// it belongs to.
func (c *Client) Status(ctx context.Context) (*api.SessionInfo, error) {
	var out api.SessionInfo
	return &out, c.do(ctx, http.MethodGet, "/api/v2/status", nil, false, &out)
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

func (c *Client) forgetSession() {
	c.mu.Lock()
	c.token = ""
	c.mu.Unlock()
}

// session returns the current session token, creating the agent (when
// allowed) and activating a session if there is none.
func (c *Client) session(ctx context.Context) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.token != "" {
		return c.token, nil
	}
	if c.autoCreate {
		if err := c.createAgentIfMissing(ctx); err != nil {
			return "", err
		}
	}
	return c.activateLocked(ctx)
}

// renewSession activates a new session after the server rejected stale,
// unless a concurrent call already replaced it.
func (c *Client) renewSession(ctx context.Context, stale string) (string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.token != "" && c.token != stale {
		return c.token, nil
	}
	c.token = ""
	return c.activateLocked(ctx)
}

func (c *Client) activateLocked(ctx context.Context) (string, error) {
	var s api.Session
	if err := c.do(ctx, http.MethodPost, c.agentPath+"/activate", nil, false, &s); err != nil {
		return "", err
	}
	c.token = s.SessionToken
	return c.token, nil
}

func (c *Client) createAgentIfMissing(ctx context.Context) error {
	err := c.do(ctx, http.MethodGet, c.agentPath, nil, false, nil)
	var apiErr *APIError
	if err == nil || !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusNotFound {
		return err
	}
	_, err = c.CreateAgent(ctx, CreateAgentInput{})
	if errors.As(err, &apiErr) && apiErr.StatusCode == http.StatusConflict {
		return nil // created concurrently by someone else
	}
	return err
}

// do sends a JSON request (body may be nil) and decodes the response into
// out (which may be nil).
func (c *Client) do(ctx context.Context, method, path string, body any, withSession bool, out any) error {
	var payload []byte
	contentType := ""
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("memanto: encode request: %w", err)
		}
		payload, contentType = b, "application/json"
	}
	return c.send(ctx, method, path, payload, contentType, withSession, out)
}

// send performs one request. Session calls that get a 401 renew the session
// and are retried once.
func (c *Client) send(ctx context.Context, method, path string, payload []byte, contentType string, withSession bool, out any) error {
	baseURL, err := c.server.start(ctx)
	if err != nil {
		return err
	}
	token := ""
	if withSession {
		if token, err = c.session(ctx); err != nil {
			return err
		}
	}
	res, err := c.roundTrip(ctx, method, baseURL+path, payload, contentType, token)
	if err != nil {
		return err
	}
	if withSession && res.StatusCode == http.StatusUnauthorized {
		res.Body.Close()
		if token, err = c.renewSession(ctx, token); err != nil {
			return err
		}
		if res, err = c.roundTrip(ctx, method, baseURL+path, payload, contentType, token); err != nil {
			return err
		}
	}
	defer res.Body.Close()

	data, err := io.ReadAll(res.Body)
	if err != nil {
		return fmt.Errorf("memanto: read response: %w", err)
	}
	if res.StatusCode < 200 || res.StatusCode > 299 {
		return &APIError{Op: method + " " + path, StatusCode: res.StatusCode, Detail: errorDetail(data)}
	}
	if out == nil || res.StatusCode == http.StatusNoContent || len(data) == 0 {
		return nil
	}
	if err := json.Unmarshal(data, out); err != nil {
		return fmt.Errorf("memanto: decode %s %s response: %w", method, path, err)
	}
	return nil
}

func (c *Client) roundTrip(ctx context.Context, method, url string, payload []byte, contentType, token string) (*http.Response, error) {
	var body io.Reader
	if payload != nil {
		body = bytes.NewReader(payload)
	}
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/json")
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	if c.apiKey != "" {
		req.Header.Set("X-Api-Key", c.apiKey)
	}
	if token != "" {
		req.Header.Set("X-Session-Token", token)
	}
	return c.http.Do(req)
}

// errorDetail extracts the server's message from FastAPI's "detail", which
// is a string or memanto's {"error", "message", "details"} object, falling
// back to the raw body.
func errorDetail(body []byte) string {
	var parsed struct {
		Detail json.RawMessage `json:"detail"`
	}
	if err := json.Unmarshal(body, &parsed); err != nil || len(parsed.Detail) == 0 {
		return string(body)
	}
	var text string
	if json.Unmarshal(parsed.Detail, &text) == nil {
		return text
	}
	var obj struct {
		Message string `json:"message"`
	}
	if json.Unmarshal(parsed.Detail, &obj) == nil && obj.Message != "" {
		return obj.Message
	}
	return string(parsed.Detail)
}
