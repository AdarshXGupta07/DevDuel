import express from "express";
import cors from "cors";
import { connectDB } from "./config/db";
import userRouter from "./routes/user.routes";
import { Request, Response } from "express";
import dotenv from "dotenv";

dotenv.config();

const requiredEnvVars = ["ACCESS_TOKEN_SECRET", "REFRESH_TOKEN_SECRET"];

for (const key of requiredEnvVars) {
  if (!process.env[key]) {
    console.error(`❌ Environment variable ${key} is not set!`);
    process.exit(1);
  } else {
    console.log(`✅ Environment variable ${key} is loaded.`);
  }
}

const app = express();
app.use(cors());
app.use(express.json());

app.use("/api/v1/users", userRouter);

app.get("/api/v1/health", (_req: Request, res: Response) => {
  res.status(200).json({ status: "OK", message: "Server is running" });
});

const PORT = process.env.PORT || 8000;

connectDB()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`✅ Server is running on http://localhost:${PORT}`);
      console.log(`📝 API Documentation: http://localhost:${PORT}/api/v1/health`);
    });
  })
  .catch((error) => {
    console.error("❌ Failed to start server:", error.message);
    process.exit(1);
  });
