# Anthropic Metrics Tracking

Manual metrics tracking for Anthropic API calls using `TokenUsage` and tracker methods.

## What Gets Tracked

- Input/output/total tokens (manual)
- Duration (automatic with `track_duration_of`)
- Success/failure status

## Implementation
```python
import anthropic
from ldai.tracker import TokenUsage

client = anthropic.Anthropic()

def call_with_tracking(config, user_prompt: str):
    """Anthropic call with manual metrics tracking."""
    if not config.enabled:
        return None

    tracker = config.tracker

    # Track duration of the call
    response = tracker.track_duration_of(
        lambda: client.messages.create(
            model=config.model.name,
            max_tokens=1024,
            messages=[{"role": "user", "content": user_prompt}]
        )
    )

    # Manually track tokens using TokenUsage object
    if hasattr(response, 'usage'):
        tokens = TokenUsage(
            total=response.usage.input_tokens + response.usage.output_tokens,
            input=response.usage.input_tokens,
            output=response.usage.output_tokens
        )
        tracker.track_tokens(tokens)

    tracker.track_success()
    return response.content[0].text
```

## With System Prompt from Config
```python
def call_with_system_prompt(config, user_prompt: str):
    """Anthropic call using system prompt from AI Config."""
    if not config.enabled:
        return None

    tracker = config.tracker
    system_content = config.messages[0].content if config.messages else ""

    response = tracker.track_duration_of(
        lambda: client.messages.create(
            model=config.model.name,
            max_tokens=1024,
            system=system_content,
            messages=[{"role": "user", "content": user_prompt}]
        )
    )

    if hasattr(response, 'usage'):
        tokens = TokenUsage(
            total=response.usage.input_tokens + response.usage.output_tokens,
            input=response.usage.input_tokens,
            output=response.usage.output_tokens
        )
        tracker.track_tokens(tokens)

    tracker.track_success()
    return response.content[0].text
```

## With Error Handling
```python
def call_with_tracking_safe(config, user_prompt: str):
    """Anthropic call with metrics and error tracking."""
    if not config.enabled:
        return None

    tracker = config.tracker

    try:
        response = tracker.track_duration_of(
            lambda: client.messages.create(
                model=config.model.name,
                max_tokens=1024,
                messages=[{"role": "user", "content": user_prompt}]
            )
        )

        if hasattr(response, 'usage'):
            tokens = TokenUsage(
                total=response.usage.input_tokens + response.usage.output_tokens,
                input=response.usage.input_tokens,
                output=response.usage.output_tokens
            )
            tracker.track_tokens(tokens)

        tracker.track_success()
        return response.content[0].text

    except Exception as e:
        tracker.track_error()
        raise
```

## Notes

- Anthropic doesn't have automatic tracking like OpenAI
- Use `track_duration_of()` to wrap the call for timing
- Extract tokens from `response.usage` and create a `TokenUsage` object
- Call `track_success()` explicitly after successful completion
- For streaming, see `streaming-tracking.md` instead
