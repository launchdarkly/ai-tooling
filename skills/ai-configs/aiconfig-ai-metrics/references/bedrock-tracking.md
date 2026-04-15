# AWS Bedrock Metrics Tracking

Automatic metrics tracking for AWS Bedrock Converse API using `track_bedrock_converse_metrics()`.

## What Gets Tracked Automatically

- Input/output/total tokens
- Success status

## Implementation
```python
import boto3

bedrock = boto3.client("bedrock-runtime")

def call_with_tracking(config, user_prompt: str):
    """Bedrock Converse call with automatic metrics tracking."""
    if not config.enabled:
        return None

    tracker = config.tracker

    # Make the Bedrock call
    response = tracker.track_duration_of(
        lambda: bedrock.converse(
            modelId=config.model.name,
            messages=[{"role": "user", "content": [{"text": user_prompt}]}]
        )
    )

    # Track Bedrock-specific metrics from response
    tracker.track_bedrock_converse_metrics(response)

    return response["output"]["message"]["content"][0]["text"]
```

## With System Prompt from Config
```python
def call_with_system_prompt(config, user_prompt: str):
    """Bedrock call using system prompt from AI Config."""
    if not config.enabled:
        return None

    tracker = config.tracker
    system_content = config.messages[0].content if config.messages else ""

    response = tracker.track_duration_of(
        lambda: bedrock.converse(
            modelId=config.model.name,
            system=[{"text": system_content}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}]
        )
    )

    tracker.track_bedrock_converse_metrics(response)

    return response["output"]["message"]["content"][0]["text"]
```

## With Error Handling
```python
def call_with_tracking_safe(config, user_prompt: str):
    """Bedrock call with metrics and error tracking."""
    if not config.enabled:
        return None

    tracker = config.tracker

    try:
        response = tracker.track_duration_of(
            lambda: bedrock.converse(
                modelId=config.model.name,
                messages=[{"role": "user", "content": [{"text": user_prompt}]}]
            )
        )

        tracker.track_bedrock_converse_metrics(response)
        return response["output"]["message"]["content"][0]["text"]

    except Exception as e:
        tracker.track_error()
        raise
```

## Notes

- `track_bedrock_converse_metrics()` extracts tokens from Bedrock's response format
- Wrap with `track_duration_of()` to capture timing
- This works with the Converse API; for legacy InvokeModel, use manual tracking
