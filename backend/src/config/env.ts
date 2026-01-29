import dotenv from "dotenv";
dotenv.config();
export const env = {
  ACCESS_TOKEN_SECRET: process.env.ACCESS_TOKEN_SECRET as string,
  REFRESH_TOKEN_SECRET: process.env.REFRESH_TOKEN_SECRET as string,

  ACCESS_TOKEN_EXPIRY: process.env.ACCESS_TOKEN_EXPIRY ?? "15m",
  REFRESH_TOKEN_EXPIRY: process.env.REFRESH_TOKEN_EXPIRY ?? "7d",
};
for (const [key, value] of Object.entries(env)) {
  if (!value) {
    throw new Error(`❌ Missing environment variable: ${key}`);
  }
}

