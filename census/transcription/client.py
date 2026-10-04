"""Small, mockable HTTP client for Anthropic's Message Batches API."""

import json

import requests


class ClaudeAPIError(RuntimeError):
    def __init__(self, message, *, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class AmbiguousSubmissionError(ClaudeAPIError):
    """The server may have accepted a POST, so automatic retry is unsafe."""


class ClaudeBatchClient:
    def __init__(self, api_key, base_url, timeout=120, session=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "x-api-key": api_key,
        }

    def create_batch(self, requests_payload):
        try:
            response = self.session.post(
                f"{self.base_url}/v1/messages/batches",
                headers=self.headers,
                json={"requests": requests_payload},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise AmbiguousSubmissionError(str(exc)) from exc

        if response.status_code >= 500:
            raise AmbiguousSubmissionError(
                f"Anthropic returned HTTP {response.status_code} during submission",
                status_code=response.status_code,
                response=_safe_json(response),
            )
        if not response.ok:
            raise ClaudeAPIError(
                f"Anthropic rejected the batch with HTTP {response.status_code}",
                status_code=response.status_code,
                response=_safe_json(response),
            )
        return response.json()

    def retrieve_batch(self, provider_batch_id):
        return self._get_json(f"/v1/messages/batches/{provider_batch_id}")

    def iter_results(self, provider_batch_id):
        try:
            response = self.session.get(
                f"{self.base_url}/v1/messages/batches/{provider_batch_id}/results",
                headers=self.headers,
                timeout=self.timeout,
                stream=True,
            )
        except requests.RequestException as exc:
            raise ClaudeAPIError(str(exc)) from exc
        if not response.ok:
            raise ClaudeAPIError(
                f"Anthropic results returned HTTP {response.status_code}",
                status_code=response.status_code,
                response=_safe_json(response),
            )
        for line in response.iter_lines(decode_unicode=True):
            if line:
                yield json.loads(line)

    def _get_json(self, path):
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ClaudeAPIError(str(exc)) from exc
        if not response.ok:
            raise ClaudeAPIError(
                f"Anthropic returned HTTP {response.status_code}",
                status_code=response.status_code,
                response=_safe_json(response),
            )
        return response.json()


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {"body": response.text[:2000]}
