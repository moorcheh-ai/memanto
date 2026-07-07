\# Bug Report: Invalid Authorization Header Format in Moorcheh API



\## Summary

The Moorcheh API returns a 403 error when using the provided API key, with the message: "Invalid key=value pair (missing equal-sign) in Authorization header". This occurs because the API key format does not include the required `=` character in the hash.



\## Steps to Reproduce

1\. Set up Memanto with a valid Moorcheh API key.

2\. Run the test script `test\_concurrent\_writes.py`.

3\. Observe the 403 error responses.



\## Expected Behavior

The API should accept the provided key and return a 200 OK response.



\## Actual Behavior

All requests return a 403 error with the message: "Invalid key=value pair (missing equal-sign) in Authorization header".



\## Impact

This bug prevents any integration with the Moorcheh API, making Memanto unusable with the provided key.



\## Proposed Fix

Update the authentication header format to include the required `=` character, or update the documentation to clarify the correct key format.

