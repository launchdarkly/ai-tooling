# OpenAI Metrics Tracking

Automatic metrics tracking for OpenAI API calls using `track_openai_metrics()`.

## What Gets Tracked Automatically

- Input/output/total tokens
- Duration
- Success/failure status

## Implementation
```python
import openai

def call_with_tracking(config, user_prompt: str):
    """OpenAI call with automatic metrics tracking."""
    if not config.enabled:
        return None

    response = config.tracker.track_openai_metrics(
        lambda: openai.chat.completions.create(
            model=config.model.name,
            messages=[
                {"role": "system", "content": config.messages[0].content},
                {"role": "user", "content": user_prompt}
            ]
        )
    )

    return response.choices[0].message.content
```

## With Error Handling
```python
def call_with_tracking_safe(config, user_prompt: str):
    """OpenAI call with metrics and error tracking."""
    if not config.enabled:
        return None

    try:
        response = config.tracker.track_openai_metrics(
            lambda: openai.chat.completions.create(
                model=config.model.name,
                messages=[
                    {"role": "system", "content": config.messages[0].content},
                    {"role": "user", "content": user_prompt}
                ]
            )
        )
        return response.choices[0].message.content

    except Exception as e:
        config.tracker.track_error()
        raise
```

## Adapting Existing Code

If you have existing OpenAI calls like this:
```python
# Before
response = openai.chat.completions.create(
    model="gpt-4",
    messages=messages
)
```

Wrap them like this:
```python
# After
response = config.tracker.track_openai_metrics(
    lambda: openai.chat.completions.create(
        model=config.model.name,
        messages=messages
    )
)
```

## Notes

- The wrapper returns the original OpenAI response object unchanged
- Token counts are extracted from the response automatically
- Duration is measured from call start to completion
- For streaming, see `streaming-tracking.md` instead
