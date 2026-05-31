#!/usr/bin/env python3
"""Fix all B904 raise-without-from-inside-except issues."""
import os

def fix_file(path, replacements):
    with open(path, 'r') as f:
        content = f.read()
    changed = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            changed = True
            print(f"  OK: {old[:60]}... -> {new[:60]}...")
        else:
            print(f"  WARN: not found: {old[:80]}")
    if changed:
        with open(path, 'w') as f:
            f.write(content)
        print(f"FIXED: {path}")
    else:
        print(f"NO CHANGES: {path}")

base = '/Users/hhh/memanto/memanto'

# --- auth_deps.py ---
fix_file(f'{base}/app/routes/auth_deps.py', [
    ("        raise map_error_to_http_exception(e)\n",
     "        raise map_error_to_http_exception(e) from e\n"),
])

# --- memory.py (routes) ---
fix_file(f'{base}/app/routes/memory.py', [
    # ValueError from None (new clean validation error, don't need the parse trace)
    ("            except ValueError:\n                raise ValueError(\n                    f\"Invalid value '{v}'. Use YYYY-MM-DD or ISO 8601 datetime.\"\n                )",
     "            except ValueError:\n                raise ValueError(\n                    f\"Invalid value '{v}'. Use YYYY-MM-DD or ISO 8601 datetime.\"\n                ) from None"),
    # map_error_to_http_exception -> from e
    ("        raise map_error_to_http_exception(e)\n",
     "        raise map_error_to_http_exception(e) from e\n"),
])

# --- namespaces.py ---
fix_file(f'{base}/app/routes/namespaces.py', [
    ("        raise map_error_to_http_exception(e)\n",
     "        raise map_error_to_http_exception(e) from e\n"),
])

# --- sessions.py ---
fix_file(f'{base}/app/routes/sessions.py', [
    ("        raise map_error_to_http_exception(e)\n",
     "        raise map_error_to_http_exception(e) from e\n"),
])

# --- agent_service.py ---
fix_file(f'{base}/app/services/agent_service.py', [
    ("            except Exception as e:\n                # Unexpected error - fail the agent creation\n                raise Exception(\n                    f\"Failed to create namespace '{namespace}' in Moorcheh: {e!s}\"\n                )",
     "            except Exception as e:\n                # Unexpected error - fail the agent creation\n                raise Exception(\n                    f\"Failed to create namespace '{namespace}' in Moorcheh: {e!s}\"\n                ) from e"),
])

# --- daily_summary_service.py ---
fix_file(f'{base}/app/services/daily_summary_service.py', [
    ("        except Exception as e:\n            raise MemoryError(f\"AI summarization failed: {e!s}\")",
     "        except Exception as e:\n            raise MemoryError(f\"AI summarization failed: {e!s}\") from e"),
    ("        except Exception as e:\n            raise MemoryError(f\"Conflict detection failed: {e!s}\")",
     "        except Exception as e:\n            raise MemoryError(f\"Conflict detection failed: {e!s}\") from e"),
])

# --- memory_read_service.py ---
memory_read = f'{base}/app/services/memory_read_service.py'
with open(memory_read, 'r') as f:
    mr_content = f.read()

# Pattern: raise MemoryError(...) inside except
import re
count = 0
def repl(m):
    global count
    count += 1
    return m.group(0) + " from e"
mr_new = re.sub(r'(\n\s+raise MemoryError\(f".+?")', repl, mr_content)
if count > 0:
    with open(memory_read, 'w') as f:
        f.write(mr_new)
    print(f"FIXED: {memory_read} ({count} MemoryError fixes)")
else:
    print(f"NO CHANGES: {memory_read}")

# --- memory_write_service.py ---
fix_file(f'{base}/app/services/memory_write_service.py', [
    ("        except Exception as e:\n            raise MemoryError(f\"Failed to store memory: {e}\")",
     "        except Exception as e:\n            raise MemoryError(f\"Failed to store memory: {e}\") from e"),
    ("        except Exception as e:\n            raise MemoryError(f\"Failed to batch store memories: {e}\")",
     "        except Exception as e:\n            raise MemoryError(f\"Failed to batch store memories: {e}\") from e"),
    ("        except Exception as e:\n            raise MemoryError(f\"Failed to update memory: {e}\")",
     "        except Exception as e:\n            raise MemoryError(f\"Failed to update memory: {e}\") from e"),
    ("        except Exception as e:\n            raise MemoryError(f\"Failed to delete memory: {e}\")",
     "        except Exception as e:\n            raise MemoryError(f\"Failed to delete memory: {e}\") from e"),
])

# --- namespace_service.py ---
fix_file(f'{base}/app/services/namespace_service.py', [
    ("            except Exception as e:\n                raise NamespaceError(f\"Failed to create namespace: {e}\")",
     "            except Exception as e:\n                raise NamespaceError(f\"Failed to create namespace: {e}\") from e"),
    ("        except Exception as e:\n            raise NamespaceError(f\"Failed to list namespaces: {e}\")",
     "        except Exception as e:\n            raise NamespaceError(f\"Failed to list namespaces: {e}\") from e"),
    ("        except Exception as e:\n            raise NamespaceError(f\"Failed to delete namespace: {e}\")",
     "        except Exception as e:\n            raise NamespaceError(f\"Failed to delete namespace: {e}\") from e"),
])

# --- session_service.py ---
fix_file(f'{base}/app/services/session_service.py', [
    # jwt.ExpiredSignatureError - not bound, need to add as e
    ("        except jwt.ExpiredSignatureError:\n            raise SessionExpiredError(\"Session token expired\")",
     "        except jwt.ExpiredSignatureError as e:\n            raise SessionExpiredError(\"Session token expired\") from e"),
    # jwt.InvalidTokenError as e
    ("        except jwt.InvalidTokenError as e:\n            raise InvalidSessionTokenError(f\"Invalid session token: {e!s}\")",
     "        except jwt.InvalidTokenError as e:\n            raise InvalidSessionTokenError(f\"Invalid session token: {e!s}\") from e"),
])

# --- ui_router.py ---
fix_file(f'{base}/app/ui/routes/ui_router.py', [
    ("    except ValueError as e:\n        raise HTTPException(status_code=400, detail=str(e))\n    except Exception as e:\n        raise HTTPException(status_code=500, detail=str(e))",
     "    except ValueError as e:\n        raise HTTPException(status_code=400, detail=str(e)) from e\n    except Exception as e:\n        raise HTTPException(status_code=500, detail=str(e)) from e"),
])

# --- direct_client.py (cli) ---
cli_base = '/Users/hhh/memanto/memanto/cli'
fix_file(f'{cli_base}/client/direct_client.py', [
    ("            except json.JSONDecodeError:\n                raise Exception(f\"Moorcheh API Error {e.code}: {body}\")",
     "            except json.JSONDecodeError:\n                raise Exception(f\"Moorcheh API Error {e.code}: {body}\") from e"),
    ("        except Exception as e:\n            raise Exception(f\"Moorcheh Connection Error: {e}\")",
     "        except Exception as e:\n            raise Exception(f\"Moorcheh Connection Error: {e}\") from e"),
])

# --- core.py (cli commands) ---
fix_file(f'{cli_base}/commands/core.py', [
    ("        except AuthenticationError:\n            console.print(\"[red]Invalid Moorcheh API key.[/red]\")\n            raise typer.Exit(1)",
     "        except AuthenticationError as e:\n            console.print(\"[red]Invalid Moorcheh API key.[/red]\")\n            raise typer.Exit(1) from e"),
])

print("\n=== All done ===")
