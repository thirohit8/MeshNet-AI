import path from "path";
import dotenv from "dotenv";

// Resolve config/.env relative to the project root (works in both
// ts-node-dev dev mode and compiled dist/ production mode).
const envPath = path.resolve(process.cwd(), "config/.env");
dotenv.config({ path: envPath });

import express from "express";
import cors from "cors";
import helmet from "helmet";
import { meshRouter }    from "./routes/mesh";
import { alertsRouter }  from "./routes/alerts";
import { messagesRouter } from "./routes/messages";
import { healthRouter }  from "./routes/health";
import { routeRouter }   from "./routes/route";
import { signalRouter }  from "./routes/signal";
import { requestLogger } from "./middleware/logger";
import { rateLimiter }   from "./middleware/rateLimit";

const app = express();
const PORT = process.env.PORT ?? 4000;

app.use(helmet());
app.use(cors({ origin: "*" })); // Restrict in production to known node origins
app.use(express.json({ limit: "64kb" }));
app.use(requestLogger);
app.use(rateLimiter);

app.use("/api/health", healthRouter);
app.use("/api/mesh", meshRouter);
app.use("/api/alerts", alertsRouter);
app.use("/api/messages", messagesRouter);
app.use("/api/route", routeRouter);
app.use("/api/signal", signalRouter);

app.listen(PORT, () => {
  console.log(`[MeshNet] Backend running on port ${PORT}`);
});

export default app;
