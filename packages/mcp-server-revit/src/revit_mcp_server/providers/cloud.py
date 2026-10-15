from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Mapping
from urllib.parse import quote, urlencode, urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .base import AECProvider, ProviderTool, enrich_mutation_metadata
from ..errors import RevitMCPError


# specklepy is slow to import (~300 ms) and only needed by the Speckle send and
# receive tools, so these names resolve it on first use. They stay module-level
# attributes so existing code and tests can still patch them.
class _LazySpeckleModule:
    def __init__(self, module_name: str) -> None:
        self._module_name = module_name

    def __getattr__(self, name: str) -> Any:
        import importlib

        return getattr(importlib.import_module(self._module_name), name)


operations = _LazySpeckleModule("specklepy.api.operations")


def SpeckleClient(*args: Any, **kwargs: Any) -> Any:  # noqa: N802
    from specklepy.api.client import SpeckleClient as _SpeckleClient

    return _SpeckleClient(*args, **kwargs)


def get_default_account(*args: Any, **kwargs: Any) -> Any:
    from specklepy.api.credentials import get_default_account as _get_default_account

    return _get_default_account(*args, **kwargs)


def ServerTransport(*args: Any, **kwargs: Any) -> Any:  # noqa: N802
    from specklepy.transports.server import ServerTransport as _ServerTransport

    return _ServerTransport(*args, **kwargs)


def Base(*args: Any, **kwargs: Any) -> Any:  # noqa: N802
    from specklepy.objects.base import Base as _Base

    return _Base(*args, **kwargs)


CredentialCallback = Callable[[str], str | None] | Callable[[str], Awaitable[str | None]]
SpeckleMergeBuilder = Callable[[Dict[str, Any]], Dict[str, Any]]

WINDOWS_PATH_PATTERN = re.compile(r"^[A-Za-z]:\\")
POSIX_PATH_PATTERN = re.compile(r"^/(?:Users|home|tmp|var|etc|opt|srv|mnt|Volumes)/")
WINDOWS_PATH_EMBEDDED_PATTERN = re.compile(r"[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]*")
POSIX_PATH_EMBEDDED_PATTERN = re.compile(r"/(?:Users|home|tmp|var|etc|opt|srv|mnt|Volumes)(?:/[^\s\"']+)*")
LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1"}
IFC_GUID_PATTERN = re.compile(r"^[0-9A-Za-z_$]{22}$")


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.strip().lower())
    return normalized in {
        "authorization",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "token",
        "password",
        "clientsecret",
        "secret",
        "codeverifier",
        "apikey",
        "authorizationcode",
        "code",
    }


def _looks_like_local_path(value: str) -> bool:
    return bool(WINDOWS_PATH_PATTERN.match(value) or POSIX_PATH_PATTERN.match(value))


def _redact_text(value: str) -> str:
    if _looks_like_local_path(value):
        return "<redacted-path>"
    redacted = WINDOWS_PATH_EMBEDDED_PATTERN.sub("<redacted-path>", value)
    redacted = POSIX_PATH_EMBEDDED_PATTERN.sub("<redacted-path>", redacted)
    return redacted


def _sanitize(value: Any, key: str | None = None) -> Any:
    if key and _is_sensitive_key(key):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {item_key: _sanitize(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _sanitize_headers(headers: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: _sanitize(value, key) for key, value in headers.items()}


def _validate_https_url(url: str, *, allow_localhost_http: bool = False, label: str = "url") -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if allow_localhost_http and parsed.scheme == "http" and parsed.hostname in LOCALHOST_HOSTS:
        return
    raise ValueError(f"{label} must use HTTPS")


def _b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _json_headers(idempotency_key: str | None = None) -> Dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    return headers


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


class BCFViewpointMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guid: str | None = None
    snapshot_url: str | None = None
    index: int | None = Field(default=None, ge=0)
    is_external: bool | None = None
    camera_view_point: Dict[str, float] | None = None


class BCFTopicPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    status: str | None = None
    topic_type: str | None = Field(default=None, alias="type")
    ifc_guid_refs: List[str] = Field(default_factory=list)
    viewpoint: BCFViewpointMetadata | None = None

    @field_validator("title", "description")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("value must not be empty")
        return trimmed

    @field_validator("ifc_guid_refs")
    @classmethod
    def _validate_ifc_guid_refs(cls, value: List[str]) -> List[str]:
        for item in value:
            if not IFC_GUID_PATTERN.match(item):
                raise ValueError(f"Invalid IFC GUID reference: {item}")
        return value


@dataclass
class OAuthTokenBundle:
    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    token_type: str = "Bearer"
    scope: str | None = None

    def is_expired(self, *, skew_seconds: int = 30) -> bool:
        if self.expires_at is None:
            return False
        return time.time() >= (self.expires_at - skew_seconds)


@dataclass
class PendingOAuthState:
    state: str
    code_verifier: str
    redirect_uri: str
    created_at: float = field(default_factory=time.time)


class OAuth2PKCETransport:
    def __init__(
        self,
        *,
        provider_name: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str,
        auth_url: str,
        token_url: str,
        scopes: List[str] | None = None,
        env_prefix: str | None = None,
        credential_callback: CredentialCallback | None = None,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
        allow_localhost_http: bool = False,
        pending_state_ttl_seconds: int = 600,
        max_pending_states: int = 32,
    ) -> None:
        self.provider_name = provider_name
        self.env_prefix = env_prefix or provider_name.upper()
        self.client_id = client_id or os.getenv(f"{self.env_prefix}_CLIENT_ID")
        self._client_secret = client_secret or os.getenv(f"{self.env_prefix}_CLIENT_SECRET")
        self.redirect_uri = redirect_uri
        self.auth_url = auth_url
        self.token_url = token_url
        self.scopes = scopes or []
        self.credential_callback = credential_callback
        self.allow_localhost_http = allow_localhost_http
        self.pending_state_ttl_seconds = pending_state_ttl_seconds
        self.max_pending_states = max_pending_states
        self._pending_states: Dict[str, PendingOAuthState] = {}
        self._token_bundle: OAuthTokenBundle | None = None
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(transport=transport, timeout=timeout)

        if not self.client_id:
            raise ValueError(f"{self.provider_name} OAuth client_id is required")
        if self.pending_state_ttl_seconds <= 0:
            raise ValueError("pending_state_ttl_seconds must be positive")
        if self.max_pending_states <= 0:
            raise ValueError("max_pending_states must be positive")
        _validate_https_url(self.auth_url, allow_localhost_http=allow_localhost_http, label="auth_url")
        _validate_https_url(self.token_url, allow_localhost_http=allow_localhost_http, label="token_url")
        _validate_https_url(self.redirect_uri, allow_localhost_http=allow_localhost_http, label="redirect_uri")

    async def _get_secret(self) -> str | None:
        if self._client_secret:
            return self._client_secret
        if self.credential_callback is None:
            return None
        secret = await _maybe_await(self.credential_callback("client_secret"))
        if secret:
            self._client_secret = secret
        return self._client_secret

    async def _get_refresh_token(self) -> str | None:
        if self._token_bundle and self._token_bundle.refresh_token:
            return self._token_bundle.refresh_token
        if self.credential_callback is None:
            return None
        return await _maybe_await(self.credential_callback("refresh_token"))

    def authorization_state(self) -> Dict[str, Any]:
        self._prune_pending_states()
        return {
            "provider": self.provider_name,
            "authorized": bool(self._token_bundle and not self._token_bundle.is_expired()),
            "has_refresh_token": bool(self._token_bundle and self._token_bundle.refresh_token),
            "expires_at": self._token_bundle.expires_at if self._token_bundle else None,
            "pending_states": len(self._pending_states),
        }

    def build_authorization_url(self) -> Dict[str, str]:
        self._prune_pending_states()
        if len(self._pending_states) >= self.max_pending_states:
            raise ValueError("Too many pending OAuth states; complete or wait for expiry before starting another flow")
        state_value = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(64)
        self._pending_states[state_value] = PendingOAuthState(
            state=state_value,
            code_verifier=code_verifier,
            redirect_uri=self.redirect_uri,
        )
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state_value,
            "code_challenge": _b64url_sha256(code_verifier),
            "code_challenge_method": "S256",
        }
        return {
            "authorization_url": f"{self.auth_url}?{urlencode(params)}",
            "state": state_value,
        }

    async def exchange_code(self, *, code: str, state: str) -> Dict[str, Any]:
        self._prune_pending_states()
        pending_state = self._pending_states.pop(state, None)
        if pending_state is None:
            raise ValueError("OAuth state validation failed")
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": pending_state.redirect_uri,
            "code_verifier": pending_state.code_verifier,
        }
        token_response = await self._post_token_form(payload)
        return self._store_token_response(token_response)

    async def refresh(self) -> Dict[str, Any]:
        refresh_token = await self._get_refresh_token()
        if not refresh_token:
            raise ValueError("No refresh token is available")
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
        }
        token_response = await self._post_token_form(payload)
        return self._store_token_response(token_response)

    async def get_access_token(self) -> str:
        if self._token_bundle and not self._token_bundle.is_expired():
            return self._token_bundle.access_token
        refresh_token = await self._get_refresh_token()
        if refresh_token:
            await self.refresh()
        if self._token_bundle and not self._token_bundle.is_expired():
            return self._token_bundle.access_token
        raise ValueError("Provider is not authenticated")

    async def _post_token_form(self, payload: Dict[str, str]) -> Dict[str, Any]:
        headers: Dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        client_secret = await self._get_secret()
        if client_secret:
            basic = base64.b64encode(f"{self.client_id}:{client_secret}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {basic}"
            payload = dict(payload)
            payload.pop("client_id", None)
        try:
            response = await self._client.post(self.token_url, data=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            details = {
                "provider": self.provider_name,
                "url": self.token_url,
                "headers": _sanitize_headers(headers),
                "payload": _sanitize(payload),
            }
            raise RuntimeError(f"OAuth token request failed: {_sanitize(str(exc))}; details={json.dumps(details)}") from exc

    def _store_token_response(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        expires_in = payload.get("expires_in")
        expires_at = time.time() + float(expires_in) if expires_in else None
        self._token_bundle = OAuthTokenBundle(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]) if payload.get("refresh_token") else None,
            expires_at=expires_at,
            token_type=str(payload.get("token_type", "Bearer")),
            scope=str(payload["scope"]) if payload.get("scope") else None,
        )
        return self.authorization_state()

    def _prune_pending_states(self) -> None:
        cutoff = time.time() - self.pending_state_ttl_seconds
        expired = [state for state, pending in self._pending_states.items() if pending.created_at < cutoff]
        for state in expired:
            self._pending_states.pop(state, None)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class CloudProviderBase(AECProvider):
    provider_identity = "cloud"
    # Exact tool names that mutate remote state (create/publish/merge/send commits,
    # branches, models, or BCF issues). Matched by exact name rather than verb, since
    # this provider's tool names include read verbs (list/get) that a generic verb
    # matcher would need to carefully exclude — an explicit, auditable set is safer
    # for a fixed-size tool surface like this one. See providers/base.py for why every
    # provider must do this: an unflagged mutating tool bypasses the ApprovalGate.
    _mutating_tool_names: frozenset[str] = frozenset()

    def __init__(
        self,
        *,
        oauth: OAuth2PKCETransport,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.oauth = oauth
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(transport=transport, timeout=timeout)
        self._capabilities = self._build_capabilities()
        enrich_mutation_metadata(self._capabilities, mutating_names=self._mutating_tool_names)

    def get_identity(self) -> str:
        return self.provider_identity

    def get_capabilities(self) -> List[ProviderTool]:
        return self._capabilities

    async def check_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.provider_identity,
            "auth": self.oauth.authorization_state(),
        }

    async def shutdown(self) -> None:
        if self._owns_client:
            await self._client.aclose()
        await self.oauth.close()

    async def execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        normalized_name = name.replace(".", "_")
        handler_name = self._tool_dispatch().get(normalized_name)
        if handler_name is None:
            raise ValueError(f"Unknown tool '{name}' on provider '{self.provider_identity}'")
        try:
            result = await getattr(self, handler_name)(arguments)
            return _sanitize(result)
        except ValidationError as exc:
            raise ValueError(json.dumps(_sanitize(exc.errors()), default=str)) from exc
        except Exception as exc:
            raise type(exc)(_sanitize(str(exc))) from exc

    def _tool_dispatch(self) -> Dict[str, str]:
        raise NotImplementedError

    def _build_capabilities(self) -> List[ProviderTool]:
        raise NotImplementedError

    async def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {await self.oauth.get_access_token()}"}

    async def _get_json(self, url: str, *, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        _validate_https_url(url, allow_localhost_http=self.oauth.allow_localhost_http, label="request_url")
        headers = await self._auth_headers()
        try:
            response = await self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            details = {"url": url, "params": params or {}, "headers": _sanitize_headers(headers)}
            raise RuntimeError(f"GET request failed: {_sanitize(str(exc))}; details={json.dumps(details)}") from exc

    async def _post_json(
        self,
        url: str,
        *,
        json_body: Dict[str, Any],
        headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        _validate_https_url(url, allow_localhost_http=self.oauth.allow_localhost_http, label="request_url")
        auth_headers = await self._auth_headers()
        merged_headers = {**auth_headers, **(headers or {})}
        try:
            response = await self._client.post(url, json=json_body, headers=merged_headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            details = {
                "url": url,
                "headers": _sanitize_headers(merged_headers),
                "body": _sanitize(json_body),
            }
            raise RuntimeError(f"POST request failed: {_sanitize(str(exc))}; details={json.dumps(details)}") from exc


class SpeckleProvider(CloudProviderBase):
    provider_identity = "speckle"
    _mutating_tool_names = frozenset({
        "speckle_create_model",
        "speckle_create_branch",
        "speckle_publish_version",
        "speckle_merge_model",
        "speckle_merge_branch",
        "speckle_send_object",
    })

    def __init__(
        self,
        *,
        host: str = "https://app.speckle.systems",
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str = "https://localhost/callback",
        scopes: List[str] | None = None,
        credential_callback: CredentialCallback | None = None,
        http_client: httpx.AsyncClient | None = None,
        oauth_http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        oauth_transport: httpx.AsyncBaseTransport | None = None,
        allow_localhost_http: bool = False,
        oauth_pending_state_ttl_seconds: int = 600,
        oauth_max_pending_states: int = 32,
        merge_operation_builder: SpeckleMergeBuilder | None = None,
    ) -> None:
        _validate_https_url(host, allow_localhost_http=allow_localhost_http, label="speckle_host")
        self.host = host.rstrip("/")
        resolved_client_id = client_id or os.getenv("SPECKLE_CLIENT_ID") or "local-credentials-only"
        self._merge_operation_builder = merge_operation_builder
        oauth = OAuth2PKCETransport(
            provider_name="speckle",
            client_id=resolved_client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            auth_url=f"{self.host}/authn/verify/{resolved_client_id or ''}",
            token_url=f"{self.host}/auth/token",
            scopes=scopes or ["profile:read", "streams:read", "streams:write"],
            env_prefix="SPECKLE",
            credential_callback=credential_callback,
            http_client=oauth_http_client,
            transport=oauth_transport,
            allow_localhost_http=allow_localhost_http,
            pending_state_ttl_seconds=oauth_pending_state_ttl_seconds,
            max_pending_states=oauth_max_pending_states,
        )
        super().__init__(oauth=oauth, http_client=http_client, transport=transport)
        self.graphql_url = f"{self.host}/graphql"

    def _tool_dispatch(self) -> Dict[str, str]:
        return {
            "speckle_health": "_tool_health",
            "speckle_auth_status": "_tool_auth_status",
            "speckle_oauth_start": "_tool_oauth_start",
            "speckle_oauth_exchange_code": "_tool_oauth_exchange_code",
            "speckle_oauth_refresh": "_tool_oauth_refresh",
            "speckle_list_projects": "_tool_list_projects",
            "speckle_list_models": "_tool_list_models",
            "speckle_list_versions": "_tool_list_versions",
            "speckle_get_version_metadata": "_tool_get_version_metadata",
            "speckle_checkout_version": "_tool_get_version_metadata",
            "speckle_create_model": "_tool_create_model",
            "speckle_create_branch": "_tool_create_branch",
            "speckle_publish_version": "_tool_publish_version",
            "speckle_merge_model": "_tool_merge_model",
            "speckle_merge_branch": "_tool_merge_model",
            "speckle_send_object": "_tool_speckle_send_object",
            "speckle_receive_object": "_tool_speckle_receive_object",
        }

    def _build_capabilities(self) -> List[ProviderTool]:
        return [
            ProviderTool(name="speckle_health", description="Check Speckle provider health.", inputSchema={"type": "object", "properties": {}}),
            ProviderTool(name="speckle_auth_status", description="Get Speckle OAuth authentication status.", inputSchema={"type": "object", "properties": {}}),
            ProviderTool(name="speckle_oauth_start", description="Generate a Speckle OAuth authorization URL using PKCE.", inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
            ProviderTool(name="speckle_oauth_exchange_code", description="Exchange a Speckle OAuth authorization code.", inputSchema={"type": "object", "properties": {"code": {"type": "string"}, "state": {"type": "string"}}, "required": ["code", "state"], "additionalProperties": False}),
            ProviderTool(name="speckle_oauth_refresh", description="Refresh the Speckle OAuth access token.", inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
            ProviderTool(name="speckle_list_projects", description="List Speckle projects.", inputSchema={"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False}),
            ProviderTool(name="speckle_list_models", description="List Speckle models for a project. Branch aliases are included for compatibility.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["project_id"], "additionalProperties": False}),
            ProviderTool(name="speckle_list_versions", description="List Speckle versions for a model or branch.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "model_id": {"type": "string"}, "branch_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "required": ["project_id"], "additionalProperties": False}),
            ProviderTool(name="speckle_get_version_metadata", description="Read Speckle version metadata.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "version_id": {"type": "string"}}, "required": ["project_id", "version_id"], "additionalProperties": False}),
            ProviderTool(name="speckle_checkout_version", description="Checkout Speckle version metadata.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "version_id": {"type": "string"}}, "required": ["project_id", "version_id"], "additionalProperties": False}),
            ProviderTool(name="speckle_create_model", description="Create an isolated Speckle model.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["project_id", "name"], "additionalProperties": False}),
            ProviderTool(name="speckle_create_branch", description="Create an isolated Speckle branch for compatibility with model workflows.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["project_id", "name"], "additionalProperties": False}),
            ProviderTool(name="speckle_publish_version", description="Publish a Speckle version by creating a commit through GraphQL.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "model_id": {"type": "string"}, "object_id": {"type": "string"}, "message": {"type": "string"}, "source_application": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["project_id", "model_id", "object_id", "message"], "additionalProperties": False}),
            ProviderTool(name="speckle_merge_model", description="Merge one Speckle model or branch into another through GraphQL.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "source_model_id": {"type": "string"}, "target_model_id": {"type": "string"}, "message": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["project_id", "source_model_id", "target_model_id", "message"], "additionalProperties": False}),
            ProviderTool(name="speckle_merge_branch", description="Compatibility alias for merge_model.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "source_model_id": {"type": "string"}, "target_model_id": {"type": "string"}, "message": {"type": "string"}, "idempotency_key": {"type": "string"}}, "required": ["project_id", "source_model_id", "target_model_id", "message"], "additionalProperties": False}),
            ProviderTool(
                name="speckle_send_object",
                description="Sends generic data objects to a Speckle stream/project using local credentials.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "The Speckle Project/Stream ID"},
                        "model_name": {"type": "string", "description": "The Model/Branch name to send to"},
                        "data": {"type": "object", "description": "JSON data to send as Base objects"},
                        "message": {"type": "string", "description": "Commit message"}
                    },
                    "required": ["project_id", "model_name", "data"],
                    "additionalProperties": False,
                }
            ),
            ProviderTool(
                name="speckle_receive_object",
                description="Receives data from a Speckle stream/project using local credentials.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "The Speckle Project/Stream ID"},
                        "version_id": {"type": "string", "description": "Specific Version/Commit ID to receive"}
                    },
                    "required": ["project_id", "version_id"],
                    "additionalProperties": False,
                }
            ),
        ]

    async def _tool_health(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await self.check_health()

    async def _tool_auth_status(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self.oauth.authorization_state()

    async def _tool_oauth_start(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self.oauth.build_authorization_url()

    async def _tool_oauth_exchange_code(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self.oauth.exchange_code(code=arguments["code"], state=arguments["state"])

    async def _tool_oauth_refresh(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await self.oauth.refresh()

    async def _tool_list_projects(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = """
        query SpeckleProjects($limit:Int!) {
          activeUser {
            projects(limit:$limit) {
              items { id name description }
            }
          }
        }
        """
        payload = await self._graphql(query=query, variables={"limit": arguments.get("limit", 20)})
        return {"projects": payload["activeUser"]["projects"]["items"]}

    async def _tool_list_models(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = """
        query SpeckleModels($projectId:String!,$limit:Int!) {
          project(id:$projectId) {
            id
            models(limit:$limit) {
              items { id name description }
            }
          }
        }
        """
        payload = await self._graphql(query=query, variables={"projectId": arguments["project_id"], "limit": arguments.get("limit", 20)})
        models = payload["project"]["models"]["items"]
        return {
            "project_id": arguments["project_id"],
            "models": [
                {
                    **model,
                    "branch_id": model["id"],
                    "branch_name": model["name"],
                }
                for model in models
            ],
        }

    async def _tool_list_versions(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        model_id = arguments.get("model_id") or arguments.get("branch_id")
        if not model_id:
            raise ValueError("model_id or branch_id is required")
        query = """
        query SpeckleVersions($projectId:String!,$modelId:String!,$limit:Int!) {
          project(id:$projectId) {
            model(id:$modelId) {
              id
              versions(limit:$limit) {
                items { id message createdAt referencedObject }
              }
            }
          }
        }
        """
        payload = await self._graphql(query=query, variables={"projectId": arguments["project_id"], "modelId": model_id, "limit": arguments.get("limit", 20)})
        return {"project_id": arguments["project_id"], "model_id": model_id, "versions": payload["project"]["model"]["versions"]["items"]}

    async def _tool_get_version_metadata(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        query = """
        query SpeckleVersion($projectId:String!,$versionId:String!) {
          project(id:$projectId) {
            version(id:$versionId) {
              id
              message
              createdAt
              sourceApplication
              referencedObject
            }
          }
        }
        """
        payload = await self._graphql(query=query, variables={"projectId": arguments["project_id"], "versionId": arguments["version_id"]})
        return {"project_id": arguments["project_id"], "version": payload["project"]["version"]}

    async def _tool_create_model(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
        mutation SpeckleCreateModel($input:CreateModelInput!) {
          projectMutations {
            modelCreate(input:$input) { id name description }
          }
        }
        """
        variables = {
            "input": {
                "projectId": arguments["project_id"],
                "name": arguments["name"],
                "description": arguments.get("description"),
            }
        }
        payload = await self._graphql(
            query=mutation,
            variables=variables,
            idempotency_key=arguments.get("idempotency_key"),
        )
        return {"model": payload["projectMutations"]["modelCreate"]}

    async def _tool_create_branch(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self._tool_create_model(arguments)

    async def _tool_publish_version(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        mutation = """
        mutation SpecklePublishVersion($input:CreateVersionInput!) {
          projectMutations {
            versionCreate(input:$input) { id message referencedObject }
          }
        }
        """
        variables = {
            "input": {
                "projectId": arguments["project_id"],
                "modelId": arguments["model_id"],
                "objectId": arguments["object_id"],
                "message": arguments["message"],
                "sourceApplication": arguments.get("source_application", "Autodesk-Revit-MCP-Server"),
            }
        }
        payload = await self._graphql(
            query=mutation,
            variables=variables,
            idempotency_key=arguments.get("idempotency_key"),
        )
        return {"version": payload["projectMutations"]["versionCreate"]}

    async def _tool_merge_model(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if self._merge_operation_builder is None:
            raise NotImplementedError(
                "Speckle merge is unsupported until an explicit merge_operation_builder is configured"
            )
        operation = self._merge_operation_builder(arguments)
        query = operation["query"]
        variables = operation["variables"]
        payload = await self._graphql(
            query=query,
            variables=variables,
            idempotency_key=arguments.get("idempotency_key"),
        )
        result_path = operation.get("result_path")
        merged = payload
        if result_path:
            for segment in result_path:
                merged = merged[segment]
        success_value = operation.get("success_value", True)
        if success_value is not None:
            merged = merged == success_value
        if not merged:
            raise RuntimeError("Speckle merge did not succeed")
        return {"merged": True}

    def _ensure_local_account(self, project_id: str) -> tuple[Any, Any]:
        account = get_default_account()
        if not account:
            raise RevitMCPError("No local Speckle account found. Please authenticate via Speckle Manager.")
        try:
            client = SpeckleClient(host=account.serverInfo.url)
            client.authenticate_with_account(account)
            transport = ServerTransport(project_id, client)
            return client, transport
        except Exception as e:
            raise RevitMCPError(f"Failed to initialize local Speckle client or transport: {e}") from e

    async def _tool_speckle_send_object(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        project_id = arguments["project_id"]
        model_name = arguments["model_name"]
        data = arguments["data"]
        message = arguments.get("message", "Sent from AEC Model Bridge")

        client, transport = self._ensure_local_account(project_id)

        # Build base object
        base_obj = Base()
        for k, v in data.items():
            setattr(base_obj, k, v)

        # Fix the legacy bug: resolve model_name -> ID via models query
        try:
            models_res = client.model.get_models(project_id, models_limit=100)
            matching_model = next((m for m in models_res.items if m.name == model_name or m.id == model_name), None)
            if not matching_model:
                raise RevitMCPError(f"Model '{model_name}' not found in project '{project_id}'.")
            model_id = matching_model.id
        except Exception as e:
            if isinstance(e, RevitMCPError):
                raise
            raise RevitMCPError(f"Failed to resolve model '{model_name}' to ID: {e}") from e

        # Send the object to transport
        try:
            obj_id = operations.send(base=base_obj, transports=[transport])
        except Exception as e:
            raise RevitMCPError(f"Failed to send object: {e}") from e

        # Create the version/commit using client
        try:
            version_id = client.version.create(
                project_id=project_id,
                model_id=model_id,
                object_id=obj_id,
                message=message,
                source_application="AECModelBridge"
            )
            return {"result": f"Successfully sent data to Speckle. Version ID: {version_id}", "version_id": version_id}
        except Exception as e:
            raise RevitMCPError(f"Data sent to transport but version creation failed: {e}") from e

    async def _tool_speckle_receive_object(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        project_id = arguments["project_id"]
        version_id = arguments["version_id"]

        client, transport = self._ensure_local_account(project_id)

        try:
            version = client.version.get(project_id, version_id)
        except Exception as e:
            raise RevitMCPError(f"Failed to retrieve version metadata: {e}") from e

        try:
            base_obj = operations.receive(obj_id=version.referencedObject, remote_transport=transport)
        except Exception as e:
            raise RevitMCPError(f"Failed to receive object data: {e}") from e

        # Deserialize and return actual object data
        try:
            serialized = operations.serialize(base_obj)
            data = json.loads(serialized)
            return {"result": data}
        except Exception as e:
            raise RevitMCPError(f"Failed to deserialize received object: {e}") from e

    async def _graphql(
        self,
        *,
        query: str,
        variables: Dict[str, Any],
        idempotency_key: str | None = None,
    ) -> Dict[str, Any]:
        body = {"query": query, "variables": variables}
        headers = _json_headers(idempotency_key)
        payload = await self._post_json(self.graphql_url, json_body=body, headers=headers)
        if payload.get("errors"):
            raise RuntimeError(f"Speckle GraphQL error: {json.dumps(_sanitize(payload['errors']))}")
        return payload["data"]


class AutodeskDataProvider(CloudProviderBase):
    provider_identity = "autodesk_data"
    _mutating_tool_names = frozenset({
        "autodesk_data_create_topic",
        "autodesk_data_create_issue",
    })

    def __init__(
        self,
        *,
        auth_base_url: str = "https://developer.api.autodesk.com/authentication/v2",
        api_base_url: str = "https://developer.api.autodesk.com",
        issues_endpoint: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str = "https://localhost/callback",
        scopes: List[str] | None = None,
        credential_callback: CredentialCallback | None = None,
        http_client: httpx.AsyncClient | None = None,
        oauth_http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        oauth_transport: httpx.AsyncBaseTransport | None = None,
        allow_localhost_http: bool = False,
        oauth_pending_state_ttl_seconds: int = 600,
        oauth_max_pending_states: int = 32,
    ) -> None:
        _validate_https_url(auth_base_url, allow_localhost_http=allow_localhost_http, label="auth_base_url")
        _validate_https_url(api_base_url, allow_localhost_http=allow_localhost_http, label="api_base_url")
        self.auth_base_url = auth_base_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/")
        self.issues_endpoint = issues_endpoint
        if issues_endpoint:
            _validate_https_url(issues_endpoint, allow_localhost_http=allow_localhost_http, label="issues_endpoint")
        oauth = OAuth2PKCETransport(
            provider_name="aps",
            client_id=client_id or os.getenv("APS_CLIENT_ID") or os.getenv("AUTODESK_CLIENT_ID"),
            client_secret=client_secret or os.getenv("APS_CLIENT_SECRET") or os.getenv("AUTODESK_CLIENT_SECRET"),
            redirect_uri=redirect_uri,
            auth_url=f"{self.auth_base_url}/authorize",
            token_url=f"{self.auth_base_url}/token",
            scopes=scopes or ["data:read", "data:write"],
            env_prefix="APS",
            credential_callback=credential_callback,
            http_client=oauth_http_client,
            transport=oauth_transport,
            allow_localhost_http=allow_localhost_http,
            pending_state_ttl_seconds=oauth_pending_state_ttl_seconds,
            max_pending_states=oauth_max_pending_states,
        )
        super().__init__(oauth=oauth, http_client=http_client, transport=transport)

    def _tool_dispatch(self) -> Dict[str, str]:
        return {
            "autodesk_data_health": "_tool_health",
            "autodesk_data_auth_status": "_tool_auth_status",
            "autodesk_data_oauth_start": "_tool_oauth_start",
            "autodesk_data_oauth_exchange_code": "_tool_oauth_exchange_code",
            "autodesk_data_oauth_refresh": "_tool_oauth_refresh",
            "autodesk_data_list_hubs": "_tool_list_hubs",
            "autodesk_data_list_projects": "_tool_list_projects",
            "autodesk_data_list_items": "_tool_list_items",
            "autodesk_data_get_version_metadata": "_tool_get_version_metadata",
            "autodesk_data_checkout_version": "_tool_get_version_metadata",
            "autodesk_data_create_topic": "_tool_create_topic",
            "autodesk_data_create_issue": "_tool_create_topic",
        }

    def _build_capabilities(self) -> List[ProviderTool]:
        return [
            ProviderTool(name="autodesk_data_health", description="Check Autodesk Data provider health.", inputSchema={"type": "object", "properties": {}}),
            ProviderTool(name="autodesk_data_auth_status", description="Get Autodesk OAuth authentication status.", inputSchema={"type": "object", "properties": {}}),
            ProviderTool(name="autodesk_data_oauth_start", description="Generate an Autodesk OAuth authorization URL using PKCE.", inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
            ProviderTool(name="autodesk_data_oauth_exchange_code", description="Exchange an Autodesk OAuth authorization code.", inputSchema={"type": "object", "properties": {"code": {"type": "string"}, "state": {"type": "string"}}, "required": ["code", "state"], "additionalProperties": False}),
            ProviderTool(name="autodesk_data_oauth_refresh", description="Refresh the Autodesk OAuth access token.", inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
            ProviderTool(name="autodesk_data_list_hubs", description="List Autodesk Construction Cloud hubs.", inputSchema={"type": "object", "properties": {}, "additionalProperties": False}),
            ProviderTool(name="autodesk_data_list_projects", description="List Autodesk projects in a hub.", inputSchema={"type": "object", "properties": {"hub_id": {"type": "string"}}, "required": ["hub_id"], "additionalProperties": False}),
            ProviderTool(name="autodesk_data_list_items", description="List Autodesk items in a project folder or container.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "folder_id": {"type": "string"}}, "required": ["project_id", "folder_id"], "additionalProperties": False}),
            ProviderTool(name="autodesk_data_get_version_metadata", description="Read Autodesk item/version metadata.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "version_id": {"type": "string"}}, "required": ["project_id", "version_id"], "additionalProperties": False}),
            ProviderTool(name="autodesk_data_checkout_version", description="Checkout Autodesk version metadata.", inputSchema={"type": "object", "properties": {"project_id": {"type": "string"}, "version_id": {"type": "string"}}, "required": ["project_id", "version_id"], "additionalProperties": False}),
            ProviderTool(name="autodesk_data_create_topic", description="Create a BCF-compatible issue/topic through a configured endpoint.", inputSchema={"type": "object", "properties": {"container_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}, "status": {"type": "string"}, "type": {"type": "string"}, "ifc_guid_refs": {"type": "array", "items": {"type": "string"}}, "viewpoint": {"type": "object"}, "idempotency_key": {"type": "string"}}, "required": ["container_id", "title", "description"], "additionalProperties": False}),
            ProviderTool(name="autodesk_data_create_issue", description="Compatibility alias for create_topic.", inputSchema={"type": "object", "properties": {"container_id": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}, "status": {"type": "string"}, "type": {"type": "string"}, "ifc_guid_refs": {"type": "array", "items": {"type": "string"}}, "viewpoint": {"type": "object"}, "idempotency_key": {"type": "string"}}, "required": ["container_id", "title", "description"], "additionalProperties": False}),
        ]

    async def _tool_health(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await self.check_health()

    async def _tool_auth_status(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self.oauth.authorization_state()

    async def _tool_oauth_start(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self.oauth.build_authorization_url()

    async def _tool_oauth_exchange_code(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return await self.oauth.exchange_code(code=arguments["code"], state=arguments["state"])

    async def _tool_oauth_refresh(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await self.oauth.refresh()

    async def _tool_list_hubs(self, _: Dict[str, Any]) -> Dict[str, Any]:
        payload = await self._get_json(self._hub_list_url())
        return {"hubs": payload.get("data", [])}

    async def _tool_list_projects(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = await self._get_json(self._projects_url(arguments["hub_id"]))
        return {"hub_id": arguments["hub_id"], "projects": payload.get("data", [])}

    async def _tool_list_items(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = await self._get_json(self._folder_contents_url(arguments["project_id"], arguments["folder_id"]))
        return {"project_id": arguments["project_id"], "folder_id": arguments["folder_id"], "items": payload.get("data", [])}

    async def _tool_get_version_metadata(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = await self._get_json(self._version_url(arguments["project_id"], arguments["version_id"]))
        return {"project_id": arguments["project_id"], "version": payload.get("data")}

    async def _tool_create_topic(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not self.issues_endpoint:
            raise ValueError("issues_endpoint is not configured")
        payload = BCFTopicPayload.model_validate(
            {
                "title": arguments["title"],
                "description": arguments["description"],
                "status": arguments.get("status"),
                "type": arguments.get("type"),
                "ifc_guid_refs": arguments.get("ifc_guid_refs", []),
                "viewpoint": arguments.get("viewpoint"),
            }
        )
        body = {
            "containerId": arguments["container_id"],
            "topic": {
                "title": payload.title,
                "description": payload.description,
                "status": payload.status,
                "type": payload.topic_type,
                "ifcGuidRefs": payload.ifc_guid_refs,
                "viewpoint": payload.viewpoint.model_dump(exclude_none=True) if payload.viewpoint else None,
            },
        }
        return await self._post_json(
            self.issues_endpoint,
            json_body=body,
            headers=_json_headers(arguments.get("idempotency_key")),
        )

    def _hub_list_url(self) -> str:
        return f"{self.api_base_url}/project/v1/hubs"

    def _projects_url(self, hub_id: str) -> str:
        return f"{self.api_base_url}/project/v1/hubs/{self._path_segment(hub_id, 'hub_id')}/projects"

    def _folder_contents_url(self, project_id: str, folder_id: str) -> str:
        return (
            f"{self.api_base_url}/data/v1/projects/{self._path_segment(project_id, 'project_id')}"
            f"/folders/{self._path_segment(folder_id, 'folder_id')}/contents"
        )

    def _version_url(self, project_id: str, version_id: str) -> str:
        return (
            f"{self.api_base_url}/data/v1/projects/{self._path_segment(project_id, 'project_id')}"
            f"/versions/{self._path_segment(version_id, 'version_id')}"
        )

    @staticmethod
    def _path_segment(identifier: str, label: str) -> str:
        value = str(identifier).strip()
        if not value:
            raise ValueError(f"{label} is required")
        return quote(value, safe="")
