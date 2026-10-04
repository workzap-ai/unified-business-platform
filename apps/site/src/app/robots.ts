import type { MetadataRoute } from "next";
import { IS_PRODUCTION, PI } from "@/features/pi/config";

// Previews and staging are never indexed; only a production deploy is.
// Owner decision (4 Oct 2026): once live, everything is allowed, including the crawlers
// that train AI models. They are named so the choice is on the record and survives
// a future edit; "*" already covers every other crawler.
const AI_CRAWLERS = [
  "GPTBot", // OpenAI: training
  "OAI-SearchBot", // OpenAI: ChatGPT search
  "ChatGPT-User", // OpenAI: a person's request in ChatGPT
  "ClaudeBot", // Anthropic: training
  "Claude-SearchBot", // Anthropic: search
  "Claude-User", // Anthropic: a person's request in Claude
  "PerplexityBot", // Perplexity: search
  "Perplexity-User", // Perplexity: a person's request
  "Google-Extended", // Google: Gemini training and grounding
  "Applebot-Extended", // Apple: training
  "Bingbot", // Microsoft: Bing and Copilot
  "CCBot", // Common Crawl
  "Meta-ExternalAgent", // Meta: training
  "Bytespider", // ByteDance
  "Amazonbot", // Amazon
  "DuckAssistBot", // DuckDuckGo: answers
  "MistralAI-User", // Mistral: a person's request
];

export default function robots(): MetadataRoute.Robots {
  if (!IS_PRODUCTION) return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: [
      { userAgent: "*", allow: "/" },
      { userAgent: AI_CRAWLERS, allow: "/" },
    ],
    sitemap: `${PI.siteUrl}/sitemap.xml`,
    host: PI.siteUrl,
  };
}
