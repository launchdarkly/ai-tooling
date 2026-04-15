# Streaming Metrics Tracking

Manual metrics tracking for streaming AI responses, including time-to-first-token (TTFT).

## What Gets Tracked

- Time to first token (TTFT)
- Total duration
- Token counts (estimated or from final chunk)
- Success/failure status

## Implementation
```python
import time
import openai
from ldai.tracker import TokenUsage

def call_streaming_with_tracking(config, user_prompt: str):
    """Streaming call with TTFT and duration tracking."""
    if not config.enabled:
        return None

    tracker = config.tracker
    start_time = time.time()
    first_token_time = None

    stream = openai.chat.completions.create(
        model=config.model.name,
        messages=[{"role": "user", "content": user_prompt}],
        stream=True
    )

    response_text = ""
    for chunk in stream:
        if first_token_time is None and chunk.choices[0].delta.content:
            first_token_time = time.time()
            ttft_ms = int((first_token_time - start_time) * 1000)
            tracker.track_time_to_first_token(ttft_ms)

        if chunk.choices[0].delta.content:
            response_text += chunk.choices[0].delta.content

    # Track final metrics (milliseconds)
    duration_ms = int((time.time() - start_time) * 1000)
    tracker.track_duration(duration_ms)
    tracker.track_success()

    # Estimate tokens (or use tiktoken for accuracy)
    estimated_input = len(user_prompt.split()) * 2
    estimated_output = len(response_text.split()) * 2
    tokens = TokenUsage(
        total=estimated_input + estimated_output,
        input=estimated_input,
        output=estimated_output
    )
    tracker.track_tokens(tokens)

    return response_text
```

## With Accurate Token Counting (tiktoken)
```python
import time
import openai
import tiktoken
from ldai.tracker import TokenUsage

def call_streaming_accurate_tokens(config, user_prompt: str):
    """Streaming with accurate token counting using tiktoken."""
    if not config.enabled:
        return None

    tracker = config.tracker
    start_time = time.time()
    first_token_time = None

    # Get encoder for the model
    try:
        enc = tiktoken.encoding_for_model(config.model.name)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")

    stream = openai.chat.completions.create(
        model=config.model.name,
        messages=[{"role": "user", "content": user_prompt}],
        stream=True
    )

    response_text = ""
    for chunk in stream:
        if first_token_time is None and chunk.choices[0].delta.content:
            first_token_time = time.time()
            ttft_ms = int((first_token_time - start_time) * 1000)
            tracker.track_time_to_first_token(ttft_ms)

        if chunk.choices[0].delta.content:
            response_text += chunk.choices[0].delta.content

    # Track final metrics
    duration_ms = int((time.time() - start_time) * 1000)
    tracker.track_duration(duration_ms)
    tracker.track_success()

    # Accurate token counts
    input_tokens = len(enc.encode(user_prompt))
    output_tokens = len(enc.encode(response_text))
    tokens = TokenUsage(
        total=input_tokens + output_tokens,
        input=input_tokens,
        output=output_tokens
    )
    tracker.track_tokens(tokens)

    return response_text
```

## With Error Handling
```python
def call_streaming_safe(config, user_prompt: str):
    """Streaming call with error tracking."""
    if not config.enabled:
        return None

    tracker = config.tracker
    start_time = time.time()
    first_token_time = None

    try:
        stream = openai.chat.completions.create(
            model=config.model.name,
            messages=[{"role": "user", "content": user_prompt}],
            stream=True
        )

        response_text = ""
        for chunk in stream:
            if first_token_time is None and chunk.choices[0].delta.content:
                first_token_time = time.time()
                ttft_ms = int((first_token_time - start_time) * 1000)
                tracker.track_time_to_first_token(ttft_ms)

            if chunk.choices[0].delta.content:
                response_text += chunk.choices[0].delta.content

        duration_ms = int((time.time() - start_time) * 1000)
        tracker.track_duration(duration_ms)
        tracker.track_success()

        return response_text

    except Exception as e:
        tracker.track_error()
        raise
```

## Notes

- TTFT is tracked when the first content chunk arrives
- Duration is tracked from stream start to completion
- Token counts must be estimated or calculated with tiktoken
- Works with any streaming provider (OpenAI, Anthropic, etc.)
- Error tracking should wrap the entire stream consumption
