# Sample Authentication Service

This repository demonstrates refresh token validation for the local RAG end-to-end test.

## Token rules

A refresh token is rejected when it is revoked or when its expiration timestamp is in the past.
The service returns `TokenExpiredError` for expired tokens.
