/**
 * The admin panel's "آزمایشگاه فروش" (sales playground) reuses the exact
 * same Conversation/Message/EndUser machinery as the real storefront chat
 * (getOrStartConversation, startNewConversation, resumeConversation) so a
 * shop owner testing their bot gets the same streaming UI, history list and
 * Langfuse tracing a real customer would. It is still not a real customer,
 * though — this sentinel webVisitorId is how every shop-facing query (the
 * "گفت‌وگوها" list, the "کاربران" list, the dashboard's user/message counts)
 * tells the two apart and excludes the former.
 */
export const PLAYGROUND_WEB_VISITOR_ID = "__playground__";
