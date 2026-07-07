import rateLimit from "express-rate-limit";

// Prevent a single node from flooding the relay with broadcasts.
// 60 requests per minute per IP — adjust per deployment.
export const rateLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Too many requests — slow down broadcast rate" },
});
