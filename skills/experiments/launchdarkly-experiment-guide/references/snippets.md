# Code snippets

Give the user the exact code they need to paste, matched to the SDK detected in
[discovery.md](discovery.md). Two kinds: **flag evaluation** (splits traffic for
the experiment) and **metric tracking** (emits the event the primary metric
counts). Replace `flag-key`, `metric-event-key`, and the context/user shape to
match their code.

> These are starting points. For flag creation + wiring that matches the
> codebase, delegate to `launchdarkly-flag-create`; for the `track()` call and
> event wiring, delegate to `launchdarkly-metric-instrument`. The snippets below
> are what those skills produce, shown here so you can hand them over inline.

## Flag evaluation (control vs. treatment)

**Node server SDK**
```js
const showNewCheckout = await ldClient.variation('new-checkout', context, false);
if (showNewCheckout) {
  // treatment: redesigned checkout
} else {
  // control: current checkout
}
```

**React client SDK**
```jsx
import { useFlags } from 'launchdarkly-react-client-sdk';

function Checkout() {
  const { newCheckout } = useFlags();
  return newCheckout ? <NewCheckout /> : <CurrentCheckout />;
}
```

**Python server SDK**
```python
show_new_checkout = ld_client.variation("new-checkout", context, False)
if show_new_checkout:
    ...  # treatment
else:
    ...  # control
```

**Go server SDK**
```go
showNewCheckout, _ := ldClient.BoolVariation("new-checkout", context, false)
if showNewCheckout {
    // treatment
} else {
    // control
}
```

## Metric tracking (emit the event the experiment measures)

Call `track` at the moment the outcome happens (e.g. when checkout completes).
The event key must match the metric's event key.

**Node server SDK**
```js
ldClient.track('checkout-completed', context);
// numeric metric (e.g. order value):
ldClient.track('order-value', context, undefined, 42.50);
```

**React / JS client SDK**
```js
ldClient.track('checkout-completed');
ldClient.track('order-value', undefined, 42.50); // numeric metric
```

**Python server SDK**
```python
ld_client.track("checkout-completed", context)
ld_client.track("order-value", context, metric_value=42.50)  # numeric metric
```

**Go server SDK**
```go
ldClient.TrackEvent("checkout-completed", context)
ldClient.TrackMetric("order-value", context, ldvalue.Null(), 42.50) // numeric
```

## Notes for the user

- **Conversion vs. numeric metric:** a conversion metric counts whether the
  event happened (checkout completed: yes/no). A numeric metric averages a value
  you pass (order value, load time). Pass the value as the last `track` argument
  for numeric metrics.
- **Context matching:** the context/user you pass to `variation` and `track`
  must be the *same* so LaunchDarkly can attribute the outcome to the variation
  the user saw.
- **Randomization unit:** experiments split on a context kind (usually `user`).
  Keep it consistent between evaluation and tracking.
