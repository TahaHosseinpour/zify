export type Mode = "explore" | "product";

export type Intent =
  | "browse"
  | "search_product"
  | "ask_question"
  | "buy_intent"
  | "needs_clarification"
  | "objection"
  | "compare"
  | "other";

export type Stage = "browsing" | "considering" | "ready_to_buy";

export type ValueDriver =
  | "price"
  | "quality"
  | "speed"
  | "social_proof"
  | "features"
  | "support"
  | "other";

export type Objection =
  | "price_too_high"
  | "not_sure_if_fits"
  | "need_to_think"
  | "comparing_options"
  | "shipping_concern"
  | "trust_issue"
  | "none";

// "link_shown" is a buy link being rendered. Telegram url-buttons fire no
// callback, so a real "click" can only be recorded once links are served
// through a redirect; until then the two must not be conflated.
export type EventType = "message" | "search" | "click" | "link_shown" | "view";

export type ConversationMode = "explore" | "product";

export interface ChatRequest {
  shopId: string;
  endUserId: string;
  mode: Mode;
  productId?: string;
  threadId: string;
  message: string;
}

export interface SuggestedProduct {
  id: string;
  name: string;
  price: number | null;
  imageUrl: string | null;
  productUrl: string | null;
}

export interface ChatResponse {
  reply: string;
  mode: Mode;
  stage: Stage;
  intent: Intent;
  valueDriver?: ValueDriver;
  objection?: Objection;
  suggestedProductIds?: string[];
  products?: SuggestedProduct[];
  purchaseUrl?: string;
  /** The pinned product, if the turn is about one. Clients send it back. */
  productId?: string | null;
  /** False on turns told not to push (an objection, or "let me think"). */
  showBuyActions?: boolean;
}

export interface ExploreFilters {
  category?: string;
  maxPrice?: number;
  minPrice?: number;
  brand?: string;
  query?: string;
}
