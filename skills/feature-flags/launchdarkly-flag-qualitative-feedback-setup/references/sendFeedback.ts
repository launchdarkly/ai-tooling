// Session replay import — remove this line if @launchdarkly/session-replay is not installed
import { LDRecord } from "@launchdarkly/session-replay";
import type { LDClient } from "launchdarkly-js-client-sdk";

export type LDFeedbackData = {
  feedback_answer: string;
  flag_key: string;
  sentiment?: LDFeedbackSentiment;
  feedback_prompt?: string;
  o11y_session_id?: string;
  custom_properties?: Record<string, any>;
};

export type LDFeedbackSentiment = "positive" | "neutral" | "negative";

export function sendFeedback(
  client: LDClient,
  flagKey: string,
  feedback: string,
  sentiment?: LDFeedbackSentiment,
  prompt?: string,
  customProperties?: Record<string, any>,
) {
  const feedbackData: LDFeedbackData = {
    feedback_answer: feedback,
    flag_key: flagKey,
    sentiment: sentiment ?? "neutral",
    custom_properties: customProperties,
  };

  // Session replay — remove this block if @launchdarkly/session-replay is not installed
  const sessionID = LDRecord?.getSession()?.sessionSecureID;
  if (sessionID) {
    feedbackData.o11y_session_id = sessionID;
  }

  if (prompt) {
    feedbackData.feedback_prompt = prompt;
  }

  client.track("$ld:feedback", feedbackData);
  client.flush();
}
