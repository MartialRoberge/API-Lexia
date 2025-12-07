# API Documentation / Documentation API

[English](#english) | [Français](#français)

---

## English

### Authentication

All API endpoints require authentication via API key.

```bash
Authorization: Bearer lx_your_api_key
```

### Rate Limits

- Default: 60 requests/minute per API key
- Configurable per key
- Headers included in responses:
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`

---

### LLM Endpoints

#### List Models

```http
GET /v1/models
```

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "general7Bv2",
      "object": "model",
      "created": 1699000000,
      "owned_by": "lexia",
      "display_name": "General 7B v2",
      "description": "General-purpose 7B model",
      "context_length": 4096,
      "capabilities": ["chat", "completion", "tool_calls"],
      "languages": ["fr", "en"],
      "status": "available"
    }
  ]
}
```

#### Chat Completion

```http
POST /v1/chat/completions
```

**Request:**
```json
{
  "model": "general7Bv2",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1699000000,
  "model": "general7Bv2",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 10,
    "total_tokens": 30
  }
}
```

#### Streaming

```http
POST /v1/chat/completions
Content-Type: application/json

{"model": "general7Bv2", "messages": [...], "stream": true}
```

**Response (SSE):**
```
data: {"id":"chatcmpl-abc","choices":[{"delta":{"role":"assistant"}}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"Hello"}}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"!"}}]}

data: [DONE]
```

---

### Speech-to-Text Endpoints

#### Create Transcription (Async)

```http
POST /v1/transcriptions
Content-Type: multipart/form-data
```

**Parameters:**
- `audio` (file): Audio file (wav, mp3, m4a, flac, ogg, webm)
- `language_code` (string): Language code (fr, en, auto)
- `speaker_diarization` (bool): Enable speaker identification
- `word_timestamps` (bool): Include word-level timing
- `webhook_url` (string): URL for completion notification

**Response (202):**
```json
{
  "id": "trans_abc123",
  "status": "queued",
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### Get Transcription

```http
GET /v1/transcriptions/{id}
```

**Response (completed):**
```json
{
  "id": "trans_abc123",
  "status": "completed",
  "created_at": "2024-01-01T00:00:00Z",
  "completed_at": "2024-01-01T00:01:00Z",
  "audio_duration": 120.5,
  "text": "Bonjour, bienvenue dans cette réunion...",
  "segments": [
    {
      "id": 0,
      "text": "Bonjour, bienvenue dans cette réunion.",
      "start": 0.0,
      "end": 2.5,
      "confidence": 0.95
    }
  ],
  "words": [
    {"text": "Bonjour", "start": 0.0, "end": 0.5, "confidence": 0.98},
    {"text": ",", "start": 0.5, "end": 0.6, "confidence": 0.99}
  ],
  "language_code": "fr",
  "language_confidence": 0.99,
  "speakers": ["SPEAKER_00", "SPEAKER_01"],
  "utterances": [
    {
      "speaker": "SPEAKER_00",
      "start": 0.0,
      "end": 2.5,
      "text": "Bonjour, bienvenue dans cette réunion.",
      "confidence": 0.95
    }
  ]
}
```

#### Sync Transcription (Short Audio)

```http
POST /v1/transcriptions/sync
Content-Type: multipart/form-data
```

Returns transcription result directly (for audio < 5 minutes).

---

### Diarization Endpoints

#### Create Diarization Job

```http
POST /v1/diarization
Content-Type: multipart/form-data
```

**Parameters:**
- `audio` (file): Audio file
- `num_speakers` (int): Exact number of speakers (1-20)
- `min_speakers` (int): Minimum speakers
- `max_speakers` (int): Maximum speakers

**Response (202):**
```json
{
  "id": "diar_abc123",
  "status": "queued",
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### Get Diarization Result

```http
GET /v1/diarization/{id}
```

**Response:**
```json
{
  "id": "diar_abc123",
  "status": "completed",
  "speakers": [
    {
      "id": "SPEAKER_00",
      "total_duration": 45.2,
      "num_segments": 12,
      "avg_segment_duration": 3.77
    },
    {
      "id": "SPEAKER_01",
      "total_duration": 38.5,
      "num_segments": 10,
      "avg_segment_duration": 3.85
    }
  ],
  "segments": [
    {"speaker": "SPEAKER_00", "start": 0.0, "end": 3.5, "confidence": 0.95},
    {"speaker": "SPEAKER_01", "start": 3.8, "end": 7.2, "confidence": 0.92}
  ],
  "overlaps": [
    {"speakers": ["SPEAKER_00", "SPEAKER_01"], "start": 15.2, "end": 15.8, "duration": 0.6}
  ],
  "stats": {
    "num_speakers": 2,
    "num_segments": 22,
    "audio_duration": 120.5,
    "num_overlaps": 3,
    "overlap_duration": 2.1
  },
  "rttm": "SPEAKER audio 1 0.000 3.500 <NA> <NA> SPEAKER_00 <NA> <NA>\n..."
}
```

---

### Jobs Endpoints

#### List Jobs

```http
GET /v1/jobs?status=completed&limit=20
```

#### Get Job

```http
GET /v1/jobs/{id}
```

#### Cancel Job

```http
DELETE /v1/jobs/{id}
```

---

### Error Responses

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "errors": [...]
    }
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

**Error Codes:**
- `AUTHENTICATION_ERROR` (401)
- `INVALID_API_KEY` (401)
- `AUTHORIZATION_ERROR` (403)
- `NOT_FOUND` (404)
- `VALIDATION_ERROR` (422)
- `RATE_LIMIT_EXCEEDED` (429)
- `INTERNAL_ERROR` (500)
- `SERVICE_UNAVAILABLE` (503)

---

## Français

### Authentification

Tous les endpoints nécessitent une authentification par clé API.

```bash
Authorization: Bearer lx_votre_cle_api
```

### Limites de Taux

- Par défaut : 60 requêtes/minute par clé API
- Configurable par clé
- Headers inclus dans les réponses :
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`

### Endpoints LLM

#### Complétion de Chat

```http
POST /v1/chat/completions
```

**Requête :**
```json
{
  "model": "general7Bv2",
  "messages": [
    {"role": "system", "content": "Tu es un assistant utile."},
    {"role": "user", "content": "Bonjour !"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000
}
```

### Endpoints Speech-to-Text

#### Créer une Transcription

```http
POST /v1/transcriptions
Content-Type: multipart/form-data
```

**Paramètres :**
- `audio` (fichier) : Fichier audio
- `language_code` (string) : Code langue (fr, en, auto)
- `speaker_diarization` (bool) : Activer l'identification des locuteurs
- `word_timestamps` (bool) : Inclure les timings mot par mot

### Endpoints Diarisation

#### Créer un Job de Diarisation

```http
POST /v1/diarization
```

**Paramètres :**
- `audio` (fichier) : Fichier audio
- `num_speakers` (int) : Nombre exact de locuteurs

### Codes d'Erreur

- `AUTHENTICATION_ERROR` (401) : Authentification requise
- `INVALID_API_KEY` (401) : Clé API invalide
- `RATE_LIMIT_EXCEEDED` (429) : Limite de taux dépassée
- `VALIDATION_ERROR` (422) : Erreur de validation
