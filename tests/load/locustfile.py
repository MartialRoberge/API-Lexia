"""
Load testing with Locust for Lexia API.

Usage:
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 to configure and start the test.
"""

import json
import random
import string

from locust import HttpUser, between, task


def random_string(length: int = 10) -> str:
    """Generate random string."""
    return "".join(random.choices(string.ascii_lowercase, k=length))


class LexiaAPIUser(HttpUser):
    """Simulates a user of the Lexia API."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    api_key = "lx_test_load_testing_key"

    def on_start(self):
        """Set up headers on user start."""
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    @task(10)
    def health_check(self):
        """Check health endpoint - most frequent."""
        self.client.get("/health")

    @task(5)
    def list_models(self):
        """List available models."""
        self.client.get("/v1/models", headers=self.headers)

    @task(8)
    def chat_completion_short(self):
        """Short chat completion request."""
        self.client.post(
            "/v1/chat/completions",
            headers=self.headers,
            json={
                "model": "general7Bv2",
                "messages": [{"role": "user", "content": "Bonjour, comment ça va?"}],
                "max_tokens": 50,
            },
        )

    @task(3)
    def chat_completion_long(self):
        """Longer chat completion request."""
        self.client.post(
            "/v1/chat/completions",
            headers=self.headers,
            json={
                "model": "general7Bv2",
                "messages": [
                    {"role": "system", "content": "Tu es un assistant utile."},
                    {"role": "user", "content": "Explique-moi le concept de machine learning en détail."},
                ],
                "max_tokens": 500,
            },
        )

    @task(2)
    def chat_completion_with_history(self):
        """Chat completion with conversation history."""
        self.client.post(
            "/v1/chat/completions",
            headers=self.headers,
            json={
                "model": "general7Bv2",
                "messages": [
                    {"role": "system", "content": "Tu es un expert en Python."},
                    {"role": "user", "content": "Comment créer une liste en Python?"},
                    {"role": "assistant", "content": "Voici comment: my_list = [1, 2, 3]"},
                    {"role": "user", "content": "Et pour ajouter un élément?"},
                ],
                "max_tokens": 200,
            },
        )

    @task(1)
    def list_jobs(self):
        """List jobs."""
        self.client.get("/v1/jobs", headers=self.headers)


class TranscriptionUser(HttpUser):
    """Simulates transcription API usage."""

    wait_time = between(5, 15)  # Transcriptions are less frequent
    api_key = "lx_test_transcription_key"

    def on_start(self):
        """Set up headers on user start."""
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    @task(1)
    def submit_transcription(self):
        """Submit a transcription job."""
        self.client.post(
            "/v1/transcriptions",
            headers=self.headers,
            json={
                "audio_url": f"https://example.com/audio/{random_string()}.wav",
                "language_code": "fr",
                "speaker_diarization": True,
            },
        )


class AggressiveUser(HttpUser):
    """Simulates aggressive/abusive API usage for stress testing."""

    wait_time = between(0.1, 0.5)  # Very fast requests
    api_key = "lx_test_aggressive_key"

    def on_start(self):
        """Set up headers on user start."""
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    @task(5)
    def rapid_chat_requests(self):
        """Rapid fire chat requests."""
        self.client.post(
            "/v1/chat/completions",
            headers=self.headers,
            json={
                "model": "general7Bv2",
                "messages": [{"role": "user", "content": random_string(100)}],
                "max_tokens": 10,
            },
        )

    @task(3)
    def rapid_health_checks(self):
        """Rapid health checks."""
        self.client.get("/health")

    @task(1)
    def large_context_request(self):
        """Request with large context."""
        large_messages = [
            {"role": "user", "content": random_string(1000)},
            {"role": "assistant", "content": random_string(1000)},
        ] * 10  # 20 messages

        self.client.post(
            "/v1/chat/completions",
            headers=self.headers,
            json={
                "model": "general7Bv2",
                "messages": large_messages,
                "max_tokens": 100,
            },
        )
